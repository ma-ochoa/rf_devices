"""Lights driven by RF codes (standalone or the light of a ceiling fan)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .calibration import lamp_from_jump, lamp_from_level, read_watts
from .const import (
    MODE_TOGGLE,
    ROLE_LIGHT_DOWN,
    ROLE_LIGHT_OFF,
    ROLE_LIGHT_ON,
    ROLE_LIGHT_TOGGLE,
    ROLE_LIGHT_UP,
)
from .entity import find_by_unique_id, last_on, setup_platform_entities
from .models import color_kelvins, color_modes
from .onoff import OnOffMixin

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(hub, device, key):
        if key != "fan_light":
            return RFLight(hub, device, key)
        if device["options"].get("light_name"):
            return RFNamedFanLight(hub, device, key)
        return RFFanLight(hub, device, key)

    setup_platform_entities(hass, entry, async_add_entities, "light", factory)


LAMP_COMMAND_GRACE = 6.0  # s after our own light command: the lamp may not have lit yet
FAN_QUIET = 90.0  # s after a fan change: the motor's ramp could look like the lamp

class RFLight(OnOffMixin, LightEntity):
    """On/off light, with colour temperature and brightness when the remote has them.

    * Colour temperature: the remote cycles through named modes; each mode has
      a Kelvin value, and the nearest mode is chosen by sending the presses
      needed (see select.py).
    * Brightness: the remote only has "brighter"/"dimmer" buttons that act
      while held. The level is estimated: holding for the configured full
      range time goes from minimum to maximum, and the lamp starts at full
      brightness when it gets power.
    """

    MIN_STEP = 12  # brightness changes smaller than this (of 255) are ignored

    def __init__(self, *args) -> None:
        super().__init__(*args)
        if self._key == "light":
            self._attr_name = None  # the entity takes the device name
        opts = self.device["options"]
        cmds = self.device.get("commands", {})
        self._kelvins = color_kelvins(self.device) if color_modes(self.device) > 1 else []
        self._dimmable = bool(opts.get("light_dim")) and ROLE_LIGHT_UP in cmds and ROLE_LIGHT_DOWN in cmds
        self._dim_time = float(opts.get("light_dim_time") or 5.0)
        if self._kelvins and "light_color" in cmds:
            mode = ColorMode.COLOR_TEMP
            self._attr_min_color_temp_kelvin = min(self._kelvins)
            self._attr_max_color_temp_kelvin = max(self._kelvins)
        elif self._dimmable:
            mode = ColorMode.BRIGHTNESS
        else:
            mode = ColorMode.ONOFF
            self._kelvins = []
        self._attr_color_mode = mode
        self._attr_supported_color_modes = {mode}
        self._attr_brightness = 255 if mode != ColorMode.ONOFF else None

    def _select(self):
        return find_by_unique_id(self.hass, f"{self.device['id']}_color")

    @property
    def color_temp_kelvin(self) -> int | None:
        if not self._kelvins:
            return None
        select = self._select()
        index = select.index if select is not None else 0
        return self._kelvins[index] if index < len(self._kelvins) else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if self._attr_brightness is not None and state is not None and last_on(state):
            self._attr_brightness = state.attributes.get("brightness") or 255

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.user_on_at = self.hass.loop.time()
        await self._async_set(True)
        if (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) and self._kelvins:
            select = self._select()
            if select is not None:
                nearest = min(range(len(self._kelvins)), key=lambda i: abs(self._kelvins[i] - kelvin))
                await select.async_select_option(select.options[nearest])
        if (brightness := kwargs.get(ATTR_BRIGHTNESS)) is not None and self._dimmable:
            await self._async_brightness(int(brightness))
        self.async_write_ha_state()

    async def _async_brightness(self, target: int) -> None:
        current = self._attr_brightness or 255
        delta = target - current
        if abs(delta) < self.MIN_STEP:
            return
        # Going to an end: hold a little longer so it really gets there.
        seconds = abs(delta) / 255 * self._dim_time
        if target in (1, 255) or target <= 3:
            seconds += 0.5
        await self.async_send_role(ROLE_LIGHT_UP if delta > 0 else ROLE_LIGHT_DOWN, hold=seconds)
        self._attr_brightness = max(1, min(255, target))

    @callback
    def power_changed(self, on: bool) -> None:
        super().power_changed(on)
        if on and self._attr_brightness is not None:
            self._attr_brightness = 255  # lamps start at full brightness


class RFFanLight(RFLight):
    """Light of a ceiling fan; named "Light" through translations."""

    _attr_translation_key = "fan_light"
    _roles = {"toggle": ROLE_LIGHT_TOGGLE, "on": ROLE_LIGHT_ON, "off": ROLE_LIGHT_OFF}
    _state_key = "light_state_entity"
    _threshold_key = "light_state_threshold"

    @property
    def _mode(self) -> str:
        return self.device["options"].get("light", MODE_TOGGLE)

    @property
    def _switch_entity(self) -> str | None:
        # A fan's wall switch is read by wall.py (gestures), never by the lamp.
        return None

    @property
    def _state_entity(self) -> str | None:
        # With a calibration the fan's aligner (or the lamp watcher below)
        # decides; a plain threshold would mistake a fast motor for the lamp.
        opts = self.device["options"]
        if opts.get("calibration") or opts.get("light_calibration"):
            return None
        return opts.get(self._state_key)

    @property
    def _lamp_calibration(self) -> dict | None:
        """The quick lamp calibration, used only when there is no full one."""
        opts = self.device["options"]
        if opts.get("calibration") or not opts.get("light_state_entity"):
            return None
        return opts.get("light_calibration")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._last_watts: float | None = None
        if self._lamp_calibration:
            meter = self.device["options"]["light_state_entity"]
            self._last_watts = read_watts(self.hass, meter)
            self.async_on_remove(
                async_track_state_change_event(self.hass, [meter], self._lamp_reading)
            )

    @callback
    def _lamp_reading(self, event: Event[EventStateChangedData]) -> None:
        """Quick calibration: follow the lamp from the meter.

        With the fan stopped the level tells; with it running only a sudden
        jump of about the lamp's watts does (a motor ramps). Readings right
        after our own command or a fan change are left alone.
        """
        cal = self._lamp_calibration
        try:
            watts = float(event.data["new_state"].state)
        except (AttributeError, TypeError, ValueError):
            return
        before, self._last_watts = self._last_watts, watts
        if cal is None or self.hub.calibrating:
            return
        now = self.hass.loop.time()
        if now - max(self.user_on_at, self.user_off_at) < LAMP_COMMAND_GRACE:
            return
        fan = find_by_unique_id(self.hass, f"{self.device['id']}_fan")
        fan_state = self.hass.states.get(fan.entity_id) if fan is not None else None
        if fan_state is not None and (dt_util.utcnow() - fan_state.last_changed).total_seconds() < FAN_QUIET:
            return  # the motor is still speeding up or slowing down
        if fan_state is not None and fan_state.state == "off":
            self.async_apply_measured(lamp_from_level(cal, watts))
        elif before is not None and (on := lamp_from_jump(cal, before, watts)) is not None:
            self.async_apply_measured(on)

    @callback
    def async_apply_measured(self, on: bool) -> None:
        """Called by the fan's power aligner; nothing is sent."""
        if self.hub.calibrating or self._op_lock.locked() or on == self._attr_is_on:
            return
        self._attr_is_on = on
        self.async_write_ha_state()

    @property
    def _power_on_allowed(self) -> bool:
        # Without a relay controller, never power a fan to get its light: the
        # fan could start spinning at night. With one, relay.py decides.
        return False


class RFNamedFanLight(RFFanLight):
    """Fan light with a name of its own (e.g. "Luz ventilador terraza").

    Home Assistant always prefixes an entity with its device's name, so the
    light is a device of its own, independent from the fan's, with that name.
    Only the RF Devices panel shows them together, as one remote.
    """

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._attr_name = None
        self._attr_translation_key = None

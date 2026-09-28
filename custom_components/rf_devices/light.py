"""Lights driven by RF codes (standalone or the light of a ceiling fan)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .calibration import lamp_from_jump, lamp_from_level, learn_lamp, read_watts
from .const import (
    DOMAIN,
    MODE_TOGGLE,
    ROLE_LIGHT_DOWN,
    ROLE_LIGHT_OFF,
    ROLE_LIGHT_ON,
    ROLE_LIGHT_TOGGLE,
    ROLE_LIGHT_UP,
)
from .entity import find_by_unique_id, last_on, setup_platform_entities
from .meter import Meter
from .models import color_kelvins, color_modes
from .onoff import OnOffMixin

# Nothing is polled; commands are queued by the hub, not by the platform.
_LOGGER = logging.getLogger(__name__)
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
LAMP_DRIFT_W = 1.0  # smaller changes are drift, not a switch
LAMP_SETTLE_READS, LAMP_SETTLE_EVERY = 20, 0.5  # after a change: read until 2 agree
LAMP_POLL_EVERY = 1.0  # live meters: seconds between readings
LAMP_JOIN_WINDOW = 20.0  # s: changes this close together may be one lamp switch in pieces
FAN_QUIET = 90.0  # s after a fan change: the motor's ramp could look like the lamp
FAN_QUIET_LIVE = 15.0  # ... with a live meter, settling is checked reading by reading

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
        self._lamp_timer = None
        self._lamp_settling: asyncio.Task | None = None
        self._meter_live = False
        self._jump_origin: tuple[float, float] | None = None  # (watts, loop time) before a change
        if self._lamp_calibration:
            meter = self.device["options"]["light_state_entity"]
            self._last_watts = read_watts(self.hass, meter)
            live_meter = Meter(self.hass, meter)
            self._meter_live = live_meter.direct
            if self._meter_live:
                poll = self.hass.async_create_background_task(
                    self._async_lamp_poll(live_meter), f"rf_devices lamp {self.entity_id}"
                )
                self.async_on_remove(poll.cancel)
            self.async_on_remove(
                async_track_state_change_event(self.hass, [meter], self._lamp_reading)
            )
            if fan_id := self._fan_entity_id():
                # The fan stopping is also a moment to check the lamp by level.
                self.async_on_remove(
                    async_track_state_change_event(self.hass, [fan_id], self._fan_changed)
                )
            self.async_on_remove(self._cancel_lamp_timer)

    @callback
    def _lamp_reading(self, event: Event[EventStateChangedData]) -> None:
        """Quick calibration: follow the lamp from the meter.

        With the fan stopped the level tells; with it running only a sudden
        jump of about the lamp's watts does (a motor ramps). Readings right
        after our own command or a fan change are left alone.
        """
        try:
            watts = float(event.data["new_state"].state)
        except (AttributeError, TypeError, ValueError):
            return
        self._lamp_value(watts)

    async def _async_lamp_poll(self, meter: Meter) -> None:
        """Live meter: read it every second, instead of waiting for its report to HA."""
        while True:
            if self._lamp_settling is None and (watts := await meter.async_read()) is not None:
                self._lamp_value(watts)
            await asyncio.sleep(LAMP_POLL_EVERY)

    @callback
    def _lamp_value(self, watts: float) -> None:
        cal = self._lamp_calibration
        if cal is None or self.hub.calibrating:
            return
        if (wait := self._lamp_quiet_left()) > 0:
            # Too soon to trust a reading; look again (by level) once it is quiet,
            # since the meter may not report anything new by then.
            _LOGGER.debug("%s: %s W while quiet (%.1f s left)", self.entity_id, watts, wait)
            self._schedule_lamp_check(wait)
            return
        _LOGGER.debug("%s: %s W (baseline %s, settling %s)", self.entity_id, watts, self._last_watts,
                      self._lamp_settling is not None)
        if self._last_watts is None or abs(watts - self._last_watts) < LAMP_DRIFT_W:
            self._last_watts = watts  # small drift: the new baseline
            return
        # Decide at once when this reading already tells (a remote press should
        # show immediately); the settle check below confirms or corrects it.
        if self._fan_off():
            self.async_apply_measured(lamp_from_level(cal, watts))
        elif (on := lamp_from_jump(cal, self._last_watts, watts)) is not None:
            self.async_apply_measured(on)
        if self._lamp_settling is None:
            self._lamp_settling = self.hass.async_create_task(self._async_lamp_settle())

    async def _async_lamp_settle(self) -> None:
        """A change started: read until it settles, then compare settled with settled.

        A lamp may light in two steps and a meter may report a change in two
        pieces, so a single reading-to-reading jump can miss it.
        """
        try:
            cal = self._lamp_calibration
            meter = Meter(self.hass, self.device["options"]["light_state_entity"])
            before, recent = self._last_watts, []
            for _ in range(LAMP_SETTLE_READS):
                value = await meter.async_read()
                if value is not None:
                    if self._fan_off() and self._lamp_quiet_left() <= 0:
                        # A lamp ramping up: decide as soon as it is past half its draw.
                        self.async_apply_measured(lamp_from_level(cal, value))
                    recent = [*recent, value][-2:]
                    if len(recent) == 2 and max(recent) - min(recent) <= LAMP_DRIFT_W:
                        break
                await asyncio.sleep(LAMP_SETTLE_EVERY)
            if not recent or cal is None:
                return
            after = recent[-1]
            self._last_watts = after
            if self._lamp_quiet_left() > 0:
                return
            if self._fan_off():
                self.async_apply_measured(lamp_from_level(cal, after))
                if before is not None and (on := lamp_from_jump(cal, before, after)) is not None:
                    self._learn_lamp(cal, after - before if on else before - after)
                return
            # A change reported in pieces: also try from where the changes began.
            now = self.hass.loop.time()
            origin = self._jump_origin if self._jump_origin and now - self._jump_origin[1] < LAMP_JOIN_WINDOW else None
            for start in (before, origin[0] if origin else None):
                if start is not None and (on := lamp_from_jump(cal, start, after)) is not None:
                    self._jump_origin = None
                    self.async_apply_measured(on)
                    return
            if origin is None and before is not None:
                self._jump_origin = (before, now)
        finally:
            self._lamp_settling = None

    @callback
    def _fan_changed(self, _event: Event[EventStateChangedData]) -> None:
        self._schedule_lamp_check(self._lamp_quiet_left())

    def _learn_lamp(self, cal: dict, watts: float) -> None:
        """Live calibration of the lamp from a switch seen with the fan stopped."""
        if not self.device["options"].get("live_calibration", True):
            return
        select = self._select()
        mode = select.index if select is not None else None
        old = cal.get("light_modes") or [cal["light"]]
        if learn_lamp(cal, mode, round(watts, 2)):
            _LOGGER.info("%s: live calibration of the lamp: %s -> %s W", self.entity_id, old, cal["light_modes"])
            self.device["rev"] = self.device.get("rev", 0) + 1
            self.hass.async_create_task(self.hub.store.async_save())

    def _fan_entity_id(self) -> str | None:
        return er.async_get(self.hass).async_get_entity_id("fan", DOMAIN, f"{self.device['id']}_fan")

    def _fan_state(self):
        entity_id = self._fan_entity_id()
        return self.hass.states.get(entity_id) if entity_id else None

    def _fan_off(self) -> bool:
        state = self._fan_state()
        return state is not None and state.state == "off"

    def _lamp_quiet_left(self) -> float:
        """Seconds until readings can be trusted: after our own command or a fan change."""
        own = LAMP_COMMAND_GRACE - (self.hass.loop.time() - max(self.user_on_at, self.user_off_at, self.sent_at))
        fan = self._fan_state()
        quiet = FAN_QUIET_LIVE if self._meter_live else FAN_QUIET
        motor = quiet - (dt_util.utcnow() - fan.last_changed).total_seconds() if fan else 0
        return max(own, motor, 0.0)

    @callback
    def _cancel_lamp_timer(self) -> None:
        if self._lamp_timer is not None:
            self._lamp_timer()
            self._lamp_timer = None

    @callback
    def _schedule_lamp_check(self, delay: float) -> None:
        self._cancel_lamp_timer()
        self._lamp_timer = async_call_later(self.hass, delay + 0.5, self._lamp_check_later)

    @callback
    def _lamp_check_later(self, _now) -> None:
        self._lamp_timer = None
        self.hass.async_create_task(self._async_lamp_check())

    async def _async_lamp_check(self) -> None:
        """Deferred check by level, with a fresh (live when possible) reading."""
        cal = self._lamp_calibration
        if cal is None or self.hub.calibrating:
            return
        if (wait := self._lamp_quiet_left()) > 0:
            self._schedule_lamp_check(wait)
            return
        watts = await Meter(self.hass, self.device["options"]["light_state_entity"]).async_read()
        if watts is None:
            return
        self._last_watts = watts  # the baseline for the next jump
        if self._fan_off():
            self.async_apply_measured(lamp_from_level(cal, watts))
        # With the motor running only a jump can tell, and there was none.

    @callback
    def async_apply_measured(self, on: bool) -> None:
        """Called by the fan's power aligner; nothing is sent.

        Not right after our own command (HA, voice, the wall switch): the lamp
        may take a few seconds to light or fade, and the meter would still
        show the old state.
        """
        if self.hub.calibrating or self._op_lock.locked() or on == self._attr_is_on:
            return
        if self.hass.loop.time() - self.sent_at < LAMP_COMMAND_GRACE:
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

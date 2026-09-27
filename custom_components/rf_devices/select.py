"""Colour temperature of a light whose remote has a single "cycle" button.

The lamp cannot report its mode, so RF Devices remembers it: it knows the
order the button cycles through, advances it on every press it sends, resets
it to the power-up mode when the relay feeding the lamp is switched on, and
lets the power aligner correct it when the modes draw differently. Choosing
a mode sends as many presses as needed to get there.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ROLE_LIGHT_COLOR
from .entity import RFEntity, find_by_unique_id, setup_platform_entities
from .models import color_names

QUICK_CYCLE = 3.0  # seconds: an off/on quicker than this counts as a colour flick

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_platform_entities(hass, entry, async_add_entities, "select", RFColorSelect)


class RFColorSelect(RFEntity, SelectEntity):
    _attr_translation_key = "color"
    _attr_icon = "mdi:palette"

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        self._attr_options = color_names(device)
        start = int(device["options"].get("light_color_start", 1)) - 1
        self._start = start if 0 <= start < len(self._attr_options) else 0
        self._power_up = device["options"].get("light_color_power_up", "memory")
        self._off_at: float | None = None
        self.index = self._start

    @property
    def current_option(self) -> str:
        return self._attr_options[self.index]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in self._attr_options:
            self.index = self._attr_options.index(state.state)

    def _light(self):
        uid = f"{self.device['id']}_{'light' if self.device['type'] == 'light' else 'fan_light'}"
        return find_by_unique_id(self.hass, uid)

    async def async_select_option(self, option: str) -> None:
        target = self._attr_options.index(option)
        presses = (target - self.index) % len(self._attr_options)
        if not presses:
            return
        self.require_power()
        light = self._light()
        if light is not None and not light.is_on:
            raise HomeAssistantError(f"{self.device['name']}: switch the light on first")
        for _ in range(presses):
            await self.async_send_role(ROLE_LIGHT_COLOR)
            self.advance()

    @callback
    def advance(self, steps: int = 1) -> None:
        """A colour press was sent (by this select or by the colour button)."""
        self.index = (self.index + steps) % len(self._attr_options)
        self.async_write_ha_state()

    @callback
    def async_set_measured(self, index: int) -> None:
        """The power aligner recognised the mode from the lamp's draw."""
        if 0 <= index < len(self._attr_options) and index != self.index:
            self.index = index
            self.async_write_ha_state()

    @callback
    def power_changed(self, on: bool) -> None:
        """What the lamp's colour does when its power is cut and restored.

        * memory: it keeps the last mode (nothing changes here);
        * fixed: it always starts in the configured mode;
        * quick_cycle: a quick off/on advances to the next mode, a longer cut
          keeps it (lamps that change colour with a quick flick of the switch).
        """
        now = self.hass.loop.time()
        if not on:
            self._off_at = now
            return
        if self._power_up == "fixed":
            self.index = self._start
        elif self._power_up == "quick_cycle" and self._off_at is not None:
            if now - self._off_at <= QUICK_CYCLE:
                self.index = (self.index + 1) % len(self._attr_options)
        self._off_at = None

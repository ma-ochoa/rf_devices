"""Switches driven by RF codes."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import setup_platform_entities
from .onoff import OnOffMixin

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_platform_entities(hass, entry, async_add_entities, "switch", RFSwitch)


class RFSwitch(OnOffMixin, SwitchEntity):
    _attr_name = None
    _on_at_power_up = False

    @property
    def _power_on_allowed(self) -> bool:
        return False

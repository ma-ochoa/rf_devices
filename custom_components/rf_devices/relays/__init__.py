"""Relay adapters: what RF Devices can do with the relay that powers a device.

A ceiling fan with a light is often wired behind a smart relay (Shelly,
Sonoff, Tuya…) that a wall switch drives. RF Devices always switches the
relay through its Home Assistant entity; an adapter adds what only the
vendor can do, such as reading power live, detaching the wall switch from
the relay, or installing a fallback script on the device.

Adding a vendor: create a module in this package with a subclass of
``RelayAdapter`` and add it to ``ADAPTERS``. ``matches`` decides from the
relay's entity registry entry whether the adapter applies; the first match
wins, and ``GenericAdapter`` (HA entities only) is the fallback. See
``shelly.py`` for a complete example.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .base import RelayAdapter, resolve_source_entity
from .generic import GenericAdapter
from .shelly import ShellyAdapter

# Order matters: the first adapter whose ``matches`` returns True is used.
ADAPTERS: list[type[RelayAdapter]] = [ShellyAdapter]


def get_adapter(hass: HomeAssistant, relay_entity: str) -> RelayAdapter:
    """The adapter for a relay entity (a switch_as_x wrapper is followed to its source)."""
    source = resolve_source_entity(hass, relay_entity)
    entry = er.async_get(hass).async_get(source)
    for adapter in ADAPTERS:
        if entry is not None and adapter.matches(hass, entry):
            return adapter(hass, relay_entity, source, entry)
    return GenericAdapter(hass, relay_entity, source, entry)


__all__ = ["ADAPTERS", "GenericAdapter", "RelayAdapter", "ShellyAdapter", "get_adapter"]

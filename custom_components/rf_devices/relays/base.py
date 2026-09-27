"""Base class for relay adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@dataclass
class Capabilities:
    """What an adapter supports. The panel only offers what is available."""

    # Can the wall switch be detached from the relay (mode B)?
    detach: bool = False
    # Can RF Devices change that setting on the device itself?
    set_detach: bool = False
    # Can the device run a fallback script (wall switch works if HA is down)?
    fallback_script: bool = False
    # Can power be read live from the device (instead of HA's pushed value)?
    live_power: bool = False
    # Free text shown in the panel (limitations, advice).
    notes: list[str] = field(default_factory=list)


class RelayAdapter:
    """Vendor-specific extras for a relay. The base class does nothing extra."""

    name = "generic"
    label = "Generic relay"

    def __init__(
        self,
        hass: HomeAssistant,
        relay_entity: str,
        source_entity: str,
        entry: er.RegistryEntry | None,
    ) -> None:
        self.hass = hass
        self.relay_entity = relay_entity  # what the user picked (maybe a wrapper)
        self.source_entity = source_entity  # the vendor's own entity
        self.entry = entry

    @classmethod
    def matches(cls, hass: HomeAssistant, entry: er.RegistryEntry) -> bool:
        return False

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities()

    async def async_get_detached(self) -> bool | None:
        """Whether the wall switch is detached from the relay; None if unknown."""
        return None

    async def async_set_detached(self, detached: bool) -> None:
        raise NotImplementedError

    async def async_install_fallback(self, wait_ms: int = 2000) -> None:
        raise NotImplementedError

    async def async_remove_fallback(self) -> None:
        raise NotImplementedError

    async def async_ack(self) -> None:
        """Confirm a wall-switch press to the fallback script."""

    def suggested_input(self) -> str | None:
        """Entity with the wall switch state, when the vendor exposes one."""
        return None

    def suggested_meter(self) -> str | None:
        """Power sensor measuring this relay, when the vendor exposes one."""
        return None

    def related_entities(self) -> list[str]:
        """Vendor entities to hide when RF Devices takes over (relay, inputs…)."""
        return [self.source_entity] if self.source_entity != self.relay_entity else []


def resolve_source_entity(hass: HomeAssistant, entity_id: str) -> str:
    """Follow a "switch as x" wrapper (e.g. a light made from a switch) to its switch."""
    reg = er.async_get(hass)
    entry = reg.async_get(entity_id)
    if entry is None or entry.platform != "switch_as_x" or not entry.config_entry_id:
        return entity_id
    config = hass.config_entries.async_get_entry(entry.config_entry_id)
    source = (config.options.get("entity_id") if config else None) or entity_id
    if source != entity_id and not source.startswith(("switch.", "light.")):
        # switch_as_x may store the registry id instead of the entity id
        found = reg.async_get(source)
        source = found.entity_id if found else entity_id
    return source

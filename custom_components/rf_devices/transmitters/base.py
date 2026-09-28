"""What every transmitter offers RF Devices: send a code and, maybe, learn one."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from ..hub import RFHub


class LearnError(HomeAssistantError):
    """Learning could not start or finish."""


@dataclass
class LearnEvent:
    stage: str  # sweep | frequency | press | captured | timeout | error
    data: dict[str, Any]


class Transmitter:
    """A Home Assistant entity that sends (and possibly learns) RF codes.

    Codes are always stored in Broadlink's packet format (see ``codec``);
    a transmitter that speaks another format converts on the way out and,
    when learning, on the way in.
    """

    #: Learning starts with a frequency sweep (the UI then offers to reuse
    #: the frequency found).
    sweeps = False

    def __init__(self, hass: HomeAssistant, hub: RFHub, entity_id: str) -> None:
        self.hass = hass
        self.hub = hub
        self.entity_id = entity_id
        self.registry_entry = er.async_get(hass).async_get(entity_id)

    @property
    def platform(self) -> str | None:
        """Integration that provides the entity (broadlink, esphome…)."""
        return self.registry_entry.platform if self.registry_entry else None

    async def async_send(self, code: str) -> None:
        raise NotImplementedError

    def learn_problem(self) -> str | None:
        """Why this transmitter cannot learn right now, or None if it can."""
        return "This transmitter cannot learn RF codes"

    async def async_learn(self, frequency: float | None) -> AsyncIterator[LearnEvent]:
        """Yield progress until ``captured``, ``timeout`` or ``error``."""
        raise LearnError(self.learn_problem() or "Learning is not supported")
        yield  # pragma: no cover - makes this an async generator

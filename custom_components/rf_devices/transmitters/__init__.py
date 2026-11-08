"""Transmitters: the Home Assistant entity that sends (and learns) the codes.

RF Devices stores every code as a Broadlink packet and hands it to a
``Transmitter`` chosen from the entity's domain:

* ``remote``: sent with ``remote.send_command``; a Broadlink remote can
  also learn (with a frequency sweep).
* ``radio_frequency`` (Home Assistant 2026.5+): sent as raw timings through
  the core RF helper, whatever the adapter (ESPHome, Broadlink…). An
  ESPHome device with an ``ir_rf_proxy`` receiver can also learn.

Adding a kind of transmitter: subclass ``Transmitter`` in this package and
map its entity domain in ``TRANSMITTERS``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from .base import LearnError, LearnEvent, Transmitter
from .radio_frequency import RadioFrequencyTransmitter
from .remote import RemoteTransmitter

if TYPE_CHECKING:
    from ..hub import RFHub

TRANSMITTERS: dict[str, type[Transmitter]] = {
    "remote": RemoteTransmitter,
    "radio_frequency": RadioFrequencyTransmitter,
}
DOMAINS = list(TRANSMITTERS)


def get_transmitter(hass: HomeAssistant, hub: RFHub, entity_id: str) -> Transmitter:
    domain = entity_id.split(".", 1)[0]
    cls = TRANSMITTERS.get(domain)
    if cls is None:
        raise LearnError(f"{entity_id} cannot send RF codes (use a remote or radio_frequency entity)")
    return cls(hass, hub, entity_id)


__all__ = [
    "DOMAINS",
    "TRANSMITTERS",
    "LearnError",
    "LearnEvent",
    "RadioFrequencyTransmitter",
    "RemoteTransmitter",
    "Transmitter",
    "get_transmitter",
]

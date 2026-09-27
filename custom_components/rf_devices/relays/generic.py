"""Any relay Home Assistant can switch (Sonoff, Tuya, Zigbee plugs, …).

Everything goes through Home Assistant entities: the relay entity is
switched, the wall switch (if its state is exposed) is read, and the power
meter is whatever sensor was chosen. Detaching the wall switch, if the
device supports it, has to be done in the vendor's own app.
"""

from __future__ import annotations

from .base import Capabilities, RelayAdapter


class GenericAdapter(RelayAdapter):
    name = "generic"
    label = "Generic relay (Home Assistant entities)"

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            detach=True,  # possible if the device allows it; set it in the vendor app
            notes=[
                "detach_in_vendor_app",
            ],
        )

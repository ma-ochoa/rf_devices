"""Diagnostics: what RF Devices knows about its devices, for bug reports.

Codes are summarised (type, frames, length), not included: they are large
and they are the user's remotes. Nothing here is secret, but the entity ids
and names of the relays and meters are kept, since they are what matters
when something goes wrong.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import codec
from .const import VERSION
from .hub import RFHub


def _command_summary(cmd: dict) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "frequency": cmd.get("frequency"),
        "hold": cmd.get("hold"),
        "label": cmd.get("label"),
    }
    try:
        analysis = codec.analyze(cmd["code"])
    except codec.CodecError as err:
        summary["error"] = str(err)
    else:
        summary.update(
            kind=analysis["kind"],
            frames=analysis["frames"],
            good_frames=analysis["good_frames"],
            repeat=analysis["repeat"],
            sent_ms=analysis["sent_ms"],
            needs_cleaning=analysis["needs_cleaning"],
        )
    return summary


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    hub: RFHub = entry.runtime_data
    devices = []
    for device in hub.store.devices.values():
        controller = hub.relays.get(device["id"])
        devices.append(
            {
                "id": device["id"],
                "name": device["name"],
                "type": device["type"],
                "rev": device.get("rev", 0),
                "transmitter": device.get("transmitter"),
                "options": device["options"],
                "commands": {
                    role: _command_summary(cmd) for role, cmd in device.get("commands", {}).items()
                },
                "relay": None
                if controller is None
                else {
                    "mode": controller.mode,
                    "relay": controller.relay,
                    "adapter": type(controller.adapter).__name__,
                    "powered": controller.powered,
                    "wall_gestures": None
                    if controller.wall is None
                    else {"actions": controller.wall.actions, "window": controller.wall.window},
                },
            }
        )
    return {
        "version": VERSION,
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "frequencies": hub.store.frequencies,
        "hidden_entities": hub.store.hidden,
        "calibrating": hub.calibrating,
        "devices": devices,
    }

"""Diagnostics: what RF Devices knows about its devices, for bug reports.

Codes are summarised (type, frames, length), not included: they are large
and they are the user's remotes. Nothing here is secret, but the entity ids
and names of the relays and meters are kept, since they are what matters
when something goes wrong. The rest of the report (transmitters, ESPHome
devices, entities, trace and log) comes from ``debug``.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import codec
from .const import VERSION
from .debug import async_build_report
from .hub import RFHub
from .models import KIND_ACTION, KIND_SOMFY, command_kind


def _command_summary(cmd: dict) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "frequency": cmd.get("frequency"),
        "hold": cmd.get("hold"),
        "label": cmd.get("label"),
    }
    kind = command_kind(cmd)
    if kind == KIND_SOMFY:
        return {**summary, "kind": "somfy", "button": cmd["button"]}
    if kind == KIND_ACTION:
        return {**summary, "kind": "action", "service": cmd["service"],
                "entity_id": cmd.get("entity_id"), "data": cmd.get("data")}
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


def config_summary(hub: RFHub) -> dict[str, Any]:
    """The entry and every device, with codes summarised."""
    entry = hub.entry
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
                "somfy": device.get("somfy"),
                "somfy_code": hub.store.somfy_code(int(device["somfy"]["address"]))
                if device.get("somfy") else None,
                "linked_entity": device.get("linked_entity"),
                "linked_light_entity": device.get("linked_light_entity"),
                "mirror": device.get("mirror"),
                "follow": device.get("follow"),
                "follow_somfy": [f"{a:06X}" for a in device.get("follow_somfy") or []],
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
        "following": sorted(hub.follower.entry_ids()) if hub.follower else [],
        "devices": devices,
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    """Home Assistant's own diagnostics download: the same report as the panel's button."""
    report = await async_build_report(hass, entry.runtime_data)
    return {**report.pop("config"), **report}

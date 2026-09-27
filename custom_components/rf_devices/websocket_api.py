"""WebSocket commands used by the RF Devices panel. All require an admin user."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import codec
from .calibration import async_calibrate, read_watts
from .const import DEVICE_TYPES, DOMAIN, MAX_SPEEDS, VERSION
from .entity import find_by_unique_id
from .hub import LearnError, RFHub, capture_result
from .meter import Meter
from .models import (
    LIGHT_SIDE_KEYS,
    entity_plan,
    missing_roles,
    registry_device_ids,
    roles,
    validate_device,
)
from .relay import MODE_DETACHED, relay_mode
from .relays import get_adapter
from .store import async_read_broadlink_codes


@callback
def async_register(hass: HomeAssistant) -> None:
    for handler in (
        ws_info,
        ws_devices,
        ws_device_save,
        ws_device_delete,
        ws_learn,
        ws_code_analyze,
        ws_code_clean,
        ws_code_send,
        ws_export,
        ws_import,
        ws_broadlink_codes,
        ws_calibrate,
        ws_relay_info,
        ws_relay_apply,
        ws_meter_live,
    ):
        websocket_api.async_register_command(hass, handler)


def _hub(hass: HomeAssistant) -> RFHub:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise LearnError("RF Devices is not set up")
    return entries[0].runtime_data


def _describe(hass: HomeAssistant, hub: RFHub, device: dict) -> dict:
    """Device plus what the UI needs to show it."""
    commands = {}
    for role, cmd in device.get("commands", {}).items():
        try:
            analysis = codec.analyze(cmd["code"])
            fp = codec.fingerprint(cmd["code"])
        except codec.CodecError:
            analysis, fp = None, None
        commands[role] = {**cmd, "analysis": analysis, "fingerprint": fp}
    ent_reg = er.async_get(hass)
    entities, light_entities = [], []
    for platform, key in entity_plan(device):
        if eid := ent_reg.async_get_entity_id(platform, DOMAIN, f"{device['id']}_{key}"):
            entities.append(eid)
            if device["type"] == "fan" and key in LIGHT_SIDE_KEYS:
                light_entities.append(eid)  # shown in the panel's light group
    dev_reg = dr.async_get(hass)
    ha_devices = [
        {"id": entry.id, "name": entry.name_by_user or entry.name}
        for ident in sorted(registry_device_ids(device))
        if (entry := dev_reg.async_get_device(identifiers={(DOMAIN, ident)}))
    ]
    return {
        **device,
        "rev": device.get("rev", 0),
        "ha_devices": ha_devices,
        "commands": commands,
        "roles": roles(device),
        "missing": missing_roles(device),
        "entities": entities,
        "light_entities": light_entities,
    }


def _reload(hass: HomeAssistant, hub: RFHub) -> None:
    hass.config_entries.async_schedule_reload(hub.entry.entry_id)


def _error(connection, msg, err: Exception) -> None:
    connection.send_error(msg["id"], "rf_devices_error", str(err))


@websocket_api.websocket_command({vol.Required("type"): "rf_devices/info"})
@websocket_api.require_admin
@callback
def ws_info(hass, connection, msg) -> None:
    try:
        hub = _hub(hass)
    except LearnError as err:
        _error(connection, msg, err)
        return
    transmitters = [
        {
            "entity_id": s.entity_id,
            "name": s.name,
            "can_learn": hub.can_learn(s.entity_id),
        }
        for s in hass.states.async_all("remote")
    ]
    connection.send_result(
        msg["id"],
        {
            "version": VERSION,
            "default_transmitter": hub.default_transmitter,
            "transmitters": transmitters,
            "frequencies": hub.store.frequencies,
            "device_types": DEVICE_TYPES,
            "max_speeds": MAX_SPEEDS,
            "min_interval": hub.min_interval,
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "rf_devices/devices"})
@websocket_api.require_admin
@callback
def ws_devices(hass, connection, msg) -> None:
    try:
        hub = _hub(hass)
    except LearnError as err:
        _error(connection, msg, err)
        return
    connection.send_result(
        msg["id"], [_describe(hass, hub, d) for d in hub.store.devices.values()]
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "rf_devices/device/save", vol.Required("device"): dict}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_device_save(hass, connection, msg) -> None:
    try:
        hub = _hub(hass)
        data = dict(msg["device"])
        # The UI sends commands back with their analysis attached; keep only stored fields.
        data["commands"] = {
            role: {k: v for k, v in cmd.items() if k in ("code", "frequency", "learned", "label", "hold", "source")}
            for role, cmd in data.get("commands", {}).items()
        }
        for key in ("roles", "missing", "entities", "light_entities", "ha_devices"):
            data.pop(key, None)
        stale_check = "rev" in data
        validated = validate_device(data)
        previous = hub.store.devices.get(validated["id"])
        if stale_check and previous is not None and validated["rev"] != previous.get("rev", 0):
            connection.send_error(
                msg["id"], "stale", "The device was changed elsewhere; reloaded the current version"
            )
            return
        await apply_relay_identity(hass, hub, previous, validated)
        device = await hub.store.async_upsert(validated)
    except (vol.Invalid, LearnError) as err:
        _error(connection, msg, err)
        return
    _reload(hass, hub)
    connection.send_result(msg["id"], _describe(hass, hub, device))


@websocket_api.websocket_command(
    {vol.Required("type"): "rf_devices/device/delete", vol.Required("device_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_device_delete(hass, connection, msg) -> None:
    try:
        hub = _hub(hass)
    except LearnError as err:
        _error(connection, msg, err)
        return
    old = hub.store.devices.get(msg["device_id"])
    if old and (old["options"].get("take_relay_name") or old["options"].get("take_relay_entity_id")):
        restored = {**old, "options": {**old["options"], "take_relay_name": False,
                                       "take_relay_entity_id": False}}
        await apply_relay_identity(hass, hub, old, restored)
    await hub.store.async_delete(msg["device_id"])
    _reload(hass, hub)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rf_devices/learn",
        vol.Optional("transmitter"): vol.Any(None, str),
        vol.Optional("frequency"): vol.Any(None, vol.Coerce(float)),
    }
)
@websocket_api.require_admin
@callback
def ws_learn(hass, connection, msg) -> None:
    """Subscription: streams learning stages until ``captured``, ``timeout`` or ``error``.

    Unsubscribing cancels the capture.
    """
    try:
        hub = _hub(hass)
        transmitter = msg.get("transmitter") or hub.default_transmitter
        hub._broadlink_device(transmitter)  # noqa: SLF001 - fail before subscribing
    except LearnError as err:
        _error(connection, msg, err)
        return

    def send(stage: str, data: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], {"stage": stage, **data}))

    async def run() -> None:
        try:
            async for event in hub.async_learn(transmitter, msg.get("frequency")):
                send(event.stage, event.data)
        except LearnError as err:
            send("error", {"message": str(err)})

    # Confirm the subscription first: the task starts eagerly and may emit at once.
    connection.send_result(msg["id"])
    task = hass.async_create_background_task(run(), "rf_devices learn")
    connection.subscriptions[msg["id"]] = task.cancel


@websocket_api.websocket_command(
    {vol.Required("type"): "rf_devices/code/analyze", vol.Required("code"): str}
)
@websocket_api.require_admin
@callback
def ws_code_analyze(hass, connection, msg) -> None:
    try:
        connection.send_result(msg["id"], capture_result(_strip(msg["code"]), None))
    except codec.CodecError as err:
        _error(connection, msg, err)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rf_devices/code/clean",
        vol.Required("code"): str,
        vol.Optional("frames", default=codec.DEFAULT_FRAMES): vol.All(int, vol.Range(1, 30)),
        vol.Optional("repeat", default=0): vol.All(int, vol.Range(0, 15)),
    }
)
@websocket_api.require_admin
@callback
def ws_code_clean(hass, connection, msg) -> None:
    try:
        code = codec.clean(_strip(msg["code"]), msg["frames"], msg["repeat"])
        connection.send_result(
            msg["id"],
            {"code": code, "analysis": codec.analyze(code), "fingerprint": codec.fingerprint(code)},
        )
    except codec.CodecError as err:
        _error(connection, msg, err)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rf_devices/code/send",
        vol.Required("code"): str,
        vol.Optional("transmitter"): vol.Any(None, str),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_code_send(hass, connection, msg) -> None:
    try:
        await _hub(hass).async_send(_strip(msg["code"]), msg.get("transmitter"))
    except Exception as err:  # noqa: BLE001 - reported to the UI
        _error(connection, msg, err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): "rf_devices/export", vol.Optional("device_ids"): [str]}
)
@websocket_api.require_admin
@callback
def ws_export(hass, connection, msg) -> None:
    try:
        connection.send_result(msg["id"], _hub(hass).store.export(msg.get("device_ids")))
    except LearnError as err:
        _error(connection, msg, err)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rf_devices/import",
        vol.Required("data"): dict,
        vol.Optional("replace", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_import(hass, connection, msg) -> None:
    try:
        hub = _hub(hass)
        result = await hub.store.async_import(msg["data"], msg["replace"])
    except (vol.Invalid, LearnError) as err:
        _error(connection, msg, err)
        return
    _reload(hass, hub)
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "rf_devices/broadlink_codes"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_broadlink_codes(hass, connection, msg) -> None:
    connection.send_result(msg["id"], await async_read_broadlink_codes(hass))


def _strip(code: str) -> str:
    code = code.strip()
    return code[4:] if code.startswith("b64:") else code


IDLE_MAX_W = 3.0  # the fan and its light must be off (below this) to calibrate


@websocket_api.websocket_command(
    {vol.Required("type"): "rf_devices/calibrate", vol.Required("device_id"): str}
)
@websocket_api.require_admin
@callback
def ws_calibrate(hass, connection, msg) -> None:
    """Subscription: run the power calibration of a saved fan, streaming progress.

    Unsubscribing stops it and switches the fan and its light off.
    """
    try:
        hub = _hub(hass)
        device = hub.store.devices.get(msg["device_id"])
        if device is None or device["type"] != "fan":
            raise LearnError("Save the fan first")
        opts = device["options"]
        meter = opts.get("light_state_entity")
        if not meter:
            raise LearnError("Choose the power meter first")
        fan = find_by_unique_id(hass, f"{device['id']}_fan")
        light = find_by_unique_id(hass, f"{device['id']}_fan_light")
        if fan is None:
            raise LearnError("The fan entity is not loaded yet")
        if not fan.powered:
            raise LearnError("The fan has no power (its relay is off)")
        watts = read_watts(hass, meter)
        if watts is None:
            raise LearnError(f"{meter} has no reading")
        if watts > IDLE_MAX_W:
            raise LearnError(
                f"Switch the fan and its light off with the remote first ({meter} reads {watts} W)"
            )
        if hub.calibrating or hub.learning:
            raise LearnError("Busy: a capture or calibration is running")
    except LearnError as err:
        _error(connection, msg, err)
        return

    async def set_light(on: bool) -> None:
        if light is None:
            return
        # Sent directly: the light's own state may be misled by the motor's draw.
        role = light._roles["toggle"] if light._toggle_mode else light._roles["on" if on else "off"]  # noqa: SLF001
        await light.async_send_role(role)
        await light.async_set_assumed_state(on)

    next_color = None
    select = find_by_unique_id(hass, f"{device['id']}_color")
    if light is not None and opts.get("light_color") and "light_color" in device["commands"]:
        async def next_color() -> None:
            await light.async_send_role("light_color")
            if select is not None:
                select.advance()

    def send(data: dict) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], data))

    async def run() -> None:
        hub.calibrating = True
        finished = False
        try:
            await fan.async_set_assumed_state(False)
            if light is not None:
                await light.async_set_assumed_state(False)
            async for event in async_calibrate(
                Meter(hass, meter),
                int(opts.get("speeds", 3)),
                fan.async_calibration_speed,
                fan.async_calibration_off,
                set_light,
                next_color,
                int(opts.get("light_colors", 3)) if next_color else 1,
                select.index if select is not None else 0,
            ):
                send(event)
            finished = True
        except Exception as err:  # noqa: BLE001 - reported to the UI
            send({"stage": "error", "message": str(err)})
        finally:
            hub.calibrating = False
            if not finished:
                # Leave everything off, as it was when calibration started.
                for step in (fan.async_calibration_off, lambda: _light_off(light)):
                    try:
                        await step()
                    except Exception:  # noqa: BLE001
                        pass

    connection.send_result(msg["id"])
    task = hass.async_create_background_task(run(), "rf_devices calibrate")
    connection.subscriptions[msg["id"]] = task.cancel


async def _light_off(light) -> None:
    if light is not None and light.is_on:
        await light.async_turn_off()


@websocket_api.websocket_command({vol.Required("type"): "rf_devices/relay/info", vol.Required("relay"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_relay_info(hass, connection, msg) -> None:
    """What the relay's vendor adapter can do, and what it suggests."""
    adapter = get_adapter(hass, msg["relay"])
    caps = adapter.capabilities
    detached = None
    if caps.set_detach:
        try:
            detached = await adapter.async_get_detached()
        except Exception:  # noqa: BLE001 - device offline: just unknown
            detached = None
    reg = er.async_get(hass)
    suggested_input = adapter.suggested_input()
    input_entry = reg.async_get(suggested_input) if suggested_input else None
    connection.send_result(
        msg["id"],
        {
            "adapter": adapter.name,
            "label": adapter.label,
            "source": adapter.source_entity,
            "capabilities": {
                "detach": caps.detach,
                "set_detach": caps.set_detach,
                "fallback_script": caps.fallback_script,
                "live_power": caps.live_power,
                "notes": caps.notes,
            },
            "detached": detached,
            "suggested_input": suggested_input,
            "input_disabled": bool(input_entry and input_entry.disabled_by),
            "suggested_meter": adapter.suggested_meter(),
            "related": adapter.related_entities(),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "rf_devices/relay/apply", vol.Required("device_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_relay_apply(hass, connection, msg) -> None:
    """Configure the relay device itself to match the saved mode (on request only).

    Mode B: detach the wall switch, enable its input entity in HA, install
    the fallback script if chosen. Mode A: re-attach the wall switch and
    remove the script.
    """
    try:
        hub = _hub(hass)
        device = hub.store.devices.get(msg["device_id"])
        if device is None or relay_mode(device) == "none":
            raise LearnError("Save the device with a relay first")
        opts = device["options"]
        adapter = get_adapter(hass, opts["power_entity"])
        caps = adapter.capabilities
        detached = relay_mode(device) == MODE_DETACHED
        done: list[str] = []
        if caps.set_detach:
            if await adapter.async_get_detached() != detached:
                await adapter.async_set_detached(detached)
                done.append("detached" if detached else "attached")
        if caps.fallback_script:
            if detached and opts.get("fallback_script"):
                await adapter.async_install_fallback(int(float(opts.get("fallback_wait", 2.0)) * 1000))
                done.append("script_installed")
            else:
                await adapter.async_remove_fallback()
        reg = er.async_get(hass)
        wall = opts.get("switch_entity")
        if detached and wall and (entry := reg.async_get(wall)) and entry.disabled_by:
            reg.async_update_entity(wall, disabled_by=None)
            if entry.config_entry_id:
                hass.config_entries.async_schedule_reload(entry.config_entry_id)
            done.append("input_enabled")
    except (LearnError, NotImplementedError, RuntimeError, OSError) as err:
        _error(connection, msg, err)
        return
    except Exception as err:  # noqa: BLE001 - network errors from the device
        _error(connection, msg, err)
        return
    connection.send_result(msg["id"], {"done": done})


def relay_switch_name(name: str, prefix: str) -> str:
    """"Luz de la terraza" -> "Interruptor luz de la terraza"."""
    return f"{prefix} {name[:1].lower()}{name[1:]}".strip()


async def apply_relay_identity(hass: HomeAssistant, hub: RFHub, old: dict | None, new: dict) -> None:
    """Names first when taking, entity ids first when giving back.

    The entity id can only be taken together with the name: unticking the
    name gives both back.
    """
    if not new["options"].get("take_relay_name"):
        new["options"]["take_relay_entity_id"] = False
    was_id = bool(old and old["options"].get("take_relay_entity_id"))
    if was_id and not new["options"].get("take_relay_entity_id"):
        await apply_take_entity_id(hass, hub, old, new)
        apply_take_name(hass, old, new)
    else:
        apply_take_name(hass, old, new)
        await apply_take_entity_id(hass, hub, old, new)


async def _rename_entity(hass: HomeAssistant, entity_id: str, new_entity_id: str) -> None:
    """Rename and wait until the old id is really free (the entity moves its state)."""
    er.async_get(hass).async_update_entity(entity_id, new_entity_id=new_entity_id)
    for _ in range(50):
        if hass.states.get(entity_id) is None:
            return
        await asyncio.sleep(0.1)


def _own_light_entity(hass: HomeAssistant, device: dict) -> str | None:
    key = "fan_light" if device["type"] == "fan" else device["type"]
    return er.async_get(hass).async_get_entity_id("light", DOMAIN, f"{device['id']}_{key}") or (
        er.async_get(hass).async_get_entity_id(device["type"], DOMAIN, f"{device['id']}_{key}")
    )


def _free_entity_id(hass: HomeAssistant, wanted: str) -> str:
    reg = er.async_get(hass)
    candidate, n = wanted, 2
    while reg.async_get(candidate) is not None or hass.states.get(candidate) is not None:
        candidate, n = f"{wanted}_{n}", n + 1
    return candidate


async def apply_take_entity_id(hass: HomeAssistant, hub: RFHub, old: dict | None, new: dict) -> None:
    """Swap entity ids with the relay when ticked; swap them back when unticked.

    Voice assistants (Alexa's YAML integration included), routines and
    dashboards know a device by its entity_id, not its name. Taking the
    relay's entity_id makes all of them drive the RF Devices light; the relay
    moves to "<domain>.interruptor_<old object id>".
    """
    opts = new["options"]
    was = bool(old and old["options"].get("take_relay_entity_id"))
    now = bool(opts.get("take_relay_entity_id")) and bool(opts.get("power_entity"))
    reg = er.async_get(hass)
    if now and not was:
        relay = opts["power_entity"]
        own = _own_light_entity(hass, new)
        if own is None or reg.async_get(relay) is None or own.split(".")[0] != relay.split(".")[0]:
            opts["take_relay_entity_id"] = False  # not possible (yet): nothing changed
            return
        domain, object_id = relay.split(".", 1)
        prefix = "interruptor" if (hass.config.language or "").startswith("es") else "switch"
        new_relay = _free_entity_id(hass, f"{domain}.{prefix}_{object_id}")
        await _rename_entity(hass, relay, new_relay)
        await _rename_entity(hass, own, relay)
        opts["entity_id_backup"] = {"relay_old": relay, "relay_new": new_relay, "own_old": own}
        _rename_relay_refs(hub, opts, relay, new_relay)
    elif was and not now:
        backup = (old["options"].get("entity_id_backup") or {}) if old else {}
        relay_old, relay_new, own_old = (backup.get(k) for k in ("relay_old", "relay_new", "own_old"))
        if relay_old and relay_new and own_old and reg.async_get(relay_old) and reg.async_get(relay_new):
            await _rename_entity(hass, relay_old, own_old)  # our light back
            await _rename_entity(hass, relay_new, relay_old)  # the relay back
            _rename_relay_refs(hub, opts, relay_new, relay_old)
        opts["entity_id_backup"] = None
    elif now and was:
        opts["entity_id_backup"] = old["options"].get("entity_id_backup")


def _rename_relay_refs(hub: RFHub, opts: dict, before: str, after: str) -> None:
    """Keep the integration's own references to the relay pointing at it."""
    if opts.get("power_entity") == before:
        opts["power_entity"] = after
    backup = opts.get("take_name_backup")
    if isinstance(backup, dict) and backup.get("relay") == before:
        backup["relay"] = after
    if before in hub.store.hidden:
        hub.store.hidden[hub.store.hidden.index(before)] = after


def _default_light_name(hass: HomeAssistant, device_name: str) -> str:
    name = device_name.strip()
    if (hass.config.language or "").startswith("es"):
        return f"Luz {name[:1].lower()}{name[1:]}"
    return f"{name} light"


def apply_take_name(hass: HomeAssistant, old: dict | None, new: dict) -> None:
    """Swap names with the relay when "take the relay's name" is ticked; undo when unticked.

    People (and voice assistants) already call the lamp by the relay's name.
    Ticking gives that name to the RF Devices light (the device, for a plain
    light) and renames the relay after its switch ("Interruptor …"). The
    previous names are kept so unticking puts everything back.
    """
    opts = new["options"]
    was = bool(old and old["options"].get("take_relay_name"))
    now = bool(opts.get("take_relay_name")) and bool(opts.get("power_entity"))
    reg = er.async_get(hass)
    if now and not was:
        relay = opts["power_entity"]
        entry = reg.async_get(relay)
        state = hass.states.get(relay)
        current = (entry and entry.name) or (state and state.name) or ""
        if not current:
            opts["take_relay_name"] = False
            return
        own_key = "light_name" if new["type"] == "fan" else "name"
        own = (opts.get("light_name") if own_key == "light_name" else new["name"]) or ""
        prefix = "Interruptor" if (hass.config.language or "").startswith("es") else "Switch"
        if own and current.lower() == relay_switch_name(own, prefix).lower():
            # Already swapped by hand: remember the relay's original name (the light's).
            opts["take_name_backup"] = {
                "relay": relay, "relay_name": own, "own_key": own_key, "own_name": None,
            }
            return
        opts["take_name_backup"] = {
            "relay": relay,
            "relay_name": entry.name if entry else None,
            "own_key": own_key,
            "own_name": opts.get("light_name") if own_key == "light_name" else new["name"],
        }
        if own_key == "light_name":
            opts["light_name"] = current
        else:
            new["name"] = current
        if entry is not None:
            reg.async_update_entity(relay, name=relay_switch_name(current, prefix))
    elif was and not now:
        # The new options' copy is the one kept up to date if the relay's
        # entity id was just given back.
        backup = opts.get("take_name_backup") or ((old["options"].get("take_name_backup") or {}) if old else {})
        relay = backup.get("relay")
        ids = (old["options"].get("entity_id_backup") or {}) if old else {}
        if relay and relay == ids.get("relay_new") and reg.async_get(relay) is None:
            relay = ids.get("relay_old")  # its entity id was given back just before
        if relay and reg.async_get(relay) is not None:
            reg.async_update_entity(relay, name=backup.get("relay_name"))
        if backup.get("own_key") == "light_name":
            # Never leave the light with the relay's name: if it had none of
            # its own before, call it after the fan ("Luz ventilador …").
            opts["light_name"] = backup.get("own_name") or _default_light_name(hass, new["name"])
        elif backup.get("own_key") == "name" and backup.get("own_name"):
            new["name"] = backup["own_name"]
        opts["take_name_backup"] = None
    elif now and was:
        opts["take_name_backup"] = old["options"].get("take_name_backup")


METER_LIVE_EVERY = 1.0  # seconds between live readings while the panel watches a meter


@websocket_api.websocket_command({vol.Required("type"): "rf_devices/meter/live", vol.Required("entity_id"): str})
@websocket_api.require_admin
@callback
def ws_meter_live(hass, connection, msg) -> None:
    """Subscription: the meter's value every second, read from the device when possible.

    Only while the panel is open (unsubscribing stops it), so nothing polls
    the device when nobody is looking.
    """
    meter = Meter(hass, msg["entity_id"])

    async def run() -> None:
        last = object()
        while True:
            value = await meter.async_read()
            if value != last:
                last = value
                connection.send_message(
                    websocket_api.event_message(msg["id"], {"watts": value, "direct": meter.direct})
                )
            await asyncio.sleep(METER_LIVE_EVERY)

    connection.send_result(msg["id"])
    task = hass.async_create_background_task(run(), "rf_devices meter live")
    connection.subscriptions[msg["id"]] = task.cancel

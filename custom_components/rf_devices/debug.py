"""Remote debugging: a trace of what RF Devices did and a report to download.

The panel's *Diagnostics* button downloads ``async_build_report``: versions,
transmitters (and why each can or cannot learn), the ESPHome devices that
offer RF or IR, the entities RF Devices uses, the devices' configuration
(codes summarised), and two in-memory rings:

* ``trace``: every transmission, every learning stage and every burst an
  RF receiver delivered while learning (raw timings included, so a failed
  capture can be analysed);
* ``log``: warnings and errors from RF Devices and the integrations it
  relies on (and debug lines when debug logging is on).

Nothing is written to disk; both rings are lost on restart.
"""

from __future__ import annotations

import logging
import traceback
from collections import deque
from typing import TYPE_CHECKING, Any

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import CONF_POWER_SWITCH, DOMAIN, VERSION

if TYPE_CHECKING:
    from .hub import RFHub

TRACE_SIZE = 400
LOG_SIZE = 300
MAX_TIMINGS = 600  # per received burst in the trace
DATA_TRACE = f"{DOMAIN}_trace"
DATA_LOG = f"{DOMAIN}_log"

# Loggers whose records go to the report (at whatever level they are set to).
WATCHED_LOGGERS = (
    "custom_components.rf_devices",
    "homeassistant.components.radio_frequency",
    "homeassistant.components.esphome",
    "homeassistant.components.broadlink",
    "aioesphomeapi",
    "broadlink",
)
RELATED_COMPONENTS = ("broadlink", "esphome", "radio_frequency", "infrared", "shelly")
RF_INFO_TYPES = ("RadioFrequencyInfo", "InfraredInfo")


def _now() -> str:
    return dt_util.utcnow().isoformat(timespec="milliseconds")


@callback
def trace(hass: HomeAssistant, kind: str, **data: Any) -> None:
    """Remember one thing RF Devices did (cheap: a dict in a bounded deque)."""
    ring = hass.data.setdefault(DATA_TRACE, deque(maxlen=TRACE_SIZE))
    ring.append({"t": _now(), "kind": kind, **data})


def clip(timings: list[int]) -> list[int]:
    return list(timings[:MAX_TIMINGS])


class _RingHandler(logging.Handler):
    def __init__(self, ring: deque) -> None:
        super().__init__(logging.DEBUG)
        self.ring = ring

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "t": dt_util.utc_from_timestamp(record.created).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                entry["exception"] = "".join(traceback.format_exception(*record.exc_info))[-3000:]
            self.ring.append(entry)
        except Exception:  # noqa: BLE001 - logging must never raise
            self.handleError(record)


@callback
def async_start_log_capture(hass: HomeAssistant) -> None:
    """Keep the latest records of the watched loggers in memory (once per HA run)."""
    if DATA_LOG in hass.data:
        return
    ring: deque = deque(maxlen=LOG_SIZE)
    handler = _RingHandler(ring)
    hass.data[DATA_LOG] = (ring, handler)
    for name in WATCHED_LOGGERS:
        logging.getLogger(name).addHandler(handler)


def _state(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    state = hass.states.get(entity_id)
    reg = er.async_get(hass).async_get(entity_id)
    out: dict[str, Any] = {"entity_id": entity_id}
    if reg is not None:
        out.update(platform=reg.platform, disabled_by=reg.disabled_by, hidden_by=reg.hidden_by)
    if state is None:
        out["state"] = None
    else:
        out.update(
            state=state.state,
            attributes=dict(state.attributes),
            last_changed=state.last_changed.isoformat(),
        )
    return out


def _entity_ids_in(value: Any) -> set[str]:
    """Every string that looks like an entity id inside a device's options."""
    found: set[str] = set()
    if isinstance(value, str):
        if "." in value and " " not in value and value.split(".", 1)[0].isidentifier():
            found.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            found |= _entity_ids_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= _entity_ids_in(item)
    return found


def _transmitters(hass: HomeAssistant, hub: RFHub) -> list[dict[str, Any]]:
    from .transmitters import DOMAINS

    ent_reg = er.async_get(hass)
    ids = {s.entity_id for s in hass.states.async_all(DOMAINS)}
    # Disabled ones have no state but matter ("disabled by integration").
    ids |= {e.entity_id for e in ent_reg.entities.values() if e.domain in DOMAINS}
    out = []
    for entity_id in sorted(ids):
        info = _state(hass, entity_id)
        try:
            tx = hub.transmitter(entity_id)
            info.update(kind=type(tx).__name__, sweeps=tx.sweeps, learn_problem=tx.learn_problem())
            if entity_id.startswith("radio_frequency."):
                try:
                    info["frequency_ranges"] = tx._ranges()
                except Exception as err:  # noqa: BLE001
                    info["frequency_ranges"] = f"error: {err}"
        except Exception as err:  # noqa: BLE001
            info["error"] = str(err)
        out.append(info)
    return out


def info_dict(info: Any) -> dict[str, Any]:
    keep = ("key", "object_id", "name", "capabilities", "frequency_min", "frequency_max",
            "supported_modulations", "receiver_frequency", "device_id", "disabled_by_default")
    return {"type": type(info).__name__, **{k: getattr(info, k) for k in keep if hasattr(info, k)}}


def _esphome(hass: HomeAssistant) -> list[dict[str, Any]]:
    """ESPHome devices, in detail for those offering RF or IR."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    out = []
    for entry in hass.config_entries.async_entries("esphome"):
        data = getattr(entry, "runtime_data", None)
        infos = [
            info
            for group in (getattr(data, "info", None) or {}).values()
            for info in group.values()
        ]
        rf = [i for i in infos if type(i).__name__ in RF_INFO_TYPES]
        entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        has_rf = bool(rf) or any(e.domain in ("radio_frequency", "infrared") for e in entities)
        item: dict[str, Any] = {"title": entry.title, "state": str(entry.state)}
        device_info = getattr(data, "device_info", None)
        if device_info is not None:
            item["device_info"] = {
                k: getattr(device_info, k, None)
                for k in ("name", "model", "manufacturer", "project_name", "project_version",
                          "esphome_version", "compilation_time")
            }
        devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        item["registry"] = [
            {"name": d.name, "model": d.model, "manufacturer": d.manufacturer,
             "sw_version": d.sw_version, "hw_version": d.hw_version}
            for d in devices
        ]
        if has_rf:
            item.update(
                available=getattr(data, "available", None),
                rf_ir_infos=[info_dict(i) for i in rf],
                entity_info_types=sorted({type(i).__name__ for i in infos}),
                entities=[
                    {"entity_id": e.entity_id, "disabled_by": e.disabled_by,
                     "state": (s.state if (s := hass.states.get(e.entity_id)) else None)}
                    for e in entities
                ],
            )
        out.append(item)
    return out


def _involved_entities(hass: HomeAssistant, hub: RFHub) -> list[dict[str, Any]]:
    ids: set[str] = set()
    for device in hub.store.devices.values():
        ids |= _entity_ids_in(device.get("options", {}))
        if device.get("transmitter"):
            ids.add(device["transmitter"])
    ids.add(hub.default_transmitter)
    if power := hub.entry.options.get(CONF_POWER_SWITCH):
        ids.add(power)
    ids |= {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), hub.entry.entry_id)
    }
    return [_state(hass, i) for i in sorted(ids) if hass.states.get(i) or er.async_get(hass).async_get(i)]


async def async_build_report(hass: HomeAssistant, hub: RFHub) -> dict[str, Any]:
    from .diagnostics import config_summary

    log = hass.data.get(DATA_LOG)
    return {
        "generated": _now(),
        "rf_devices": VERSION,
        "home_assistant": HA_VERSION,
        "components": {c: c in hass.config.components for c in RELATED_COMPONENTS},
        "rf_devices_log_level": logging.getLevelName(
            logging.getLogger("custom_components.rf_devices").getEffectiveLevel()
        ),
        "config": config_summary(hub),
        "transmitters": _transmitters(hass, hub),
        "esphome": _esphome(hass),
        "entities": _involved_entities(hass, hub),
        "trace": list(hass.data.get(DATA_TRACE, [])),
        "log": list(log[0]) if log else [],
    }

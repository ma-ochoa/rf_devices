"""Device model: validation, command roles and the entities each device creates.

Stored device::

    {
      "id": "a1b2c3",
      "name": "Luz cama",
      "type": "light",                 # light | switch | cover | fan | buttons
      "transmitter": null,             # remote entity, null = the hub default
      "options": {...},                # see OPTION_SCHEMAS
      "commands": {
        "toggle": {"code": "<base64>", "frequency": 433.92,
                   "learned": "2026-09-25T10:00:00+00:00", "label": null},
        "x_timer": {"code": "...", "label": "Temporizador"}
      }
    }

Commands whose role starts with ``x_`` are extra buttons on any device type.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import voluptuous as vol

from . import codec
from .const import (
    ATTR_CODE,
    ATTR_FREQUENCY,
    ATTR_HOLD,
    ATTR_LABEL,
    ATTR_LEARNED,
    DEVICE_TYPES,
    EXTRA_PREFIX,
    LIGHT_EXTRA_ROLES,
    MAX_PRESETS,
    MAX_SPEEDS,
    MAX_TIMERS,
    MODE_BUTTONS,
    MODE_NONE,
    MODE_OFF_BUTTON,
    MODE_ONOFF,
    MODE_TOGGLE,
    PRESET_PREFIX,
    ROLE_CLOSE,
    ROLE_DIRECTION,
    ROLE_FORWARD,
    ROLE_LIGHT_COLOR,
    ROLE_LIGHT_DOWN,
    ROLE_LIGHT_OFF,
    ROLE_LIGHT_ON,
    ROLE_LIGHT_TOGGLE,
    ROLE_LIGHT_UP,
    ROLE_OFF,
    ROLE_ON,
    ROLE_OPEN,
    ROLE_POWER,
    ROLE_REVERSE,
    ROLE_STOP,
    ROLE_TOGGLE,
    SPEED_PREFIX,
    SYNC_PREFIX,
    TIMER_PREFIX,
    TYPE_BUTTONS,
    TYPE_COVER,
    TYPE_FAN,
    TYPE_LIGHT,
    TYPE_SWITCH,
    WALL_ACTIONS,
)

ROLE_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def _code(value: Any) -> str:
    value = str(value).strip()
    if value.startswith("b64:"):
        value = value[4:]
    try:
        codec.decode(value)
    except codec.CodecError as err:
        raise vol.Invalid(f"invalid code: {err}") from err
    return value


def _role(value: Any) -> str:
    value = str(value)
    if not ROLE_RE.match(value):
        raise vol.Invalid(f"invalid command role: {value}")
    return value


COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CODE): _code,
        vol.Optional(ATTR_FREQUENCY): vol.Any(None, vol.Coerce(float)),
        vol.Optional(ATTR_LEARNED): vol.Any(None, str),
        vol.Optional(ATTR_LABEL): vol.Any(None, str),
        # The code as first cleaned, kept so the number of frames can be changed
        # back and forth without losing the original pause between frames.
        vol.Optional("source"): vol.Any(None, _code),
        # Seconds to keep the button "pressed" (dimmers, blinds); 0 = one press.
        vol.Optional(ATTR_HOLD, default=0): vol.All(vol.Coerce(float), vol.Range(0, 10)),
    }
)

_ENTITY_ID = vol.Any(None, vol.Match(r"^[a-z_]+\.[a-z0-9_]+$"))

# Feedback and power options shared by on/off devices.
#   state_entity     real state: a binary entity, or a power sensor (W) compared
#                    with state_threshold. When set it wins over what was sent.
#   power_entity     relay that feeds the device. While it is off the device is
#                    off and RF commands are refused. RF Devices NEVER switches it
#                    on by itself unless power_on_allowed is true (lights only):
#                    powering a ceiling fan usually lights its lamp.
_FEEDBACK = {
    vol.Optional("state_entity", default=None): _ENTITY_ID,
    vol.Optional("state_threshold", default=3.0): vol.All(vol.Coerce(float), vol.Range(0, 5000)),
}
CALIBRATION_SCHEMA = vol.Schema(
    {
        vol.Required("idle"): vol.Coerce(float),
        vol.Required("light"): vol.Coerce(float),
        vol.Required("speeds"): [vol.All([vol.Coerce(float)], vol.Length(min=2, max=2))],
        # Motor draw reached going down to each speed (PWM fans settle higher).
        vol.Optional("speeds_down"): [vol.Any(None, vol.Coerce(float))],
        vol.Optional("light_modes"): [vol.Coerce(float)],
        vol.Optional("settle"): vol.Coerce(float),
        vol.Optional("measured"): str,
        vol.Optional("direct"): bool,
        # Speed matching band: max(band_w, band_pct × speed's draw).
        vol.Optional("band_w"): vol.All(vol.Coerce(float), vol.Range(0.1, 20)),
        vol.Optional("band_pct"): vol.All(vol.Coerce(float), vol.Range(0.01, 1)),
        # When each value was last corrected by the live calibration ("<speed>_<up|down>").
        vol.Optional("learned"): {str: str},
    }
)

# Quick calibration: only idle and the lamp (per colour mode), measured with the fan stopped.
LIGHT_CALIBRATION_SCHEMA = vol.Schema(
    {
        vol.Required("idle"): vol.Coerce(float),
        vol.Required("light"): vol.Coerce(float),
        vol.Optional("light_modes"): [vol.Coerce(float)],
        vol.Optional("measured"): str,
        vol.Optional("direct"): bool,
    }
)

_LIGHT_EXTRAS = {
    vol.Optional("light_color", default=False): bool,  # button cycling colour temperature
    vol.Optional("light_colors", default=3): vol.All(vol.Coerce(int), vol.Range(1, 6)),  # modes it cycles
    # Names of the modes in the order the button cycles them (e.g. Frío, Neutro, Cálido),
    # and the mode the lamp starts in when it gets power (1-based).
    vol.Optional("light_color_names", default=list): [vol.All(str, vol.Strip, vol.Length(max=20))],
    vol.Optional("light_color_start", default=1): vol.All(vol.Coerce(int), vol.Range(1, 6)),
    # Colour mode after the lamp gets power: "memory" (keeps the last one),
    # "fixed" (always light_color_start), or "quick_cycle" (a quick off/on of the
    # power advances to the next mode; a longer cut keeps it).
    vol.Optional("light_color_power_up", default="memory"): vol.In(["memory", "fixed", "quick_cycle"]),
    # Colour temperature of each mode, for HA/Alexa colour-temperature control.
    vol.Optional("light_color_kelvin", default=list): [vol.All(vol.Coerce(int), vol.Range(1500, 10000))],
    # Seconds a brightness button must be held to go from minimum to maximum.
    vol.Optional("light_dim_time", default=5.0): vol.All(vol.Coerce(float), vol.Range(0.5, 30)),
    vol.Optional("light_dim", default=False): bool,  # brighter / dimmer buttons (held)
}
_HHMM = vol.Match(r"^([01]\d|2[0-3]):[0-5]\d$")
_POWER = {
    # The relay that powers the device (see relay.py).
    vol.Optional("power_entity", default=None): _ENTITY_ID,
    # "none": not wired to a relay; "coupled": the wall switch drives the relay
    # (mode A); "detached": Home Assistant reads the wall switch (mode B);
    # "wall_only": always powered, a wall switch (e.g. a detached Shelly input
    # whose relay output is not wired) only toggles the light by RF.
    vol.Optional("relay_mode"): vol.In(["none", "coupled", "detached", "wall_only"]),
    # Powering a fan to start it lights its lamp for a moment: opt-in only.
    vol.Optional("fan_power_on", default=False): bool,
    # After powering the relay: seconds before RF is sent (the receiver boots),
    # optionally cut short as soon as the meter sees the lamp.
    vol.Optional("power_up_delay", default=0.5): vol.All(vol.Coerce(float), vol.Range(0, 15)),
    vol.Optional("power_up_wait_meter", default=False): bool,
    # Then: seconds between switching the lamp off and the fan command.
    vol.Optional("power_up_gap", default=0.4): vol.All(vol.Coerce(float), vol.Range(0, 5)),
    # Then: if the meter still sees the lamp, send "light off" again (max 2).
    vol.Optional("power_up_check", default=True): bool,
    # When the relay powers up (wall switch, voice, HA) the lamp is expected to
    # light; a lamp with memory may stay off: if the meter does not see it,
    # send "light on". Never after a power-up done to start the fan.
    vol.Optional("ensure_light_on_power_up", default=True): bool,
    # Wall switch gestures (wall.py): action for 1–4 quick flips, and the
    # longest pause between flips of one gesture. Unset = light toggle only.
    vol.Optional("wall_actions"): vol.Schema(
        {vol.In(["1", "2", "3", "4"]): vol.In(list(WALL_ACTIONS))}
    ),
    vol.Optional("wall_window"): vol.All(vol.Coerce(float), vol.Range(0.2, 2.0)),
    vol.Optional("fallback_script", default=False): bool,  # mode B: script on the device
    # Seconds the script waits for Home Assistant to confirm a press.
    vol.Optional("fallback_wait", default=2.0): vol.All(vol.Coerce(float), vol.Range(0.5, 10)),
    vol.Optional("hide_sources", default=False): bool,  # hide the relay's own entities
    # The RF Devices light takes the relay's name; the relay is renamed after
    # its switch. Reversible: the previous names are kept in take_name_backup.
    vol.Optional("take_relay_name", default=False): bool,
    vol.Optional("take_name_backup", default=None): vol.Any(None, dict),
    # Also take the relay's entity_id, so voice assistants, routines and
    # dashboards that used the relay now drive the RF Devices light.
    vol.Optional("take_relay_entity_id", default=False): bool,
    vol.Optional("entity_id_backup", default=None): vol.Any(None, dict),
    # Relay off after this many minutes with everything off (0 = never), because
    # a relay energised for years can weld its contacts.
    vol.Optional("idle_off_minutes", default=0): vol.All(vol.Coerce(int), vol.Range(0, 1440)),
    vol.Optional("idle_off_when", default="always"): vol.In(["always", "night", "hours"]),
    vol.Optional("idle_off_from", default="23:00"): _HHMM,
    vol.Optional("idle_off_to", default="08:00"): _HHMM,
}

# Covers: powering the motor moves nothing, so the relay may be switched on to
# send a command. The meter (W, or an on/off "moving" entity) tells when the
# motor really runs. Wall buttons are independent of the relay: one input steps
# open → stop → close → stop; with a second one the first opens and it closes.
# "momentary": push buttons, a press acts; "maintained": a switch or an
# up/0/down rocker, every change acts (two inputs: back to 0 stops).
_COVER_POWER = {
    vol.Optional("power_entity", default=None): _ENTITY_ID,
    vol.Optional("power_on_allowed", default=True): bool,
    vol.Optional("power_up_delay", default=1.0): vol.All(vol.Coerce(float), vol.Range(0, 15)),
    **_FEEDBACK,
    vol.Optional("switch_entity", default=None): _ENTITY_ID,
    vol.Optional("switch_close_entity", default=None): _ENTITY_ID,
    vol.Optional("wall_type", default="momentary"): vol.In(["momentary", "maintained"]),
}

OPTION_SCHEMAS = {
    TYPE_LIGHT: vol.Schema(
        {
            vol.Optional("mode", default=MODE_TOGGLE): vol.In([MODE_TOGGLE, MODE_ONOFF]),
            vol.Optional("switch_entity", default=None): _ENTITY_ID,
            **_FEEDBACK,
            **_POWER,
            vol.Optional("power_on_allowed", default=False): bool,
            **_LIGHT_EXTRAS,
        }
    ),
    TYPE_SWITCH: vol.Schema(
        {
            vol.Optional("mode", default=MODE_ONOFF): vol.In([MODE_TOGGLE, MODE_ONOFF]),
            vol.Optional("switch_entity", default=None): _ENTITY_ID,
            **_FEEDBACK,
            **_POWER,
        }
    ),
    TYPE_COVER: vol.Schema(
        {
            vol.Optional("open_time", default=0): vol.All(vol.Coerce(float), vol.Range(0, 300)),
            vol.Optional("close_time", default=0): vol.All(vol.Coerce(float), vol.Range(0, 300)),
            vol.Optional("device_class", default="shutter"): vol.In(
                ["shutter", "blind", "curtain", "awning", "garage", "gate", "shade"]
            ),
            **_COVER_POWER,
        }
    ),
    TYPE_FAN: vol.Schema(
        {
            vol.Optional("switch_entity", default=None): _ENTITY_ID,  # wall switch (mode B)
            vol.Optional("speeds", default=3): vol.All(vol.Coerce(int), vol.Range(1, MAX_SPEEDS)),
            # Speed used by "turn on" without a speed: a number, or 0 for the last one.
            # Sending a speed code (not the power button) makes it predictable.
            vol.Optional("turn_on_speed", default=1): vol.All(vol.Coerce(int), vol.Range(0, MAX_SPEEDS)),
            # Percentage shown for each speed and upper bound of its range
            # (empty = even split). Voice assistants speak in percentages.
            vol.Optional("speed_percentages", default=list): [vol.All(vol.Coerce(int), vol.Range(1, 100))],
            # "Set to 2" often arrives as 2 %: percentages up to the number of
            # speeds are taken as the speed itself.
            vol.Optional("small_pct_is_speed", default=True): bool,
            # "off": a dedicated off button; "toggle": one power button that alternates.
            vol.Optional("power", default=MODE_OFF_BUTTON): vol.In([MODE_OFF_BUTTON, MODE_TOGGLE]),
            # "toggle": one button reverses; "buttons": summer/winter buttons.
            vol.Optional("direction", default=MODE_NONE): vol.In(
                [MODE_NONE, MODE_TOGGLE, MODE_BUTTONS]
            ),
            vol.Optional("presets", default=list): vol.All(
                [vol.All(str, vol.Length(min=1, max=30))], vol.Length(max=MAX_PRESETS)
            ),
            vol.Optional("timers", default=list): vol.All(
                [vol.All(str, vol.Length(min=1, max=20))], vol.Length(max=MAX_TIMERS)
            ),
            vol.Optional("light", default=MODE_NONE): vol.In([MODE_NONE, MODE_TOGGLE, MODE_ONOFF]),
            # Full name of the fan's light entity, e.g. "Luz ventilador terraza".
            vol.Optional("light_name", default=None): vol.Any(None, vol.All(str, vol.Strip, vol.Length(max=80))),
            **_LIGHT_EXTRAS,
            vol.Optional("light_state_entity", default=None): _ENTITY_ID,
            vol.Optional("light_state_threshold", default=3.0): vol.All(
                vol.Coerce(float), vol.Range(0, 5000)
            ),
            # Result of the power calibration wizard (see calibration.py).
            vol.Optional("calibration", default=None): vol.Any(None, CALIBRATION_SCHEMA),
            # Only the lamp (quick): tells the lamp from the motor without the full table.
            vol.Optional("light_calibration", default=None): vol.Any(None, LIGHT_CALIBRATION_SCHEMA),
            # Correct the table from settled live readings after own speed commands.
            vol.Optional("live_calibration", default=True): bool,
            **_POWER,
        }
    ),
    TYPE_BUTTONS: vol.Schema({}),
}

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("id"): vol.Any(None, vol.Match(r"^[a-z0-9]{4,32}$")),
        vol.Required("name"): vol.All(str, vol.Strip, vol.Length(min=1, max=80)),
        vol.Required("type"): vol.In(DEVICE_TYPES),
        vol.Optional("transmitter", default=None): _ENTITY_ID,
        vol.Optional("options", default=dict): dict,
        # Pause between two transmissions for this device (None = integration default).
        vol.Optional("command_interval", default=None): vol.Any(
            None, vol.All(vol.Coerce(float), vol.Range(0, 5))
        ),
        vol.Optional("commands", default=dict): {_role: COMMAND_SCHEMA},
        # Revision, bumped on every save: an editor holding an older copy is
        # refused instead of overwriting newer changes.
        vol.Optional("rev", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)


def new_id() -> str:
    return secrets.token_hex(4)


def validate_device(data: dict) -> dict:
    """Validate and normalise a device; assigns an id when missing."""
    device = DEVICE_SCHEMA(data)
    device["options"] = OPTION_SCHEMAS[device["type"]](device["options"])
    if not device.get("id"):
        device["id"] = new_id()
    return device


def roles(device: dict) -> list[dict]:
    """Command slots the device type needs, in display order.

    Each slot: ``{"role": str, "required": bool}``. Extra buttons are added
    after the type's own slots.
    """
    kind = device["type"]
    opts = device.get("options", {})
    slots: list[tuple[str, bool]] = []
    if kind in (TYPE_LIGHT, TYPE_SWITCH):
        if opts.get("mode") == MODE_TOGGLE:
            slots = [(ROLE_TOGGLE, True)]
        else:
            slots = [(ROLE_ON, True), (ROLE_OFF, True)]
    elif kind == TYPE_COVER:
        slots = [(ROLE_OPEN, True), (ROLE_CLOSE, True), (ROLE_STOP, False)]
    elif kind == TYPE_FAN:
        slots = [(ROLE_POWER if opts.get("power") == MODE_TOGGLE else ROLE_OFF, True)]
        slots += [(f"{SPEED_PREFIX}{n}", True) for n in range(1, opts.get("speeds", 3) + 1)]
        if opts.get("direction") == MODE_TOGGLE:
            slots.append((ROLE_DIRECTION, True))
        elif opts.get("direction") == MODE_BUTTONS:
            slots += [(ROLE_FORWARD, True), (ROLE_REVERSE, True)]
        slots += [(f"{PRESET_PREFIX}{n}", True) for n in range(1, len(opts.get("presets", [])) + 1)]
        if opts.get("light") == MODE_TOGGLE:
            slots.append((ROLE_LIGHT_TOGGLE, True))
        elif opts.get("light") == MODE_ONOFF:
            slots += [(ROLE_LIGHT_ON, True), (ROLE_LIGHT_OFF, True)]
    if kind == TYPE_FAN:
        slots += [(f"{TIMER_PREFIX}{n}", False) for n in range(1, len(opts.get("timers", [])) + 1)]
    has_light = kind == TYPE_LIGHT or (kind == TYPE_FAN and opts.get("light", MODE_NONE) != MODE_NONE)
    if has_light and opts.get("light_color"):
        slots.append((ROLE_LIGHT_COLOR, False))
    if has_light and opts.get("light_dim"):
        slots += [(ROLE_LIGHT_UP, False), (ROLE_LIGHT_DOWN, False)]
    result = [{"role": r, "required": req} for r, req in slots]
    result += [
        {"role": r, "required": False}
        for r in device.get("commands", {})
        if r.startswith(EXTRA_PREFIX)
    ]
    return result


def entity_plan(device: dict) -> list[tuple[str, str]]:
    """``(platform, key)`` for every entity the device creates.

    Toggle-only on/off entities without real feedback get a "sync" button
    that flips the state in HA without transmitting, to re-align it after
    the original remote was used.

    The unique id of each entity is ``f"{device_id}_{key}"``.
    """
    kind = device["type"]
    opts = device.get("options", {})
    plan: list[tuple[str, str]] = []
    if kind in (TYPE_LIGHT, TYPE_SWITCH):
        plan.append((kind, kind))
        if opts.get("mode") == MODE_TOGGLE and not opts.get("state_entity"):
            plan.append(("button", f"{SYNC_PREFIX}{kind}"))
    elif kind == TYPE_COVER:
        plan.append(("cover", "cover"))
    elif kind == TYPE_FAN:
        plan.append(("fan", "fan"))
        if opts.get("power") == MODE_TOGGLE:
            plan.append(("button", f"{SYNC_PREFIX}fan"))
        if opts.get("light", MODE_NONE) != MODE_NONE:
            plan.append(("light", "fan_light"))
            if opts.get("light") == MODE_TOGGLE and not opts.get("light_state_entity"):
                plan.append(("button", f"{SYNC_PREFIX}fan_light"))
    # Mirrors shown on the device page: live draw, what the aligner reads, power.
    meter = opts.get("state_entity") or opts.get("light_state_entity")
    if meter:
        plan.append(("sensor", "power"))
    if kind == TYPE_FAN and opts.get("calibration") and opts.get("light_state_entity"):
        plan.append(("sensor", "estimate"))
        plan.append(("sensor", "speed_estimate"))
    if opts.get("power_entity"):
        plan.append(("binary_sensor", "powered"))
    if color_modes(device) > 1 and "light_color" in device.get("commands", {}):
        plan.append(("select", "color"))
    offered = {slot["role"] for slot in roles(device)}
    for role in device.get("commands", {}):
        if role.startswith(EXTRA_PREFIX) or (
            role in offered and (role.startswith(TIMER_PREFIX) or role in LIGHT_EXTRA_ROLES)
        ):
            plan.append(("button", role))
    return plan


LIGHT_SIDE_KEYS = {"fan_light", f"{SYNC_PREFIX}fan_light", "color", *LIGHT_EXTRA_ROLES}


def on_light_device(device: dict, key: str) -> bool:
    """Whether an entity belongs to the fan's named light device, not the fan's.

    The lamp, its colour, dimming and sync go with the light; speeds, timers,
    extra buttons and the meter mirrors stay with the fan.
    """
    return has_named_light(device) and key in LIGHT_SIDE_KEYS


def missing_roles(device: dict) -> list[str]:
    cmds = device.get("commands", {})
    return [s["role"] for s in roles(device) if s["required"] and s["role"] not in cmds]


def light_device_id(device: dict) -> str:
    """Device registry id of a fan light that has a name of its own."""
    return f"{device['id']}_light"


def has_named_light(device: dict) -> bool:
    """A fan whose lamp is a device of its own, with its own name."""
    opts = device.get("options", {})
    return (
        device["type"] == TYPE_FAN
        and bool(opts.get("light_name"))
        and opts.get("light", MODE_NONE) != MODE_NONE
    )


_MODELS = {
    "en": {"light": "Light", "switch": "Switch", "cover": "Cover", "fan": "Fan",
           "fan_light": "Fan with light", "buttons": "Remote buttons"},
    "es": {"light": "Luz", "switch": "Interruptor", "cover": "Persiana", "fan": "Ventilador",
           "fan_light": "Ventilador con luz", "buttons": "Botones de mando"},
}


def device_model(device: dict, language: str = "en") -> str:
    """Line under the device name on its card, in the language of Home Assistant.

    A fan whose lamp has a name of its own is two independent devices in Home
    Assistant (the fan, and the light); only a lamp without a name of its own
    lives on the fan's device ("Fan with light").
    """
    labels = _MODELS["es" if language.startswith("es") else "en"]
    kind = device["type"]
    if kind == TYPE_FAN and not has_named_light(device) and (
        device.get("options", {}).get("light", MODE_NONE) != MODE_NONE
    ):
        kind = "fan_light"
    return labels.get(kind, kind)


def registry_device_ids(device: dict) -> set[str]:
    """Every device-registry identifier this stored device uses."""
    ids = {device["id"]}
    if has_named_light(device):
        ids.add(light_device_id(device))
    return ids


def color_modes(device: dict) -> int:
    """Colour-temperature modes the light cycles through (0 if it has no such button)."""
    opts = device.get("options", {})
    has_light = device["type"] == TYPE_LIGHT or (
        device["type"] == TYPE_FAN and opts.get("light", MODE_NONE) != MODE_NONE
    )
    return int(opts.get("light_colors", 3)) if has_light and opts.get("light_color") else 0


def color_names(device: dict) -> list[str]:
    names = list(device.get("options", {}).get("light_color_names") or [])
    count = color_modes(device)
    return [names[i] if i < len(names) and names[i] else str(i + 1) for i in range(count)]


_KELVIN_BY_NAME = (
    (("fri", "frí", "cold", "cool", "blanco", "white", "day"), 6000),
    (("neut", "natur"), 4000),
    (("cal", "warm", "cálid"), 2700),
)


def color_kelvins(device: dict) -> list[int]:
    """Kelvin per colour mode: configured, guessed from the names, or spread out."""
    count = color_modes(device)
    given = list(device.get("options", {}).get("light_color_kelvin") or [])
    names = [n.lower() for n in color_names(device)]
    result = []
    for i in range(count):
        if i < len(given) and given[i]:
            result.append(int(given[i]))
            continue
        guess = next((k for keys, k in _KELVIN_BY_NAME if names[i].startswith(keys)), None)
        result.append(guess or round(6500 - i * (3800 / max(1, count - 1))))
    return result

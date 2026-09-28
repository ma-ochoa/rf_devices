"""Power calibration of fans with a light, and the aligner that uses it.

A single meter usually feeds both the fan motor and its lamp. Measuring every
speed with the light off and on gives a table of expected consumptions; when
the reading settles, the closest entry tells what the fan and the light are
really doing, even after someone used the original remote.

The lamp changes the reading at once; the motor takes seconds to speed up or
slow down, so readings are only trusted once they have been stable for a
while. It is an estimate: when two states consume about the same, only what
can be told apart (fan on/off, light on/off) is corrected.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .meter import Meter

_LOGGER = logging.getLogger(__name__)

# Timings come from a real ceiling fan on a Shelly Plus 2PM: the motor peaks
# at ~21 W when starting, then drifts down for ~2.5 min to ~4 W (speed 1).
# The Shelly reports only when the value moves ~1 W, at most every 6-8 s, so
# "no report for a few seconds" does not mean "settled".
# A speed change also ramps slowly (+1 W every 15-30 s for minutes), so a
# live reading counts as settled only once its trend is flat as well.
SAMPLE_EVERY = 0.5  # seconds between readings of the HA state
DIRECT_EVERY = 1.0  # seconds between live readings from the device
LIGHT_HOLD, LIGHT_MIN, LIGHT_MAX = 4.0, 3.0, 30.0  # the lamp is instant
LIGHT_TOLERANCE_W = 1.5
# Motor with live readings: flat within 0.5 W (or 3 %) and < 0.6 W/min, for at
# least 15 s and at least half the time since the command (at most 60 s). Each fan's pace is
# detected by itself: a fast motor (flat after ~20 s) is done in ~30 s, a slow
# PWM one keeps creeping and is followed for minutes (checked on real fans: 25-29 s
# vs 40-140 s, within 0.5 W of the final value).
FAN_HOLD, FAN_MIN, FAN_MAX = 15.0, 10.0, 300.0
FAN_HOLD_FRACTION, FAN_HOLD_MAX = 0.5, 60.0
FAN_TOLERANCE_W, FAN_TOLERANCE_PCT, FAN_MAX_SLOPE = 0.5, 0.03, 0.01
# Motor with only HA's pushed values (~1 W steps): hold longer, no slope.
SLOW_FAN_HOLD, SLOW_FAN_MIN, SLOW_FAN_MAX = 60.0, 120.0, 300.0
SLOW_FAN_TOLERANCE_W = 1.0
QUICK_DELAY = 5.0  # seconds after a change before correcting light and on/off
SLOW_SETTLE = 90.0  # pushed-only meters: seconds without a report = settled
ALIGN_HOLD = 20.0  # live meters: flat this long to count as settled
MIN_MARGIN_W = 2.0  # best match must beat the runner-up by this much
LIVE_MARGIN_W = 0.5  # ... when the table and readings are live (0.1 W steps)
COLOUR_STEP_TOLERANCE = 0.4  # W: a jump matches a colour press within this
COLOUR_STEP_MIN = 0.5  # W: jumps smaller than this cannot be seen
MONITOR_EVERY = 3.0  # live meters: seconds between readings while watching
REDECIDE_W = 0.3  # re-decide when the settled reading moves this much
COLOUR_HOLD_W = 0.25  # after a sudden jump the new level must hold within this
COLOUR_CONFIRM = 2  # readings the new level must hold to count as a colour press
# Speed matching: nearest calibrated speed, if it is within its band and
# clearly nearer than the runner-up (PWM and heat make readings wander).
DEFAULT_BAND_W = 0.3  # live-read calibrations (0.1 W resolution)
DEFAULT_BAND_PCT = 0.05
PUSHED_BAND_W = 1.0  # calibrations from HA's pushed values (~1 W steps)
PUSHED_BAND_PCT = 0.10
JUMP_MIN = 0.3  # W: a smaller change between settled readings has no direction
SPEED_DEADBAND_LIVE = 0.1
SPEED_DEADBAND_PUSHED = 0.4
TOP_OVERSHOOT_W, TOP_OVERSHOOT_PCT = 6.0, 0.40  # above the top speed's value: still the top speed
# Live calibration: after an own speed command, with the lamp off, the motor is
# watched until it has really settled (the top speed of the terrace fan kept
# creeping up for ~6 min) and that speed's value is corrected.
LEARN_MIN = 180.0  # s after the command before anything is learned
LEARN_MAX = 900.0  # s: stop watching after this
LEARN_HOLD = 120.0  # s the reading must stay flat
LEARN_SPREAD_W, LEARN_SPREAD_PCT = 0.3, 0.015  # allowed spread within LEARN_HOLD
LEARN_MAX_SLOPE = 0.1 / 60  # W/s (0.1 W per minute)
LEARN_STEP_W = 0.2  # learn again when the settled value moves this much
LEARN_MAX_CHANGE_W, LEARN_MAX_CHANGE_PCT = 1.0, 0.60  # larger corrections are refused
TREND_WINDOW = 60.0  # s of readings for the speed-estimate trend
TREND_SLOPE = 0.3 / 60  # W/s: faster than this = accelerating / decelerating


def read_watts(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state else None
    except ValueError:
        return None


def _slope(window: list[tuple[float, float]]) -> float:
    """Least-squares slope in W/s."""
    n = len(window)
    if n < 2:
        return 0.0
    mean_t = sum(t for t, _ in window) / n
    mean_v = sum(v for _, v in window) / n
    den = sum((t - mean_t) ** 2 for t, _ in window)
    return 0.0 if den == 0 else sum((t - mean_t) * (v - mean_v) for t, v in window) / den


async def async_wait_stable(
    meter: Meter,
    hold: float,
    min_wait: float,
    max_wait: float,
    tolerance_w: float,
    tolerance_pct: float = 0.05,
    max_slope: float | None = None,
    hold_fraction: float = 0.0,
    hold_max: float | None = None,
) -> tuple[float, float, bool]:
    """Wait at least ``min_wait`` s, then until the reading holds for ``hold`` s.

    Held means: spread within tolerance and, if ``max_slope`` is given, no
    trend steeper than that (W/s). With ``hold_fraction`` the hold grows with
    the time already waited (a slow motor must stay flat for longer). Returns (watts, seconds it took, settled).
    Elapsed time is counted in samples rather than read from a clock, which
    keeps it deterministic (and testable).
    """
    every = DIRECT_EVERY if meter.direct else SAMPLE_EVERY
    history: list[tuple[float, float]] = []
    value = None
    for step in range(int(max_wait / every)):
        elapsed = step * every
        value = await meter.async_read()
        if value is not None:
            span = max(hold, elapsed * hold_fraction)
            if hold_max is not None:
                span = min(span, max(hold, hold_max))
            history.append((elapsed, value))
            window = [(t, v) for t, v in history if t >= elapsed - span]
            values = [v for _, v in window]
            median = statistics.median(values)
            if (
                elapsed >= max(span, min_wait)
                and history[0][0] <= elapsed - span + every
                and max(values) - min(values) <= max(tolerance_w, abs(median) * tolerance_pct)
                and (max_slope is None or abs(_slope(window)) <= max_slope)
            ):
                return round(median, 1), round(elapsed, 1), True
        await asyncio.sleep(every)
    return round(value or 0.0, 1), round(max_wait, 1), False


async def async_wait_lamp(meter: Meter) -> tuple[float, float, bool]:
    return await async_wait_stable(meter, LIGHT_HOLD, LIGHT_MIN, LIGHT_MAX, LIGHT_TOLERANCE_W, 0.03)


async def async_wait_motor(meter: Meter) -> tuple[float, float, bool]:
    if meter.direct:
        return await async_wait_stable(
            meter, FAN_HOLD, FAN_MIN, FAN_MAX, FAN_TOLERANCE_W, FAN_TOLERANCE_PCT, FAN_MAX_SLOPE,
            FAN_HOLD_FRACTION, FAN_HOLD_MAX,
        )
    return await async_wait_stable(
        meter, SLOW_FAN_HOLD, SLOW_FAN_MIN, SLOW_FAN_MAX, SLOW_FAN_TOLERANCE_W
    )


@dataclass
class Candidate:
    speed: int  # 0 = fan stopped
    light: bool
    watts: float
    mode: int | None = None  # colour mode of the lamp, when on


def _modes(calibration: dict) -> list[float]:
    return list(calibration.get("light_modes") or [calibration["light"]])


def candidates(calibration: dict, only_mode: int | None = None) -> list[Candidate]:
    """Every (speed, light, colour mode) state with its expected draw.

    The lamp's draw adds to the motor's at once, so each speed with the light
    on is the motor alone plus that mode's lamp draw. ``light_modes`` is in
    the order of the mode names (the order the colour button cycles).
    """
    idle = calibration["idle"]
    modes = list(enumerate(_modes(calibration)))
    if only_mode is not None and 0 <= only_mode < len(modes):
        modes = [modes[only_mode]]
    result = [Candidate(0, False, idle)]
    result += [Candidate(0, True, watts, mode) for mode, watts in modes]
    for index, (off, _on) in enumerate(calibration["speeds"], start=1):
        result.append(Candidate(index, False, off))
        result += [
            Candidate(index, True, round(off + watts - idle, 1), mode) for mode, watts in modes
        ]
    return result


@dataclass
class Estimate:
    speed: int | None  # None: running, but the speed cannot be told apart
    fan_on: bool
    light: bool
    light_mode: int | None = None  # colour mode, when it can be told


def _classify(
    calibration: dict,
    watts: float,
    only_mode: int | None,
    direction: str | None = None,
    current: int | None = None,
    trust_current: bool = False,
) -> Estimate | None:
    ranked = sorted(candidates(calibration, only_mode), key=lambda c: abs(c.watts - watts))
    best = ranked[0]
    top = len(calibration["speeds"])
    overshoot = best.speed == top and watts > best.watts and watts - best.watts <= max(
        TOP_OVERSHOOT_W, (calibration["speeds"][-1][0] - calibration["idle"]) * TOP_OVERSHOOT_PCT
    )
    if abs(best.watts - watts) > max(3.0, best.watts * 0.10) and not overshoot:
        return None
    # Live-read tables resolve 0.1 W; pushed-only ones about 1 W.
    margin = LIVE_MARGIN_W if calibration.get("direct") else MIN_MARGIN_W
    close = [c for c in ranked if abs(c.watts - watts) < abs(best.watts - watts) + margin]
    if len({c.light for c in close}) > 1 or len({c.speed > 0 for c in close}) > 1:
        return None  # cannot even tell light or fan on/off apart
    modes = {c.mode for c in close}
    if best.speed == 0:
        speed: int | None = 0
    else:
        # With the light on, the lamp's draw is added; if the colour mode is
        # not known, every candidate mode must agree on the speed.
        light_modes = {c.mode for c in close if c.light} if best.light else set()
        offsets = [_lamp_offset(calibration, m) for m in light_modes] if best.light else [0.0]
        found = {
            speed_from_reading(calibration, watts, off, direction, current, trust_current)
            for off in offsets
        }
        speed = found.pop() if len(found) == 1 else None
    return Estimate(
        speed=speed,
        fan_on=best.speed > 0,
        light=best.light,
        light_mode=best.mode if best.light and len(modes) == 1 else None,
    )


def speed_band(calibration: dict, watts: float) -> float:
    """Margin around a calibrated draw: the larger of ``band_w`` and ``band_pct``."""
    live = bool(calibration.get("direct"))
    band_w = float(calibration.get("band_w", DEFAULT_BAND_W if live else PUSHED_BAND_W))
    band_pct = float(calibration.get("band_pct", DEFAULT_BAND_PCT if live else PUSHED_BAND_PCT))
    return max(band_w, abs(watts) * band_pct)


def speed_values(calibration: dict) -> list[tuple[float, float]]:
    """Motor-only draw of each speed as (reached going up, reached going down).

    A PWM fan settles higher when it slows down to a speed than when it
    speeds up to it (on a tested ceiling fan, speed 2 going down draws what
    speed 3 draws going up). Without a "down" value the "up" one is used.
    """
    downs = list(calibration.get("speeds_down") or [])
    result = []
    for index, row in enumerate(calibration["speeds"]):
        up = float(row[0])
        down = float(downs[index]) if index < len(downs) and downs[index] else up
        result.append((up, down))
    return result


def speed_ranges(calibration: dict, offset: float = 0.0) -> list[tuple[float, float]]:
    """Range of readings each speed may give: up..down plus the band either side."""
    ranges = []
    for up, down in speed_values(calibration):
        low, high = min(up, down), max(up, down)
        # The band scales with the motor's own draw, not with the lamp's on top.
        ranges.append((
            low - speed_band(calibration, low) + offset,
            high + speed_band(calibration, high) + offset,
        ))
    return ranges


def speed_from_reading(
    calibration: dict,
    watts: float,
    offset: float = 0.0,
    direction: str | None = None,
    current: int | None = None,
    trust_current: bool = False,
) -> int | None:
    """Speed for a settled reading (``offset``: lamp draw to add), or None if unclear.

    1. An own command is never overruled while the reading fits its range.
    2. After a clear change of draw, its direction picks the "up" or "down"
       values and the nearest one that fits wins.
    3. Otherwise a reading that fits a single range is that speed; when
       ranges overlap, the current speed is kept if it fits.
    """
    ranges = speed_ranges(calibration, offset)
    fits = [n for n, (low, high) in enumerate(ranges, start=1) if low <= watts <= high]
    if not fits and ranges:
        # Beyond the table: a motor that settled higher than calibrated is still
        # the top speed, one below the slowest is still the slowest.
        if watts > ranges[-1][1]:
            fits = [len(ranges)]
        elif watts < ranges[0][0]:
            fits = [1]
    if trust_current and current and current in fits:
        return current
    values = speed_values(calibration)
    deadband = SPEED_DEADBAND_LIVE if calibration.get("direct") else SPEED_DEADBAND_PUSHED
    if direction in ("up", "down"):
        table = [(v[0] if direction == "up" else v[1]) + offset for v in values]
        ranked = sorted(range(len(table)), key=lambda i: abs(table[i] - watts))
        best = ranked[0] + 1
        clear = len(ranked) < 2 or (
            abs(table[ranked[1]] - watts) - abs(table[ranked[0]] - watts) >= deadband
        )
        if best in fits and clear:
            return best
    if len(fits) == 1:
        return fits[0]
    if current and current in fits:
        return current
    return None


def learn_speed(
    calibration: dict, speed: int, direction: str, watts: float, when: str | None = None
) -> bool:
    """Correct one speed's value from a settled live reading (motor only, lamp off).

    Refused when the value would break the order of the values already
    learned live, when it matches another learned speed within its band
    (someone used the remote meanwhile), or when the change is implausibly
    large. Returns whether the
    table changed.
    """
    speeds = calibration["speeds"]
    count = len(speeds)
    if not 1 <= speed <= count or direction not in ("up", "down"):
        return False
    values = speed_values(calibration)
    col = 0 if direction == "up" else 1
    old = values[speed - 1][col]
    if abs(watts - old) > max(LEARN_MAX_CHANGE_W, abs(old) * LEARN_MAX_CHANGE_PCT):
        return False
    # Only values already confirmed live are trusted as neighbours: a wizard
    # value taken too early (the top speed of the terrace fan: 18.66 W, really
    # ~25 W) would otherwise block every speed below it.
    learned = calibration.get("learned") or {}

    def trusted(index: int, column: int) -> float | None:
        key = f"{index + 1}_{'up' if column == 0 else 'down'}"
        return values[index][column] if key in learned else None

    below = trusted(speed - 2, col) if speed > 1 else None
    above = trusted(speed, col) if speed < count else None
    if (below is not None and watts <= below) or (above is not None and watts >= above):
        return False
    # It reads as another speed already learned (the remote was used meanwhile).
    others = [
        x for i in range(count) if i != speed - 1
        for x in (trusted(i, 0), trusted(i, 1)) if x is not None
    ]
    if any(abs(watts - x) <= speed_band(calibration, x) for x in others):
        return False
    watts = round(watts, 2)
    downs = list(calibration.get("speeds_down") or [])
    downs += [None] * (count - len(downs))
    old_up = values[speed - 1][0]
    if direction == "up":
        speeds[speed - 1][0] = watts
        speeds[speed - 1][1] = round(watts + calibration["light"] - calibration["idle"], 2)
        # A "down" value never measured on its own (e.g. the top speed) follows.
        if downs[speed - 1] is None or abs(float(downs[speed - 1]) - old_up) < 0.005:
            downs[speed - 1] = watts
    else:
        downs[speed - 1] = watts
    calibration["speeds_down"] = downs
    calibration.setdefault("learned", {})[f"{speed}_{direction}"] = (
        when or dt_util.utcnow().isoformat()
    )
    return True


def speed_position(calibration: dict, motor: float, direction: str | None = None) -> float:
    """Fractional speed (0 = stopped … N = top) for a motor-only draw.

    Interpolated between the calibrated speeds, not in a straight line from
    the slowest to the fastest: a fan's draw grows much faster than its
    speed. Going up the "up" values are used, going down the "down" ones,
    otherwise their average. Clamped to 0…N.
    """
    values = speed_values(calibration)
    pick = {"up": lambda v: v[0], "down": lambda v: v[1]}.get(direction, lambda v: (v[0] + v[1]) / 2)
    points = [(0.0, float(calibration["idle"]))]
    for index, v in enumerate(values, start=1):
        points.append((float(index), max(pick(v), points[-1][1] + 0.01)))
    if motor <= points[0][1]:
        return 0.0
    for (s0, w0), (s1, w1) in zip(points, points[1:], strict=False):
        if motor <= w1:
            return s0 + (motor - w0) / (w1 - w0) * (s1 - s0)
    return float(len(values))


def _lamp_offset(calibration: dict, mode: int | None) -> float:
    modes = _modes(calibration)
    watts = modes[mode] if mode is not None and 0 <= mode < len(modes) else modes[0]
    return watts - calibration["idle"]


def classify(
    calibration: dict,
    watts: float,
    light_mode: int | None = None,
    direction: str | None = None,
    current: int | None = None,
    trust_current: bool = False,
) -> Estimate | None:
    """Most likely state for a settled reading, or None if nothing fits.

    With the remembered colour mode the lamp's draw is known exactly, which
    lets close speeds be told apart with the light on; if the reading does
    not fit that mode (the remote changed it), every mode is considered.
    """
    extra = (direction, current, trust_current)
    if light_mode is not None:
        estimate = _classify(calibration, watts, light_mode, *extra)
        if estimate is not None:
            return estimate
    return _classify(calibration, watts, None, *extra)


async def _measure_lamp(
    meter: Meter,
    set_light: Callable[[bool], Any],
    next_color: Callable[[], Any] | None,
    colors: int,
    first_mode: int,
    result: dict,
) -> AsyncIterator[dict]:
    """Idle, then the lamp in each colour mode, with the fan stopped (seconds, not minutes)."""
    yield {"stage": "meter", "direct": meter.direct}
    idle, _, _ = await async_wait_lamp(meter)
    yield {"stage": "measured", "what": "idle", "watts": idle}

    await set_light(True)
    light, _, _ = await async_wait_lamp(meter)
    yield {"stage": "measured", "what": "light", "watts": light, "mode": first_mode + 1}
    measured = [light]
    if next_color is not None and colors > 1:
        for step in range(1, colors):
            await next_color()
            watts, _, _ = await async_wait_lamp(meter)
            measured.append(watts)
            yield {"stage": "measured", "what": "light", "watts": watts,
                   "mode": (first_mode + step) % colors + 1}
        await next_color()  # back to the mode it started in
        await async_wait_lamp(meter)
    await set_light(False)
    await async_wait_lamp(meter)
    # Stored in the order of the mode names, whatever mode the lamp was in.
    n = len(measured)
    result.update(idle=idle, light=light, light_modes=[measured[(i - first_mode) % n] for i in range(n)])


async def async_calibrate_light(
    meter: Meter,
    set_light: Callable[[bool], Any],
    next_color: Callable[[], Any] | None = None,
    colors: int = 1,
    first_mode: int = 0,
) -> AsyncIterator[dict]:
    """Quick calibration: only idle and the lamp, with the fan stopped (1–2 minutes).

    Enough to tell the lamp from the motor by its sudden jumps (see
    ``lamp_from_jump``) without measuring every speed.
    """
    result: dict = {}
    async for event in _measure_lamp(meter, set_light, next_color, colors, first_mode, result):
        yield event
    yield {"stage": "done", "calibration": {
        **result, "direct": meter.direct, "measured": dt_util.utcnow().isoformat(),
    }}


LAMP_JUMP_PCT = 0.35  # a jump within ±35 % (or ±3 W) of the lamp's draw is the lamp
LAMP_JUMP_MIN_W = 3.0


def lamp_from_jump(calibration: dict, before: float, after: float) -> bool | None:
    """The lamp switching, told from a sudden change between two readings.

    The lamp changes the draw at once by about its own watts; a motor ramps.
    Returns True (lamp on), False (lamp off) or None (not the lamp).
    """
    lamp = calibration["light"] - calibration["idle"]
    if lamp <= 0:
        return None
    jump = after - before
    if abs(abs(jump) - lamp) <= max(LAMP_JUMP_MIN_W, lamp * LAMP_JUMP_PCT):
        return jump > 0
    return None


def lamp_from_level(calibration: dict, watts: float) -> bool:
    """With the fan stopped, the lamp is on when the draw is past half its watts."""
    lamp = calibration["light"] - calibration["idle"]
    return watts - calibration["idle"] > lamp / 2


async def async_calibrate(
    meter: Meter,
    speeds: int,
    send_speed: Callable[[int], Any],
    send_fan_off: Callable[[], Any],
    set_light: Callable[[bool], Any],
    next_color: Callable[[], Any] | None = None,
    colors: int = 1,
    first_mode: int = 0,
) -> AsyncIterator[dict]:
    """Measure idle, the lamp (per colour mode) and every speed.

    The lamp's draw adds to the motor's at once, so it is measured once with
    the fan stopped and added to each speed, instead of switching the light
    on and off at every speed. Speeds are measured going up without stopping
    the fan in between; each one waits for the motor to settle.

    The fan and the light must be off when it starts; the caller checks it.
    Yields progress events and finally ``{"stage": "done", "calibration": ...}``.
    """
    lamp_result: dict = {}
    async for event in _measure_lamp(meter, set_light, next_color, colors, first_mode, lamp_result):
        yield event
    idle, light, modes = lamp_result["idle"], lamp_result["light"], lamp_result["light_modes"]
    lamp = round(light - idle, 1)

    table: list[list[float]] = []
    settle_times: list[float] = []
    for speed in range(1, speeds + 1):
        yield {"stage": "speed", "speed": speed}
        await send_speed(speed)
        off, took, settled = await async_wait_motor(meter)
        settle_times.append(took)
        table.append([off, round(off + lamp, 1)])
        yield {"stage": "measured", "what": "speed", "speed": speed, "light": False,
               "watts": off, "seconds": took, "settled": settled}

    # Going down: a PWM motor settles higher when it slows to a speed.
    downs: list[float | None] = [None] * speeds
    if speeds:
        downs[-1] = table[-1][0]
    for speed in range(speeds - 1, 0, -1):
        yield {"stage": "speed", "speed": speed, "direction": "down"}
        await send_speed(speed)
        down, took, settled = await async_wait_motor(meter)
        settle_times.append(took)
        downs[speed - 1] = down
        yield {"stage": "measured", "what": "speed", "speed": speed, "light": False,
               "direction": "down", "watts": down, "seconds": took, "settled": settled}

    await send_fan_off()
    calibration = {
        "idle": idle,
        "light": light,
        "speeds": table,
        "speeds_down": downs,
        "light_modes": modes,
        "settle": round(max(settle_times, default=FAN_MIN), 1),
        "direct": meter.direct,
        "measured": dt_util.utcnow().isoformat(),
    }
    yield {"stage": "done", "calibration": calibration}


def colour_steps(calibration: dict) -> list[float]:
    """Jump in draw caused by a colour press from each mode to the next.

    Lamps drift with temperature (about 2 W on a tested 36 W lamp), which moves
    every mode together; the jump between modes stays put, so it identifies
    the press much better than the absolute value.
    """
    modes = _modes(calibration)
    n = len(modes)
    return [round(modes[(i + 1) % n] - modes[i], 2) for i in range(n)] if n > 1 else []


def colour_from_jump(calibration: dict, jump: float) -> int | None:
    """Mode the lamp moved to, if ``jump`` matches exactly one visible colour press."""
    steps = colour_steps(calibration)
    if abs(jump) < COLOUR_STEP_MIN:
        return None
    matches = [i for i, step in enumerate(steps)
               if abs(step) >= COLOUR_STEP_MIN and abs(step - jump) <= COLOUR_STEP_TOLERANCE]
    if len(matches) != 1:
        return None
    return (matches[0] + 1) % len(steps)


class PowerAligner:
    """Watches the meter and corrects the fan and light states, in two steps.

    1. ``QUICK_DELAY`` s after the reading changes: the lamp adds its full
       draw at once, so light on/off and fan running/stopped can be told
       even while the motor is still speeding up. Speed is left alone.
    2. Once the motor has settled: the speed as well, when the table can tell
       it apart. Live meters are sampled until flat; pushed-only meters count
       as settled after ``SLOW_SETTLE`` s without a new report.

    With a live meter it also learns: after an own speed command (see
    ``command_sent``) with the lamp off, the reading is watched for up to
    ``LEARN_MAX`` s and, once really flat, that speed's value is corrected
    through ``learn`` (see ``learn_speed``).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        meter: Meter,
        calibration: dict,
        apply: Callable[[Estimate], None],
        light_mode: Callable[[], int | None] = lambda: None,
        colour_changed: Callable[[int], None] = lambda mode: None,
        speed_state: Callable[[], tuple[int | None, bool]] = lambda: (None, False),
        lamp_on: Callable[[], bool | None] = lambda: None,
        learn: Callable[[int, str, float], None] | None = None,
    ) -> None:
        self.hass = hass
        self.meter = meter
        self.calibration = calibration
        self._apply = apply
        self._light_mode = light_mode
        self._colour_changed = colour_changed
        self._speed_state = speed_state  # (current speed, set by our own command)
        # Last settled reading: (watts, fan on, fan settled, light on).
        self._previous: tuple[float, bool, bool, bool] | None = None
        self._cancel_timers: list[Callable[[], None]] = []
        self._watch: asyncio.Task | None = None
        self._monitor: asyncio.Task | None = None
        self._decided: float | None = None  # last settled reading acted upon
        self._flat: float | None = None  # current settled level
        self._pending_colour: tuple[int, float, int] | None = None  # (mode, level, confirmations)
        self._flat_before: float | None = None  # settled level before a sudden jump
        self._lamp_on = lamp_on
        self._learn = learn
        self._session: dict | None = None  # live calibration after an own command

    @callback
    def command_sent(self, speed: int, previous: int) -> None:
        """An own speed command (0 = off): start watching to learn its real draw."""
        self._session = None
        if not self.meter.direct or self._learn is None or not speed or speed == previous:
            return
        self._session = {
            "speed": speed,
            "direction": "up" if speed > previous else "down",
            "start": self.hass.loop.time(),
            "window": [],
            "learned": None,
        }
        _LOGGER.debug("%s: watching speed %s (%s) to learn its draw",
                      self.meter.entity_id, speed, self._session["direction"])

    def _learn_tick(self, now: float, watts: float) -> None:
        session = self._session
        if session is None:
            return
        # Anything else happening (lamp on, speed corrected, fan off) ends it.
        if (
            self._speed_state() != (session["speed"], True)
            or self._lamp_on() is not False
            or now - session["start"] > LEARN_MAX
        ):
            self._session = None
            return
        window = session["window"]
        window.append((now, watts))
        window[:] = [(t, v) for t, v in window if t >= now - LEARN_HOLD]
        if now - session["start"] < LEARN_MIN or window[0][0] > now - LEARN_HOLD + MONITOR_EVERY:
            return
        values = [v for _, v in window]
        median = statistics.median(values)
        if max(values) - min(values) > max(LEARN_SPREAD_W, abs(median) * LEARN_SPREAD_PCT):
            return
        if abs(_slope(window)) > LEARN_MAX_SLOPE:
            return
        if session["learned"] is not None and abs(median - session["learned"]) < LEARN_STEP_W:
            return
        session["learned"] = median
        self._learn(session["speed"], session["direction"], round(median, 2))

    @callback
    def async_start(self) -> Callable[[], None]:
        unsub = async_track_state_change_event(self.hass, [self.meter.entity_id], self._changed)
        # Check once at start too: the restored state may no longer be true.
        self._cancel_timers.append(async_call_later(self.hass, QUICK_DELAY, self._quick))
        if self.meter.direct:
            # A Shelly pushes only big changes: watch live, so slow drifts to a
            # new speed (e.g. set with the original remote) are noticed too.
            self._monitor = self.hass.async_create_background_task(
                self._async_monitor(), f"rf_devices monitor {self.meter.entity_id}"
            )

        def stop() -> None:
            unsub()
            self._cancel()
            if self._monitor and not self._monitor.done():
                self._monitor.cancel()

        return stop

    def _cancel(self) -> None:
        for cancel in self._cancel_timers:
            cancel()
        self._cancel_timers = []
        if self._watch and not self._watch.done():
            self._watch.cancel()
        self._watch = None

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        self._cancel()
        self._cancel_timers.append(async_call_later(self.hass, QUICK_DELAY, self._quick))
        if not self.meter.direct:
            self._cancel_timers.append(async_call_later(self.hass, SLOW_SETTLE, self._slow))

    @callback
    def _quick(self, _now) -> None:
        self._watch = self.hass.async_create_background_task(self._async_follow(), "rf_devices aligner")

    @callback
    def _slow(self, _now) -> None:
        self.hass.async_create_background_task(self._async_final(), "rf_devices aligner")

    async def _async_follow(self) -> None:
        watts = await self.meter.async_read()
        if watts is None:
            return
        estimate = classify(self.calibration, watts, self._light_mode())
        _LOGGER.debug("Meter %s quick check %s W -> %s", self.meter.entity_id, watts, estimate)
        if estimate is not None:
            self._apply(Estimate(speed=None, fan_on=estimate.fan_on, light=estimate.light))
            if not estimate.fan_on:  # lamp alone: its reading is final at once
                self._colour_jump(watts, estimate, settled=True)

    async def _async_monitor(self) -> None:
        """Read live every few seconds; decide each time the reading settles anew."""
        window: list[tuple[float, float]] = []
        while True:
            watts = await self.meter.async_read()
            now = self.hass.loop.time()
            if watts is not None and self._abrupt_colour(watts):
                window = []  # a new level: stability starts again
            if watts is not None:
                self._learn_tick(now, watts)
                window.append((now, watts))
                window = [(t, v) for t, v in window if t >= now - ALIGN_HOLD]
                values = [v for _, v in window]
                median = statistics.median(values)
                settled = (
                    window[0][0] <= now - ALIGN_HOLD + MONITOR_EVERY
                    and max(values) - min(values) <= max(FAN_TOLERANCE_W, abs(median) * FAN_TOLERANCE_PCT)
                    and abs(_slope(window)) <= FAN_MAX_SLOPE
                )
                self._flat = median if settled else None
                if settled and (self._decided is None or abs(median - self._decided) >= REDECIDE_W):
                    direction = None
                    colour = False
                    if self._decided is not None and abs(median - self._decided) >= JUMP_MIN:
                        # The lamp changed colour (not the speed) if the change is exactly that.
                        colour = self._colour_explains(self._decided, median)
                        direction = None if colour else ("up" if median > self._decided else "down")
                    self._decided = median
                    if colour:
                        self._previous = None
                    else:
                        await self._async_final(round(median, 2), direction)
            await asyncio.sleep(MONITOR_EVERY)

    def _colour_explains(self, before: float, after: float) -> bool:
        """Between two settled levels: is the change exactly a colour press, lamp on?"""
        estimate = classify(self.calibration, before, self._light_mode())
        if estimate is None or not estimate.light:
            return False
        mode = colour_from_jump(self.calibration, after - before)
        if mode is None:
            return False
        _LOGGER.info("%s: %.2f W between settled readings -> colour mode %s",
                     self.meter.entity_id, after - before, mode + 1)
        self._colour_changed(mode)
        return True

    def _abrupt_colour(self, watts: float) -> bool:
        """A colour press moves the lamp's draw at once; a speed change ramps for minutes.

        From a settled level, a jump that matches a colour press and holds for
        the next readings is taken as a colour change: the mode is updated and
        the speed is left alone (the reference level moves with the jump).
        """
        if self._pending_colour is not None:
            mode, level, seen = self._pending_colour
            if abs(watts - level) > COLOUR_HOLD_W:
                self._pending_colour = None  # it kept moving: the motor, not the lamp
                return False
            seen += 1
            if seen < COLOUR_CONFIRM:
                self._pending_colour = (mode, level, seen)
                return False
            self._pending_colour = None
            jump = level - (self._flat_before or level)
            if self._decided is not None:
                self._decided += jump
            if self._previous is not None:
                self._previous = (self._previous[0] + jump, *self._previous[1:])
            _LOGGER.info("%s: sudden %.2f W with the lamp on -> colour mode %s",
                         self.meter.entity_id, jump, mode + 1)
            self._colour_changed(mode)
            return True
        if self._flat is None or abs(watts - self._flat) < COLOUR_STEP_MIN:
            return False
        estimate = classify(self.calibration, self._flat, self._light_mode())
        if estimate is None or not estimate.light:
            return False
        mode = colour_from_jump(self.calibration, watts - self._flat)
        if mode is not None:
            self._flat_before = self._flat
            self._pending_colour = (mode, watts, 0)
        return False

    async def _async_final(self, watts: float | None = None, direction: str | None = None) -> None:
        if watts is None:
            watts = await self.meter.async_read()
        if watts is None:
            return
        current, own = self._speed_state()
        estimate = classify(self.calibration, watts, self._light_mode(), direction, current, own)
        _LOGGER.debug("Meter %s settled at %s W -> %s", self.meter.entity_id, watts, estimate)
        if estimate is not None:
            self._apply(Estimate(estimate.speed, estimate.fan_on, estimate.light))
            self._colour_jump(watts, estimate, settled=True)

    def _colour_jump(self, watts: float, estimate: Estimate, settled: bool) -> None:
        """Recognise a colour press (e.g. from the original remote) by the jump it causes.

        Only between two settled readings with the lamp on and the fan in the
        same state, so a motor ramping or the lamp switching is never read as
        a colour change.
        """
        previous, self._previous = self._previous, (watts, estimate.fan_on, settled, estimate.light)
        if previous is None or not (estimate.light and previous[3]):
            return
        if previous[1] != estimate.fan_on or (estimate.fan_on and not (settled and previous[2])):
            return
        mode = colour_from_jump(self.calibration, watts - previous[0])
        if mode is not None:
            _LOGGER.info("%s: jump of %.2f W -> colour mode %s", self.meter.entity_id, watts - previous[0], mode + 1)
            self._colour_changed(mode)

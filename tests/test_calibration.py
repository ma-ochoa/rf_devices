"""Power calibration wizard and aligner."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_devices import calibration as cal
from custom_components.rf_devices import codec
from custom_components.rf_devices.const import DOMAIN

from .helpers import capture

TX = "remote.rm_pro"
METER = "sensor.fan_power"
CODES = {k: codec.clean(capture(format(i + 9, "024b"))) for i, k in enumerate(
    ["power", "s1", "s2", "s3", "light", "color"]
)}
# What the simulated fan draws: idle, lamp, and per speed (motor only).
LAMP_W, SPEED_W = 38.7, {1: 9.0, 2: 16.0, 3: 24.0}
COLOR_W = [38.7, 20.0, 19.0]  # both LED rows, warm only, cold only
TABLE = {"idle": 0.0, "light": 38.7, "speeds": [[9, 47.7], [16, 54.7], [24, 62.7]]}


def test_classify_light_colour_modes() -> None:
    # Warm LEDs 20 W, cold 19 W, both 38.7 W; speeds measured with both.
    table = {**TABLE, "light_modes": [38.7, 20.0, 19.0]}
    e = cal.classify(table, 20.3)
    assert (e.fan_on, e.light) == (False, True)
    e = cal.classify(table, 16 + 20.0)  # speed 2, warm only
    assert (e.fan_on, e.light) == (True, True)
    assert e.speed == 2


def test_known_colour_mode_tells_speeds_apart_with_light() -> None:
    real = {"idle": 0.0, "light": 38.0, "direct": True,
            "speeds": [[3.8, 41.8], [5.0, 43.0], [6.7, 44.7]],
            "light_modes": [38.0, 36.3, 37.8]}
    assert cal.classify(real, 41.45).speed is None  # 1 + mode 3 (41.6) or 2 + mode 2 (41.3)?
    e = cal.classify(real, 41.8, light_mode=0)
    assert (e.speed, e.light, e.light_mode) == (1, True, 0)
    e = cal.classify(real, 36.3)  # lamp alone in its lowest-draw mode
    assert (e.fan_on, e.light, e.light_mode) == (False, True, 1)


def test_classify() -> None:
    e = cal.classify(TABLE, 48.5)
    assert (e.speed, e.fan_on, e.light) == (1, True, True)
    e = cal.classify(TABLE, 0.4)
    assert (e.speed, e.fan_on, e.light) == (0, False, False)
    assert cal.classify(TABLE, 33) is None  # nothing near
    close = {"idle": 0, "light": 38.7, "speeds": [[22, 60.7], [23, 61.7]]}
    e = cal.classify(close, 22.4)
    assert (e.speed, e.fan_on, e.light) == (None, True, False)  # speed undecided


class FakeFan:
    """Reacts to RF codes like the real fan and updates the meter."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass, self.speed, self.last, self.light, self.color = hass, 0, 1, False, 0

    def publish(self) -> None:
        watts = (COLOR_W[self.color] if self.light else 0) + SPEED_W.get(self.speed, 0)
        self.hass.states.async_set(METER, str(watts), {"unit_of_measurement": "W"})

    async def handle(self, call: ServiceCall) -> None:
        code = call.data["command"][0].removeprefix("b64:")
        role = next(k for k, v in CODES.items() if v == code)
        if role == "power":
            self.speed = 0 if self.speed else self.last
        elif role == "light":
            self.light = not self.light
        elif role == "color":
            self.color = (self.color + 1) % len(COLOR_W)
        else:
            self.speed = self.last = int(role[1])
            # Like the real motor: a start-up peak, then a slow drift down.
            self.hass.async_create_task(self._ramp())
            return
        self.publish()

    async def _ramp(self) -> None:
        final = SPEED_W[self.speed]
        lamp = COLOR_W[self.color] if self.light else 0
        for watts in (final * 2.4, final * 2.0, final * 1.6, final * 1.3, final * 1.1):
            self.hass.states.async_set(METER, str(round(lamp + watts, 1)), {"unit_of_measurement": "W"})
            await asyncio.sleep(0.05)
        self.publish()


@pytest.fixture
async def fan(hass: HomeAssistant, hass_storage, monkeypatch):
    for name, value in (("SAMPLE_EVERY", 0.01), ("LIGHT_HOLD", 0.05), ("LIGHT_MIN", 0.03),
                        ("LIGHT_MAX", 2), ("FAN_HOLD", 0.15), ("FAN_MIN", 0.4), ("FAN_MAX", 3),
                        ("SLOW_FAN_HOLD", 0.15), ("SLOW_FAN_MIN", 0.4), ("SLOW_FAN_MAX", 3),
                        ("QUICK_DELAY", 0.05), ("SLOW_SETTLE", 0.15)):
        monkeypatch.setattr(cal, name, value)
    device = {
        "id": "terr", "name": "Terraza", "type": "fan",
        "options": {"speeds": 3, "power": "toggle", "light": "toggle", "light_state_entity": METER,
                    "light_color": True, "light_colors": 3,
                    "power_entity": "switch.relay"},
        "commands": {"power": {"code": CODES["power"]}, "speed_1": {"code": CODES["s1"]},
                     "speed_2": {"code": CODES["s2"]}, "speed_3": {"code": CODES["s3"]},
                     "light_toggle": {"code": CODES["light"]}, "light_color": {"code": CODES["color"]}},
    }
    hass_storage[DOMAIN] = {"version": 1, "minor_version": 1, "key": DOMAIN,
                            "data": {"devices": {"terr": device}, "frequencies": {}}}
    hass.states.async_set(TX, "on")
    hass.states.async_set("switch.relay", "on")
    sim = FakeFan(hass)
    sim.publish()
    hass.services.async_register("remote", "send_command", sim.handle)
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, sim=sim)


async def _run(ws, device_id="terr") -> list[dict]:
    await ws.send_json_auto_id({"type": "rf_devices/calibrate", "device_id": device_id})
    first = await ws.receive_json()
    if not first["success"]:
        return [first]
    events = []
    while True:
        ev = (await ws.receive_json(timeout=20))["event"]
        events.append(ev)
        if ev["stage"] in ("done", "error"):
            return events


async def test_calibration_measures_every_state(hass: HomeAssistant, fan, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    events = await _run(ws)
    done = events[-1]
    assert done["stage"] == "done", events
    c = done["calibration"]
    assert c["idle"] == 0.0 and c["light"] == 38.7
    assert c["speeds"] == [[9.0, 47.7], [16.0, 54.7], [24.0, 62.7]]
    assert c["light_modes"] == [38.7, 20.0, 19.0]
    assert fan.sim.color == 0  # back to the colour mode it started in
    # Everything is left off.
    assert fan.sim.speed == 0 and not fan.sim.light
    assert hass.states.get("fan.terraza").state == "off"


async def test_calibration_refused_when_not_idle(hass: HomeAssistant, fan, hass_ws_client) -> None:
    fan.sim.light = True
    fan.sim.publish()
    ws = await hass_ws_client(hass)
    [msg] = await _run(ws)
    assert not msg["success"]
    assert "Switch the fan and its light off" in msg["error"]["message"]


async def test_aligner_follows_the_original_remote(hass: HomeAssistant, fan, hass_ws_client) -> None:
    hub = fan.entry.runtime_data
    device = dict(hub.store.devices["terr"])
    device["options"] = {**device["options"], "calibration": TABLE}
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()

    # Someone uses the original remote: speed 2 and the lamp on.
    fan.sim.speed, fan.sim.light = 2, True
    fan.sim.publish()
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()
    state = hass.states.get("fan.terraza")
    assert state.state == "on"
    assert state.attributes["percentage"] == 66  # speed 2 of 3
    assert hass.states.get("light.terraza_light").state == "on"
    assert hass.states.get("sensor.terraza_detected_state").state == "fan_light"

    # And switches everything off.
    fan.sim.speed, fan.sim.light = 0, False
    fan.sim.publish()
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()
    assert hass.states.get("fan.terraza").state == "off"
    assert hass.states.get("light.terraza_light").state == "off"


async def test_light_follows_even_if_the_meter_keeps_changing(
    hass: HomeAssistant, fan, hass_ws_client
) -> None:
    """Toggling the lamp every few seconds must not starve the aligner."""
    hub = fan.entry.runtime_data
    device = dict(hub.store.devices["terr"])
    device["options"] = {**device["options"], "calibration": TABLE}
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()

    fan.sim.speed, fan.sim.last = 1, 1
    for light in (True, False, True):
        fan.sim.light = light
        fan.sim.publish()
        await asyncio.sleep(0.08)  # longer than QUICK_DELAY, shorter than SLOW_SETTLE
        await hass.async_block_till_done()
        assert hass.states.get("light.terraza_light").state == ("on" if light else "off")
        assert hass.states.get("fan.terraza").state == "on"


async def test_aligner_checks_the_restored_state_at_start(
    hass: HomeAssistant, fan, hass_ws_client
) -> None:
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": "fan.terraza", "percentage": 33}, blocking=True
    )
    fan.sim.speed = 0  # stopped with the original remote while HA was down
    fan.sim.publish()
    hub = fan.entry.runtime_data
    device = dict(hub.store.devices["terr"])
    device["options"] = {**device["options"], "calibration": TABLE}
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert hass.states.get("fan.terraza").state == "off"


async def test_colour_select_sends_the_right_number_of_presses(hass: HomeAssistant, fan) -> None:
    hub = fan.entry.runtime_data
    device = dict(hub.store.devices["terr"])
    device["options"] = {**device["options"], "light_color_names": ["Frío", "Neutro", "Cálido"],
                         "light_color_power_up": "fixed"}
    await hub.store.async_upsert(device)
    await hass.config_entries.async_reload(fan.entry.entry_id)
    await hass.async_block_till_done()
    select = "select.terraza_colour_temperature"
    assert hass.states.get(select).state == "Frío"
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    with pytest.raises(HomeAssistantError):  # the light is off
        await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "Cálido"}, blocking=True)
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.terraza_light"}, blocking=True)
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "Cálido"}, blocking=True)
    assert fan.sim.color == 2  # two presses: Frío -> Neutro -> Cálido
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "Frío"}, blocking=True)
    assert fan.sim.color == 0  # one press wraps round
    assert hass.states.get(select).state == "Frío"
    # The colour button keeps the remembered mode in step as well.
    await hass.services.async_call("button", "press", {"entity_id": "button.terraza_light_colour"}, blocking=True)
    assert hass.states.get(select).state == "Neutro"
    # Re-align without sending (after using the original remote).
    sent_before = fan.sim.color
    await hass.services.async_call(DOMAIN, "set_color_mode", {"entity_id": select, "option": "Cálido"}, blocking=True)
    assert hass.states.get(select).state == "Cálido"
    assert fan.sim.color == sent_before  # nothing transmitted
    await hass.services.async_call(DOMAIN, "set_color_mode", {"entity_id": select, "option": "Neutro"}, blocking=True)
    # Power cut and back: the lamp starts in its power-up mode.
    hass.states.async_set("switch.relay", "off")
    hass.states.async_set("switch.relay", "on")
    await hass.async_block_till_done()
    assert hass.states.get(select).state == "Frío"


def test_colour_from_jump_with_real_numbers() -> None:
    # Terrace lamp, 27/09: modes in button order 35.79 / 35.72 / 34.31 W.
    table = {"idle": 0.0, "light": 35.79, "speeds": [[3.5, 39.3]], "light_modes": [35.79, 35.72, 34.31]}
    assert cal.colour_steps(table) == [-0.07, -1.41, 1.48]
    assert cal.colour_from_jump(table, -1.38) == 2  # 2 -> 3
    assert cal.colour_from_jump(table, 1.45) == 0  # 3 -> 1
    assert cal.colour_from_jump(table, -0.1) is None  # 1 -> 2 cannot be seen
    # A 2 W thermal drift moves every mode together: jumps are unchanged.
    drifted = {**table, "light_modes": [37.79, 37.72, 36.31]}
    assert cal.colour_from_jump(drifted, -1.41) == 2


async def test_aligner_follows_colour_presses_from_the_remote(hass: HomeAssistant, fan, hass_ws_client) -> None:
    hub = fan.entry.runtime_data
    device = dict(hub.store.devices["terr"])
    device["options"] = {**device["options"], "light_color_names": ["Frío", "Neutro", "Cálido"],
                         "calibration": {**TABLE, "light_modes": [38.7, 20.0, 19.0]}}
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()
    select = "select.terraza_colour_temperature"
    fan.sim.light = True  # lamp on, fan off, mode Frío (38.7 W)
    fan.sim.publish()
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    # Original remote: Frío -> Neutro (38.7 -> 20.0 W, a -18.7 W jump).
    fan.sim.color = 1
    fan.sim.publish()
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert hass.states.get(select).state == "Neutro"




# Terrace fan, 28/09/2026: settled draw going up and going down (W).
REAL = {"idle": 0.0, "light": 36.0, "direct": True,
        "speeds": [[3.59, 39.6], [4.75, 40.8], [6.43, 42.4], [9.82, 45.8], [13.73, 49.7], [18.66, 54.7]],
        "speeds_down": [3.56, 6.01, 8.77, 12.21, 14.78, 18.66]}


def test_ranges_from_up_and_down() -> None:
    ranges = cal.speed_ranges(REAL)
    assert ranges[1] == pytest.approx((4.45, 6.31), abs=0.01)  # speed 2: 4.75 up .. 6.01 down
    assert ranges[3] == pytest.approx((9.33, 12.82), abs=0.01)


@pytest.mark.parametrize(
    ("watts", "direction", "current", "own", "expected"),
    [
        (6.01, None, 2, True, 2),  # the 28/09 mistake: own "speed 2" going down is kept
        (6.18, None, 3, True, 3),  # 6.18 fits speeds 2 and 3: own command 3 kept
        (6.01, "down", 3, False, 2),  # remote 3 -> 2: dropped to the "down" value of 2
        (6.45, "up", 2, False, 3),  # remote 2 -> 3
        (12.21, "down", 5, False, 4),
        (8.77, None, None, False, 3),  # fits only speed 3
        (7.6, None, 2, True, 3),  # outside own speed's range: corrected
        (16.5, None, 5, True, None),  # between 5 and 6: undecided
    ],
)
def test_speed_rule_with_real_data(watts, direction, current, own, expected) -> None:
    assert cal.speed_from_reading(REAL, watts, 0.0, direction, current, own) == expected


def test_speed_rule_with_the_light_on() -> None:
    # Lamp 36 W on top: speed 2 going down reads 42.0 W.
    e = cal.classify(REAL, 42.0, light_mode=0, current=2, trust_current=True)
    assert (e.fan_on, e.light, e.speed) == (True, True, 2)


async def test_monitor_follows_a_remote_change_down(hass: HomeAssistant, monkeypatch) -> None:
    """Live meter, no pushes: speed 3 settled, then the remote sets 2 (drifts down)."""
    monkeypatch.setattr(cal, "MONITOR_EVERY", 0.01)
    monkeypatch.setattr(cal, "ALIGN_HOLD", 0.1)
    readings = iter([6.4] * 25 + [6.3, 6.2, 6.1] + [6.0] * 40)

    class LiveMeter:
        direct = True
        entity_id = "sensor.fan_power"

        async def async_read(self):
            return next(readings, 6.0)

    decided: list = []
    state = {"speed": 3, "own": False}
    aligner = cal.PowerAligner(hass, LiveMeter(), REAL, decided.append,
                               speed_state=lambda: (state["speed"], state["own"]))
    stop = aligner.async_start()
    await asyncio.sleep(0.8)
    stop()
    speeds = [e.speed for e in decided if e.speed is not None]
    assert speeds[0] == 3 and speeds[-1] == 2


async def test_colour_press_with_the_fan_running_is_not_a_speed_change(hass: HomeAssistant, monkeypatch) -> None:
    """Fan settled at speed 3 with the lamp in Frío; the remote changes colour."""
    monkeypatch.setattr(cal, "MONITOR_EVERY", 0.01)
    monkeypatch.setattr(cal, "ALIGN_HOLD", 0.1)
    table = {**REAL, "light": 34.31, "light_modes": [34.31, 35.79, 35.72]}  # Neutro, Frío, Cálido
    level = 6.43 + 35.79
    # Settled, then Frío -> Cálido is invisible, Cálido -> Neutro is a sudden -1.41 W.
    readings = iter([level] * 30 + [level - 1.41] * 40)

    class LiveMeter:
        direct = True
        entity_id = "sensor.fan_power"

        async def async_read(self):
            return next(readings, level - 1.41)

    decided, colours = [], []
    state = {"mode": 1}
    aligner = cal.PowerAligner(hass, LiveMeter(), table, decided.append,
                               light_mode=lambda: state["mode"],
                               colour_changed=lambda m: (colours.append(m), state.update(mode=m)),
                               speed_state=lambda: (3, True))
    stop = aligner.async_start()
    await asyncio.sleep(0.8)
    stop()
    assert colours and colours[-1] == 0  # Neutro
    assert {e.speed for e in decided if e.speed is not None} == {3}  # speed never touched


def test_above_the_top_speed_is_still_the_top_speed() -> None:
    # 28/09: speed 6 kept creeping up for ~6 min, to 22.8 W (table: 18.66).
    assert cal.speed_from_reading(REAL, 22.8, 0.0, "up", 4, False) == 6
    e = cal.classify(REAL, 22.8, current=4)
    assert (e.fan_on, e.light, e.speed) == (True, False, 6)
    e = cal.classify(REAL, 22.8 + 36.0, light_mode=0, current=4)
    assert (e.fan_on, e.light, e.speed) == (True, True, 6)
    assert cal.classify(REAL, 30.0) is None  # far above: not a fan state


def test_learn_speed() -> None:
    import copy

    table = copy.deepcopy(REAL)
    assert cal.learn_speed(table, 6, "up", 23.5, "t")
    assert table["speeds"][5] == [23.5, 59.5]
    assert table["speeds_down"][5] == 23.5  # never measured on its own: follows
    assert table["learned"] == {"6_up": "t"}
    assert cal.learn_speed(table, 5, "down", 15.3)
    assert table["speeds_down"][4] == 15.3 and table["speeds"][4][0] == 13.73
    # Refused against learned values: reads as speed 5 down, order broken.
    assert not cal.learn_speed(table, 6, "up", 15.4)
    assert not cal.learn_speed(table, 4, "down", 15.4)
    # Too big a change, or no such speed.
    assert not cal.learn_speed(table, 1, "up", 0.5)
    assert not cal.learn_speed(table, 7, "up", 30.0)


def test_learn_speed_is_not_blocked_by_a_wrong_wizard_value() -> None:
    # 28/09: speed 5 going down settled at 19.6 W, above the wizard's 18.66 W
    # for speed 6 (really ~24.8 W). The unconfirmed 6 must not block it.
    import copy

    table = copy.deepcopy(REAL)
    assert cal.learn_speed(table, 5, "down", 19.6)
    assert table["speeds_down"][4] == 19.6
    assert cal.learn_speed(table, 4, "down", 15.2)  # below 5's learned value: fine
    assert not cal.learn_speed(table, 3, "down", 14.9)  # reads as the learned 4
    assert cal.learn_speed(table, 3, "down", 12.1)  # the whole table was ~30 % low


@pytest.mark.parametrize(
    ("motor", "direction", "expected"),
    [(0.0, None, 0.0), (3.59, "up", 1.0), (9.82, "up", 4.0), (16.195, "up", 5.5),
     (12.21, "down", 4.0), (30.0, None, 6.0), (1.795, "up", 0.5)],
)
def test_speed_position(motor, direction, expected) -> None:
    assert cal.speed_position(REAL, motor, direction) == pytest.approx(expected, abs=0.01)


def _live_aligner(hass, monkeypatch, readings, lamp, learned, state):
    monkeypatch.setattr(cal, "MONITOR_EVERY", 0.01)
    monkeypatch.setattr(cal, "ALIGN_HOLD", 0.1)
    monkeypatch.setattr(cal, "LEARN_MIN", 0.2)
    monkeypatch.setattr(cal, "LEARN_HOLD", 0.15)
    monkeypatch.setattr(cal, "LEARN_MAX", 5.0)
    it = iter(readings)

    class LiveMeter:
        direct = True
        entity_id = "sensor.fan_power"

        async def async_read(self):
            return next(it, readings[-1])

    import copy

    return cal.PowerAligner(
        hass, LiveMeter(), copy.deepcopy(REAL), lambda e: None,
        speed_state=lambda: (state["speed"], state["own"]),
        lamp_on=lambda: lamp["on"],
        learn=lambda s, d, w: learned.append((s, d, w)),
    )


async def test_live_calibration_learns_the_settled_top_speed(hass: HomeAssistant, monkeypatch) -> None:
    ramp = [9.8 + i * 0.5 for i in range(27)] + [23.4] * 60
    learned: list = []
    state = {"speed": 6, "own": True}
    aligner = _live_aligner(hass, monkeypatch, ramp, {"on": False}, learned, state)
    stop = aligner.async_start()
    aligner.command_sent(6, 4)
    await asyncio.sleep(1.2)
    stop()
    assert learned and learned[-1] == (6, "up", 23.4)


async def test_live_calibration_needs_the_lamp_off_and_own_speed(hass: HomeAssistant, monkeypatch) -> None:
    learned: list = []
    lamp = {"on": True}
    state = {"speed": 6, "own": True}
    aligner = _live_aligner(hass, monkeypatch, [23.4] * 100, lamp, learned, state)
    stop = aligner.async_start()
    aligner.command_sent(6, 4)
    await asyncio.sleep(0.6)
    assert not learned  # lamp on: the session ended
    lamp["on"] = False
    state["own"] = False  # the speed now comes from a reading
    aligner.command_sent(6, 4)
    await asyncio.sleep(0.6)
    stop()
    assert not learned

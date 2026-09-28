"""Feedback, power relay, rich fans, held buttons and sync (0.2)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.rf_devices import codec
from custom_components.rf_devices.const import DOMAIN

from .helpers import BITS_A, BITS_B, capture

TX = "remote.rm_pro"
POWER = codec.clean(capture(BITS_A))
OTHER = codec.clean(capture(BITS_B))
C = {k: codec.clean(capture(format(i + 5, "024b"))) for i, k in enumerate(
    ["s1", "s2", "s3", "light", "dir", "fwd", "rev", "breeze", "dim", "off"]
)}


def _devices() -> dict:
    return {
        # Terraza: wall relay feeds the fan; power toggle; light measured by the relay.
        "terr": {
            "id": "terr", "name": "Terraza", "type": "fan",
            "options": {
                "speeds": 3, "power": "toggle", "direction": "toggle", "light": "toggle",
                "light_state_entity": "sensor.relay_power", "light_state_threshold": 5,
                "power_entity": "switch.relay",
            },
            "commands": {
                "power": {"code": POWER}, "speed_1": {"code": C["s1"]}, "speed_2": {"code": C["s2"]},
                "speed_3": {"code": C["s3"]}, "direction": {"code": C["dir"]},
                "light_toggle": {"code": C["light"]},
            },
        },
        # Cama: always powered; off button, summer/winter, breeze, dimmer held 0.5 s.
        "cama": {
            "id": "cama", "name": "Cama", "type": "fan",
            "options": {
                "speeds": 3, "power": "off", "direction": "buttons", "presets": ["Brisa"],
                "light": "toggle", "light_name": "Luz ventilador cama", "timers": ["30'", "2h"],
                "light_color": True, "light_dim": True,
            },
            "commands": {
                "off": {"code": C["off"]}, "speed_1": {"code": C["s1"]}, "speed_2": {"code": C["s2"]},
                "speed_3": {"code": C["s3"]}, "forward": {"code": C["fwd"]},
                "reverse": {"code": C["rev"]}, "preset_1": {"code": C["breeze"]},
                "light_toggle": {"code": C["light"]},
                "x_dim_up": {"code": C["dim"], "label": "Subir luz", "hold": 0.5},
                "timer_2": {"code": C["s2"]}, "light_color": {"code": C["s3"]}, "light_down": {"code": C["dim"]},
            },
        },
        # Lamp on a relay that may be switched on to light it.
        "lamp": {
            "id": "lamp", "name": "Lampara", "type": "light",
            "options": {"mode": "toggle", "power_entity": "switch.lamp_relay", "power_on_allowed": True},
            "commands": {"toggle": {"code": OTHER}},
        },
    }


@pytest.fixture
async def rf(hass: HomeAssistant, hass_storage):
    hass_storage[DOMAIN] = {
        "version": 1, "minor_version": 1, "key": DOMAIN,
        "data": {"devices": _devices(), "frequencies": {}},
    }
    hass.states.async_set(TX, "on")
    hass.states.async_set("switch.relay", "on")
    hass.states.async_set("sensor.relay_power", "1.2", {"unit_of_measurement": "W"})
    hass.states.async_set("switch.lamp_relay", "off")
    calls = async_mock_service(hass, "remote", "send_command")
    ha_on = async_mock_service(hass, "homeassistant", "turn_on")
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, calls=calls, ha_on=ha_on)


def sent(rf) -> list[str]:
    return [c.data["command"][0].removeprefix("b64:") for c in rf.calls]


async def call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)


async def test_light_follows_power_sensor(hass: HomeAssistant, rf) -> None:
    light = "light.terraza_light"
    assert hass.states.get(light).state == "off"
    # Someone uses the original remote: consumption rises.
    hass.states.async_set("sensor.relay_power", "9.5", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get(light).state == "on"
    # Asking to turn it on sends nothing: it really is on.
    await call(hass, "light", "turn_on", light)
    assert sent(rf) == []
    await call(hass, "light", "turn_off", light)
    assert sent(rf) == [C["light"]]
    assert hass.states.get("button.terraza_sync_light") is None  # has real feedback


async def test_fan_never_powers_relay_but_light_may(hass: HomeAssistant, rf) -> None:
    """Mode A (the default for devices with a relay): the lamp may power the
    relay (it lights by itself); the fan may not unless explicitly allowed."""
    hass.states.async_set("switch.relay", "off")
    await hass.async_block_till_done()
    assert hass.states.get("fan.terraza").state == "off"
    for service, data in (("turn_on", {}), ("set_percentage", {"percentage": 100})):
        with pytest.raises(HomeAssistantError):
            await call(hass, "fan", service, "fan.terraza", **data)
    await call(hass, "fan", "turn_off", "fan.terraza")
    assert sent(rf) == []
    assert rf.ha_on == []  # the fan never touched the relay
    await call(hass, "light", "turn_on", "light.terraza_light")
    assert [c.data["entity_id"] for c in rf.ha_on] == ["switch.relay"]
    assert sent(rf) == []  # the lamp lights at power-up: no RF needed


async def test_fan_toggle_power(hass: HomeAssistant, rf) -> None:
    await call(hass, "fan", "turn_off", "fan.terraza")
    assert sent(rf) == []  # already off: a toggle would start it
    await call(hass, "fan", "turn_on", "fan.terraza")
    assert sent(rf) == [C["s1"]]  # "on" without a speed = speed 1, sent as a speed code
    await call(hass, "fan", "set_percentage", "fan.terraza", percentage=100)
    await call(hass, "fan", "turn_off", "fan.terraza")
    assert sent(rf) == [C["s1"], C["s3"], POWER]
    await call(hass, "fan", "turn_on", "fan.terraza")
    assert hass.states.get("fan.terraza").attributes["percentage"] == 33
    await call(hass, "button", "press", "button.terraza_sync_fan")
    assert hass.states.get("fan.terraza").state == "off"
    assert len(rf.calls) == 4  # sync sent nothing


async def test_direction_toggle_and_buttons(hass: HomeAssistant, rf) -> None:
    await call(hass, "fan", "set_direction", "fan.terraza", direction="forward")
    assert sent(rf) == []  # already forward
    await call(hass, "fan", "set_direction", "fan.terraza", direction="reverse")
    assert sent(rf) == [C["dir"]]
    await call(hass, "fan", "set_direction", "fan.cama", direction="forward")
    await call(hass, "fan", "set_direction", "fan.cama", direction="reverse")
    assert sent(rf)[1:] == [C["fwd"], C["rev"]]
    assert hass.states.get("fan.cama").attributes["direction"] == "reverse"


async def test_preset_and_off_button(hass: HomeAssistant, rf) -> None:
    await call(hass, "fan", "set_preset_mode", "fan.cama", preset_mode="Brisa")
    state = hass.states.get("fan.cama")
    assert state.state == "on"
    assert state.attributes["preset_mode"] == "Brisa"
    await call(hass, "fan", "set_percentage", "fan.cama", percentage=33)
    assert hass.states.get("fan.cama").attributes["preset_mode"] is None
    await call(hass, "fan", "turn_off", "fan.cama")
    assert sent(rf) == [C["breeze"], C["s1"], C["off"]]


async def test_held_button(hass: HomeAssistant, rf) -> None:
    await call(hass, "button", "press", "button.cama_subir_luz")
    a = codec.analyze(sent(rf)[0])
    assert 450 <= a["sent_ms"] <= 700  # plus ~50 ms of silence closing each packet
    assert a["good_frames"] > 4


async def test_light_may_power_its_relay_when_allowed(hass: HomeAssistant, rf) -> None:
    assert hass.states.get("light.lampara").state == "off"
    await call(hass, "light", "turn_on", "light.lampara")
    assert [c.data["entity_id"] for c in rf.ha_on] == ["switch.lamp_relay"]
    assert sent(rf) == []  # it lights up by itself when powered
    assert hass.states.get("light.lampara").state == "on"
    hass.states.async_set("switch.lamp_relay", "on")
    await hass.async_block_till_done()
    hass.states.async_set("switch.lamp_relay", "off")
    await hass.async_block_till_done()
    assert hass.states.get("light.lampara").state == "off"


async def test_named_light_timers_and_light_buttons(hass: HomeAssistant, rf) -> None:
    assert hass.states.get("light.luz_ventilador_cama").name == "Luz ventilador cama"
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    ents, devs = er.async_get(hass), dr.async_get(hass)
    light_dev = devs.async_get(ents.async_get("light.luz_ventilador_cama").device_id)
    fan_dev = devs.async_get(ents.async_get("fan.cama").device_id)
    assert light_dev.name == "Luz ventilador cama"
    assert light_dev.via_device_id is None  # two independent devices
    assert light_dev.id != fan_dev.id
    colour = ents.async_get(next(e for e in ents.entities if e.endswith("light_colour")))
    assert colour.device_id == light_dev.id  # light buttons live on the light
    assert hass.states.get("button.cama_timer_2h") is not None
    assert hass.states.get("button.cama_timer_30") is None  # not captured
    assert hass.states.get("button.luz_ventilador_cama_light_colour") is not None
    await call(hass, "button", "press", "button.luz_ventilador_cama_dimmer")
    a = codec.analyze(sent(rf)[0])
    assert a["good_frames"] > 4  # held 0.5 s by default


async def test_device_page_mirrors(hass: HomeAssistant, rf) -> None:
    power = hass.states.get("sensor.terraza_power_draw")
    assert power.state == "1.2"
    assert power.attributes["unit_of_measurement"] == "W"
    hass.states.async_set("sensor.relay_power", "40.1", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.terraza_power_draw").state == "40.1"
    assert hass.states.get("binary_sensor.terraza_power_supply").state == "on"
    hass.states.async_set("switch.relay", "off")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.terraza_power_supply").state == "off"


async def test_percentage_table_and_small_numbers(hass: HomeAssistant, rf) -> None:
    hub = rf.entry.runtime_data
    device = dict(hub.store.devices["cama"])
    device["options"] = {**device["options"], "speed_percentages": [20, 60, 100], "turn_on_speed": 2}
    await hub.store.async_upsert(device)
    await hass.config_entries.async_reload(rf.entry.entry_id)
    await hass.async_block_till_done()
    await call(hass, "fan", "set_percentage", "fan.cama", percentage=2)  # "set the fan to 2"
    assert sent(rf)[-1] == C["s2"]
    await call(hass, "fan", "set_percentage", "fan.cama", percentage=45)  # table: 21-60 % -> 2
    assert sent(rf)[-1] == C["s2"]
    assert hass.states.get("fan.cama").attributes["percentage"] == 60
    await call(hass, "fan", "set_percentage", "fan.cama", percentage=15)  # up to 20 % -> 1
    assert sent(rf)[-1] == C["s1"]
    await call(hass, "fan", "turn_off", "fan.cama")
    await call(hass, "fan", "turn_on", "fan.cama")  # configured turn-on speed
    assert sent(rf)[-1] == C["s2"]


async def test_rounded_percentages_hit_the_intended_speed(hass: HomeAssistant, rf) -> None:
    """4 × 16.67 % arrives as 67 %; with 6 speeds that is speed 4, not 5."""
    hub = rf.entry.runtime_data
    device = dict(hub.store.devices["cama"])
    device["options"] = {**device["options"], "speeds": 6}
    device["commands"] = {**device["commands"], "speed_4": {"code": C["dim"]}, "speed_5": {"code": C["breeze"]},
                          "speed_6": {"code": C["fwd"]}}
    await hub.store.async_upsert(device)
    await hass.config_entries.async_reload(rf.entry.entry_id)
    await hass.async_block_till_done()
    await call(hass, "fan", "set_percentage", "fan.cama", percentage=67)
    assert sent(rf)[-1] == C["dim"]  # speed 4
    assert hass.states.get("fan.cama").attributes["speed_percentages"] == [16, 33, 50, 66, 83, 100]


async def test_aligner_keeps_a_running_preset(hass: HomeAssistant, rf) -> None:
    """Breeze swings between speeds on purpose: a reading must not turn it into a speed."""
    from custom_components.rf_devices.calibration import Estimate
    from custom_components.rf_devices.entity import live_entities

    await call(hass, "fan", "set_preset_mode", "fan.cama", preset_mode="Brisa")
    fan = live_entities(hass)["fan.cama"]
    fan._apply_estimate(Estimate(speed=3, fan_on=True, light=False))
    assert hass.states.get("fan.cama").attributes["preset_mode"] == "Brisa"
    fan._apply_estimate(Estimate(speed=None, fan_on=False, light=False))  # really stopped
    assert hass.states.get("fan.cama").state == "off"

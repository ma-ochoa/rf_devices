"""End-to-end tests against a real Home Assistant core."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from broadlink.exceptions import ReadError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.rf_devices import codec
from custom_components.rf_devices.const import DOMAIN

from .helpers import BITS_A, BITS_B, capture

TX = "remote.rm_pro"
CODE_A = codec.clean(capture(BITS_A))
CODE_B = codec.clean(capture(BITS_B))


def _devices() -> dict:
    return {
        "lamp": {
            "id": "lamp", "name": "Luz cama", "type": "light", "transmitter": None,
            "options": {"mode": "toggle", "switch_entity": "binary_sensor.wall"},
            "commands": {"toggle": {"code": CODE_A}},
        },
        "fan1": {
            "id": "fan1", "name": "Ventilador", "type": "fan", "transmitter": None,
            "options": {"speeds": 3, "light": "none"},
            "commands": {
                "off": {"code": CODE_B},
                "speed_1": {"code": CODE_A}, "speed_2": {"code": CODE_A}, "speed_3": {"code": CODE_B},
                "x_timer": {"code": CODE_A, "label": "Temporizador"},
            },
        },
        "blind": {
            "id": "blind", "name": "Persiana", "type": "cover", "transmitter": None,
            "options": {"open_time": 1, "close_time": 1, "device_class": "shutter"},
            "commands": {"open": {"code": CODE_A}, "close": {"code": CODE_B}, "stop": {"code": CODE_A}},
        },
    }


@pytest.fixture
async def setup(hass: HomeAssistant, hass_storage):
    hass_storage[DOMAIN] = {
        "version": 1, "minor_version": 1, "key": DOMAIN,
        "data": {"devices": _devices(), "frequencies": {}},
    }
    hass.states.async_set(TX, "on")
    hass.states.async_set("binary_sensor.wall", "off")
    calls = async_mock_service(hass, "remote", "send_command")
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, calls=calls)


def _sent(calls) -> list[str]:
    return [c.data["command"][0] for c in calls]


async def test_config_flow(hass: HomeAssistant) -> None:
    hass.states.async_set(TX, "on")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"transmitter": TX})
    assert result["type"] == "create_entry"
    assert result["data"] == {"transmitter": TX}


async def test_entities_created(hass: HomeAssistant, setup) -> None:
    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), setup.entry.entry_id)}
    assert ids == {
        "light.luz_cama", "button.luz_cama_sync",
        "fan.ventilador", "button.ventilador_temporizador", "cover.persiana",
    }
    assert "assumed_state" not in hass.states.get("light.luz_cama").attributes  # toggle in dashboards


async def test_toggle_light_is_idempotent(hass: HomeAssistant, setup) -> None:
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.luz_cama"}, blocking=True)
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.luz_cama"}, blocking=True)
    assert _sent(setup.calls) == [f"b64:{CODE_A}"]
    assert setup.calls[0].data["entity_id"] == [TX] or setup.calls[0].data["entity_id"] == TX
    assert hass.states.get("light.luz_cama").state == "on"
    await hass.services.async_call("light", "turn_off", {"entity_id": "light.luz_cama"}, blocking=True)
    assert len(setup.calls) == 2
    assert hass.states.get("light.luz_cama").state == "off"


async def test_wall_switch_flips_on_any_change(hass: HomeAssistant, setup) -> None:
    hass.states.async_set("binary_sensor.wall", "on")
    await hass.async_block_till_done()
    assert hass.states.get("light.luz_cama").state == "on"
    hass.states.async_set("binary_sensor.wall", "unavailable")
    hass.states.async_set("binary_sensor.wall", "on")
    await hass.async_block_till_done()
    assert len(setup.calls) == 1  # unavailable → on is not a flip
    hass.states.async_set("binary_sensor.wall", "off")
    await hass.async_block_till_done()
    assert hass.states.get("light.luz_cama").state == "off"
    assert len(setup.calls) == 2


async def test_fast_flips_stay_in_step(hass: HomeAssistant, setup) -> None:
    for state in ("on", "off", "on"):
        hass.states.async_set("binary_sensor.wall", state)
    await hass.async_block_till_done()
    assert len(setup.calls) == 3
    assert hass.states.get("light.luz_cama").state == "on"


async def test_set_state_service_sends_nothing(hass: HomeAssistant, setup) -> None:
    await hass.services.async_call(
        DOMAIN, "set_state", {"entity_id": "light.luz_cama", "is_on": True}, blocking=True
    )
    assert hass.states.get("light.luz_cama").state == "on"
    assert setup.calls == []


async def test_fan_speeds(hass: HomeAssistant, setup) -> None:
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": "fan.ventilador", "percentage": 100}, blocking=True
    )
    assert _sent(setup.calls) == [f"b64:{CODE_B}"]
    assert hass.states.get("fan.ventilador").attributes["percentage"] == 100
    await hass.services.async_call("fan", "turn_off", {"entity_id": "fan.ventilador"}, blocking=True)
    assert hass.states.get("fan.ventilador").state == "off"
    await hass.services.async_call("fan", "turn_on", {"entity_id": "fan.ventilador"}, blocking=True)
    assert hass.states.get("fan.ventilador").attributes["percentage"] == 33  # speed 1 by default
    await hass.services.async_call("button", "press", {"entity_id": "button.ventilador_temporizador"}, blocking=True)
    assert len(setup.calls) == 4


async def test_cover_position_by_time(hass: HomeAssistant, setup) -> None:
    assert hass.states.get("cover.persiana").attributes["current_position"] == 100
    await hass.services.async_call(
        "cover", "set_cover_position", {"entity_id": "cover.persiana", "position": 50}, blocking=True
    )
    assert _sent(setup.calls) == [f"b64:{CODE_B}"]  # close
    assert hass.states.get("cover.persiana").state == "closing"
    await asyncio.sleep(0.7)
    await hass.async_block_till_done()
    assert _sent(setup.calls) == [f"b64:{CODE_B}", f"b64:{CODE_A}"]  # close, stop
    assert hass.states.get("cover.persiana").attributes["current_position"] == 50
    await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.persiana"}, blocking=True)
    await hass.services.async_call("cover", "stop_cover", {"entity_id": "cover.persiana"}, blocking=True)
    pos = hass.states.get("cover.persiana").attributes["current_position"]
    assert 50 <= pos < 60
    assert hass.states.get("cover.persiana").state == "open"


async def test_websocket_crud_export_import(hass: HomeAssistant, setup, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)

    await ws.send_json_auto_id({"type": "rf_devices/info"})
    info = (await ws.receive_json())["result"]
    assert info["default_transmitter"] == TX

    await ws.send_json_auto_id({
        "type": "rf_devices/device/save",
        "device": {"name": "Enchufe", "type": "switch", "commands": {"on": {"code": "b64:" + CODE_A, "analysis": {}}}},
    })
    msg = await ws.receive_json()
    assert msg["success"], msg
    new = msg["result"]
    assert new["missing"] == ["off"]
    await hass.async_block_till_done()
    assert hass.states.get("switch.enchufe") is not None

    await ws.send_json_auto_id({"type": "rf_devices/export"})
    export = (await ws.receive_json())["result"]
    assert export["format"] == "rf_devices_export"
    assert len(export["devices"]) == 4

    await ws.send_json_auto_id({"type": "rf_devices/device/delete", "device_id": new["id"]})
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()
    assert hass.states.get("switch.enchufe") is None
    assert er.async_get(hass).async_get("switch.enchufe") is None

    await ws.send_json_auto_id({"type": "rf_devices/import", "data": export, "replace": True})
    result = (await ws.receive_json())["result"]
    assert result == {"added": 1, "replaced": 3}
    await hass.async_block_till_done()
    assert hass.states.get("switch.enchufe") is not None

    await ws.send_json_auto_id({"type": "rf_devices/import", "data": {"format": "other"}})
    assert not (await ws.receive_json())["success"]


async def test_websocket_code_tools(hass: HomeAssistant, setup, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    raw = capture(BITS_A, frames=12, repeat=2)
    await ws.send_json_auto_id({"type": "rf_devices/code/analyze", "code": "b64:" + raw})
    r = (await ws.receive_json())["result"]
    assert r["raw_analysis"]["needs_cleaning"]
    assert r["analysis"]["good_frames"] == 4

    await ws.send_json_auto_id({"type": "rf_devices/code/clean", "code": raw, "frames": 6})
    assert (await ws.receive_json())["result"]["analysis"]["good_frames"] == 6

    await ws.send_json_auto_id({"type": "rf_devices/code/send", "code": CODE_A})
    assert (await ws.receive_json())["success"]
    assert _sent(setup.calls) == [f"b64:{CODE_A}"]


def _fake_broadlink(hass: HomeAssistant, api: MagicMock) -> None:
    """Register TX as a Broadlink remote whose device object uses ``api``."""
    fake_entry = MockConfigEntry(domain="broadlink")
    fake_entry.add_to_hass(hass)
    hass.states.async_remove(TX)  # free the entity_id for the registry entry
    ent = er.async_get(hass).async_get_or_create(
        "remote", "broadlink", "mac", config_entry=fake_entry, suggested_object_id="rm_pro"
    )
    assert ent.entity_id == TX

    async def request(func, *args):
        return func(*args)

    hass.data["broadlink"] = SimpleNamespace(
        devices={fake_entry.entry_id: SimpleNamespace(api=api, async_request=request)}
    )


async def _stages(ws) -> tuple[list[str], dict]:
    stages = []
    while True:
        ev = (await ws.receive_json(timeout=10))["event"]
        stages.append(ev["stage"])
        if ev["stage"] in ("captured", "timeout", "error"):
            return stages, ev


async def test_learn_with_known_frequency(hass: HomeAssistant, setup, hass_ws_client) -> None:
    api = MagicMock()
    raw = codec.decode(capture(BITS_A, frames=12))
    answers = [ReadError(-5, "no data"), codec.encode(raw)]

    def check_data():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    api.check_data.side_effect = check_data
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn", "frequency": 433.92})
    first = await ws.receive_json()
    assert first.get("success"), first
    stages, ev = await _stages(ws)
    assert stages == ["press", "captured"], ev
    api.find_rf_packet.assert_called_once_with(433.92)
    api.sweep_frequency.assert_not_called()
    assert ev["analysis"]["good_frames"] == 4
    assert ev["raw_analysis"]["frames"] == 13


async def test_learn_with_sweep_remembers_frequency(hass: HomeAssistant, setup, hass_ws_client) -> None:
    api = MagicMock()
    api.check_frequency.side_effect = [(False, 0.0), (True, 433.92)]
    api.check_data.return_value = codec.encode(codec.decode(capture(BITS_B)))
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    assert (await ws.receive_json())["success"]
    stages, ev = await _stages(ws)
    assert stages == ["sweep", "frequency", "press", "captured"]
    api.cancel_sweep_frequency.assert_called_once()  # only the reset before starting
    assert setup.entry.runtime_data.store.frequencies == {TX: 433.92}


async def test_learn_cancel_stops_sweep(hass: HomeAssistant, setup, hass_ws_client) -> None:
    api = MagicMock()
    api.check_frequency.return_value = (False, 0.0)
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    sub_id = (await ws.receive_json())["id"]
    assert (await ws.receive_json())["event"]["stage"] == "sweep"
    await ws.send_json_auto_id({"type": "unsubscribe_events", "subscription": sub_id})
    assert (await ws.receive_json())["success"]
    await hass.async_block_till_done()
    assert api.cancel_sweep_frequency.call_count == 2  # reset before, exit after


async def test_learn_press_timeout_exits_learning(hass: HomeAssistant, setup, hass_ws_client, monkeypatch) -> None:
    monkeypatch.setattr("custom_components.rf_devices.transmitters.remote.LEARN_TIMEOUT", 1)
    api = MagicMock()
    api.check_data.side_effect = ReadError(-5, "no data")
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn", "frequency": 433.92})
    assert (await ws.receive_json())["success"]
    stages, ev = await _stages(ws)
    assert stages == ["press", "timeout"]
    await hass.async_block_till_done()
    assert api.cancel_sweep_frequency.call_count == 2


async def test_learn_zero_frequency_and_unreachable(hass: HomeAssistant, setup, hass_ws_client) -> None:
    from broadlink.exceptions import NetworkTimeoutError

    api = MagicMock()
    api.check_frequency.return_value = (True, 0.0)  # RM Pro+ behaviour
    api.check_data.side_effect = NetworkTimeoutError(-4000, "Network timeout")
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    assert (await ws.receive_json())["success"]
    stages, ev = await _stages(ws)
    assert stages == ["sweep", "frequency", "press", "error"]
    assert ev["reason"] == "unreachable"
    api.find_rf_packet.assert_called_once_with(None)
    assert setup.entry.runtime_data.store.frequencies == {}


async def test_learn_rejects_non_broadlink(hass: HomeAssistant, setup, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert "not a Broadlink remote" in msg["error"]["message"]


async def test_learn_refused_when_broadlink_silent(hass: HomeAssistant, setup, hass_ws_client) -> None:
    from broadlink.exceptions import NetworkTimeoutError

    api = MagicMock()
    api.hello.side_effect = NetworkTimeoutError(-4000, "Network timeout")
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    assert (await ws.receive_json())["success"]
    stages, ev = await _stages(ws)
    assert stages == ["error"]
    assert ev["reason"] == "unreachable"
    api.sweep_frequency.assert_not_called()
    api.find_rf_packet.assert_not_called()


async def test_no_transmission_during_capture(hass: HomeAssistant, setup, hass_ws_client) -> None:
    api = MagicMock()
    api.check_frequency.return_value = (False, 0.0)
    _fake_broadlink(hass, api)

    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    sub_id = (await ws.receive_json())["id"]
    assert (await ws.receive_json())["event"]["stage"] == "sweep"
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("light", "turn_on", {"entity_id": "light.luz_cama"}, blocking=True)
    assert setup.calls == []
    await ws.send_json_auto_id({"type": "unsubscribe_events", "subscription": sub_id})
    await ws.receive_json()


async def test_power_cycle_when_broadlink_hangs(hass: HomeAssistant, setup, monkeypatch) -> None:
    for name in ("HEALTH_DELAY", "POWER_OFF_TIME"):
        monkeypatch.setattr(f"custom_components.rf_devices.transmitters.remote.{name}", 0)
    monkeypatch.setattr("custom_components.rf_devices.transmitters.remote.POWER_BOOT_TIME", 5)
    monkeypatch.setattr("custom_components.rf_devices.transmitters.remote.asyncio.sleep", _no_sleep)
    hass.config_entries.async_update_entry(
        setup.entry, options={**setup.entry.options, "power_switch": "switch.plug"}
    )
    await hass.async_block_till_done()
    hass.states.async_set("switch.plug", "on")
    offs = async_mock_service(hass, "homeassistant", "turn_off")
    ons = async_mock_service(hass, "homeassistant", "turn_on")

    api = MagicMock()
    alive = iter([False, False, True])

    def hello():
        if not next(alive):
            raise OSError("no route")
        return True

    api.hello.side_effect = hello
    tx = setup.entry.runtime_data.transmitter(TX)
    await tx._async_after_learning(SimpleNamespace(api=api, async_request=_request))
    assert [c.data["entity_id"] for c in offs] == ["switch.plug"]
    assert [c.data["entity_id"] for c in ons] == ["switch.plug"]
    api.cancel_sweep_frequency.assert_called_once()


_real_sleep = asyncio.sleep


async def _no_sleep(_delay) -> None:
    await _real_sleep(0)


async def _request(func, *args):
    return func(*args)


async def test_learn_tolerates_a_busy_broadlink(hass: HomeAssistant, setup, hass_ws_client, monkeypatch) -> None:
    from broadlink.exceptions import NetworkTimeoutError

    monkeypatch.setattr("custom_components.rf_devices.transmitters.remote.POLL_INTERVAL", 0.05)
    api = MagicMock()
    answers = [NetworkTimeoutError(-4000, "busy"), ReadError(-5, "no data"), NetworkTimeoutError(-4000, "busy"),
               codec.encode(codec.decode(capture(BITS_A)))]

    def check_data():
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    api.check_data.side_effect = check_data
    _fake_broadlink(hass, api)
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn", "frequency": 433.92})
    assert (await ws.receive_json())["success"]
    stages, _ = await _stages(ws)
    assert stages == ["press", "captured"]


@pytest.mark.parametrize("kind", ["cover", "buttons"])
async def test_new_device_without_relay_options_can_be_saved(hass, setup, hass_ws_client, kind) -> None:
    """Covers and button sets have no relay options; saving must not add any."""
    ws = await hass_ws_client(hass)
    commands = {"open": {"code": CODE_A}, "close": {"code": CODE_B}} if kind == "cover" else {}
    device = {"name": "Nuevo", "type": kind, "options": {}, "commands": commands}
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert "take_relay_entity_id" not in msg["result"]["options"]
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": msg["result"]})
    assert (await ws.receive_json())["success"]  # and again, as the editor does


async def _cover_with(hass, hass_storage, **options):
    devices = {"blind": _devices()["blind"]}
    devices["blind"]["options"].update(options)
    hass_storage[DOMAIN] = {
        "version": 1, "minor_version": 1, "key": DOMAIN,
        "data": {"devices": devices, "frequencies": {}},
    }
    hass.states.async_set(TX, "on")
    calls = async_mock_service(hass, "remote", "send_command")
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return calls


async def test_cover_full_travel_follows_the_motor(hass, hass_storage, monkeypatch) -> None:
    """With a meter, closing ends when the motor stops, not when the time is up."""
    from custom_components.rf_devices import cover as cover_mod

    monkeypatch.setattr(cover_mod, "TICK", 0.05)
    hass.states.async_set("sensor.motor", "0")
    await _cover_with(hass, hass_storage, state_entity="sensor.motor", open_time=0.2, close_time=0.2)
    await hass.services.async_call("cover", "close_cover", {"entity_id": "cover.persiana"}, blocking=True)
    hass.states.async_set("sensor.motor", "120")
    await asyncio.sleep(0.5)  # well past the 0.2 s: still running
    state = hass.states.get("cover.persiana")
    assert state.state == "closing" and state.attributes["current_position"] == 1
    hass.states.async_set("sensor.motor", "0")
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()
    state = hass.states.get("cover.persiana")
    assert state.state == "closed" and state.attributes["current_position"] == 0
    assert state.attributes["position_reliable"] is True
    assert 0.3 < state.attributes["last_run_seconds"] < 0.8
    # The original remote moves it: which way cannot be known.
    await asyncio.sleep(0.1)
    monkeypatch.setattr(cover_mod, "OWN_WINDOW", 0)
    hass.states.async_set("sensor.motor", "118")
    await hass.async_block_till_done()
    assert hass.states.get("cover.persiana").attributes["position_reliable"] is False


async def test_cover_relay_and_wall_button(hass, hass_storage, monkeypatch) -> None:
    hass.states.async_set("switch.motor", "off")
    hass.states.async_set("binary_sensor.wall", "off")
    relay_on = async_mock_service(hass, "homeassistant", "turn_on")
    calls = await _cover_with(
        hass, hass_storage, power_entity="switch.motor", power_up_delay=0, switch_entity="binary_sensor.wall",
        wall_type="maintained", open_time=5, close_time=5,
    )
    assert not entry_relays(hass)  # the fan/light relay controller is not for covers
    await hass.services.async_call("cover", "stop_cover", {"entity_id": "cover.persiana"}, blocking=True)
    assert not calls  # no power: nothing to stop
    hass.states.async_set("binary_sensor.wall", "on")  # open (100 %) -> close
    await hass.async_block_till_done()
    assert [c.data["entity_id"] for c in relay_on] == ["switch.motor"]
    assert _sent(calls) == [f"b64:{CODE_B}"]
    hass.states.async_set("switch.motor", "on")
    hass.states.async_set("binary_sensor.wall", "off")  # moving -> stop
    await hass.async_block_till_done()
    assert _sent(calls) == [f"b64:{CODE_B}", f"b64:{CODE_A}"]
    assert hass.states.get("cover.persiana").state == "open"
    hass.states.async_set("binary_sensor.wall", "on")  # was closing -> open
    await hass.async_block_till_done()
    assert hass.states.get("cover.persiana").state == "opening"
    hass.states.async_set("switch.motor", "off")  # power cut: it stops there
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert hass.states.get("cover.persiana").state == "open"


def entry_relays(hass):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data.relays


async def test_cover_two_wall_push_buttons(hass, hass_storage) -> None:
    """Up and down push buttons: a press moves, any press while moving stops; releases do nothing."""
    up, down = "binary_sensor.up", "binary_sensor.down"
    hass.states.async_set(up, "off")
    hass.states.async_set(down, "off")
    calls = await _cover_with(
        hass, hass_storage, switch_entity=up, switch_close_entity=down, open_time=5, close_time=5
    )

    async def press(entity):
        hass.states.async_set(entity, "on")
        await hass.async_block_till_done()
        hass.states.async_set(entity, "off")
        await hass.async_block_till_done()

    await press(down)
    assert _sent(calls) == [f"b64:{CODE_B}"]
    assert hass.states.get("cover.persiana").state == "closing"
    await press(up)  # moving: stop
    assert _sent(calls) == [f"b64:{CODE_B}", f"b64:{CODE_A}"]
    assert hass.states.get("cover.persiana").state == "open"
    await press(up)
    assert hass.states.get("cover.persiana").state == "opening"
    await hass.services.async_call("cover", "stop_cover", {"entity_id": "cover.persiana"}, blocking=True)

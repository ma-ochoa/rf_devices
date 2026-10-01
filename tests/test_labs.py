"""labs: Somfy RTS, service-call buttons, linked entities and following the original remote.

Two ESPHome radios as an ESP32 with two CC1101 would expose them: one fixed
at 433.92 MHz and one at 433.42 MHz, each with a transmitter entity and a
receiver (the receivers are not entities, only entity info).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aioesphomeapi import RadioFrequencyInfo
from homeassistant.components.radio_frequency import RadioFrequencyTransmitterEntity
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_capture_events,
    async_mock_service,
)

from custom_components.rf_devices import codec, listen
from custom_components.rf_devices import hub as hub_module
from custom_components.rf_devices.const import DOMAIN
from custom_components.rf_devices.protocols import somfy
from custom_components.rf_devices.transmitters import radio_frequency as rf_tx

from .helpers import BITS_A, BITS_B, capture
from .test_radio_frequency import FakeClient, _esphome_bursts

TX92 = "radio_frequency.rf_433_92"
TX42 = "radio_frequency.rf_433_42"
CODE_A = codec.clean(capture(BITS_A))
CODE_B = codec.clean(capture(BITS_B))
OWN = 0x123456  # our virtual Somfy remote
REAL = 0xABCDEF  # the real Somfy remote in the room


class Radio(RadioFrequencyTransmitterEntity):
    def __init__(self, entity_id: str, hz: int) -> None:
        self.entity_id = entity_id
        self._attr_name = entity_id.split(".")[1]
        self._attr_unique_id = entity_id
        self._hz = hz
        self.sent = []

    @property
    def supported_frequency_ranges(self) -> list[tuple[int, int]]:
        return [(self._hz, self._hz)]

    async def async_send_command(self, command) -> None:
        self.sent.append(command)


def _devices() -> dict:
    return {
        "blind": {
            "id": "blind", "name": "Persiana salon", "type": "cover", "transmitter": TX42,
            "options": {"open_time": 10, "close_time": 10},
            "somfy": {"address": OWN},
            "commands": {
                "open": {"kind": "somfy", "button": "up"},
                "close": {"kind": "somfy", "button": "down"},
                "stop": {"kind": "somfy", "button": "my"},
            },
            "follow": True, "follow_somfy": [REAL],
        },
        "alarm": {
            "id": "alarm", "name": "Alarma", "type": "switch", "transmitter": TX92,
            "options": {"mode": "onoff"},
            "commands": {"on": {"code": CODE_A}, "off": {"code": CODE_B}},
            "follow": True,
        },
        "remote": {
            "id": "remote", "name": "Botonera", "type": "buttons",
            "options": {},
            "commands": {"x_scene": {"kind": "action", "service": "test.press",
                                     "entity_id": "scene.cine", "data": {"transition": 2},
                                     "label": "Cine"}},
        },
        "curtain": {
            "id": "curtain", "name": "Cortina", "type": "cover",
            "options": {}, "linked_entity": "cover.esp_cortina", "mirror": True,
            "commands": {
                "open": {"kind": "action", "service": "test.open", "entity_id": "cover.esp_cortina"},
                "close": {"kind": "action", "service": "test.close", "entity_id": "cover.esp_cortina"},
            },
        },
        "blefan": {
            "id": "blefan", "name": "Ventilador Dani", "type": "fan",
            "options": {"speeds": 6, "light": "onoff"},
            "linked_entity": "fan.ble", "linked_light_entity": "light.ble", "mirror": True,
            "commands": {
                "off": {"kind": "action", "service": "test.fan_off", "entity_id": "fan.ble"},
                **{f"speed_{n}": {"kind": "action", "service": "test.pct", "entity_id": "fan.ble",
                                  "data": {"percentage": round(n * 100 / 6)}} for n in range(1, 7)},
                "light_on": {"kind": "action", "service": "test.lon", "entity_id": "light.ble"},
                "light_off": {"kind": "action", "service": "test.loff", "entity_id": "light.ble"},
            },
        },
    }


@pytest.fixture
async def labs(hass: HomeAssistant, hass_storage, monkeypatch):
    monkeypatch.setattr(hub_module, "ECHO_MARGIN", 0.0)
    monkeypatch.setattr(listen, "PRESS_QUIET", 0.1)
    esphome_entry = MockConfigEntry(domain="esphome")
    esphome_entry.add_to_hass(hass)
    infos = {
        1: RadioFrequencyInfo(key=1, capabilities=1, frequency_min=433_920_000, frequency_max=433_920_000),
        2: RadioFrequencyInfo(key=2, capabilities=2, frequency_min=433_920_000, frequency_max=433_920_000),
        3: RadioFrequencyInfo(key=3, capabilities=1, frequency_min=433_420_000, frequency_max=433_420_000),
        4: RadioFrequencyInfo(key=4, capabilities=2, frequency_min=433_420_000, frequency_max=433_420_000),
    }
    client = FakeClient(infos.values())
    esphome_entry.runtime_data = SimpleNamespace(
        client=client,
        available=True,
        # As Home Assistant does: it keeps the transmitters only (no entity for a receiver).
        info={RadioFrequencyInfo: {1: infos[1], 3: infos[3]}},
    )
    assert await async_setup_component(hass, "radio_frequency", {})
    platform = MockEntityPlatform(hass, domain="radio_frequency", platform_name="esphome")
    platform.config_entry = esphome_entry
    r92, r42 = Radio(TX92, 433_920_000), Radio(TX42, 433_420_000)
    await platform.async_add_entities([r92, r42])
    hass.states.async_set("cover.esp_cortina", "open", {"current_position": 40})
    hass.states.async_set("fan.ble", "on", {"percentage": 50})
    hass.states.async_set("light.ble", "off")
    calls = {name: async_mock_service(hass, "test", name)
             for name in ("press", "open", "close", "fan_off", "pct", "lon", "loff")}

    hass_storage[DOMAIN] = {
        "version": 1, "minor_version": 1, "key": DOMAIN,
        "data": {"devices": _devices(), "frequencies": {}, "somfy_codes": {f"{OWN:06X}": 41}},
    }
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX92}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await asyncio.sleep(0.6)  # linked entities are copied shortly after start
    await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, r92=r92, r42=r42, client=client, calls=calls,
                           hub=entry.runtime_data)


def _decode(command) -> list[somfy.Press]:
    return somfy.decode(list(command.get_raw_timings()))


# ---------------------------------------------------------------- Somfy


async def test_somfy_press_uses_the_433_42_radio_and_counts(hass: HomeAssistant, labs) -> None:
    await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.persiana_salon"}, blocking=True)
    await hass.services.async_call("cover", "stop_cover", {"entity_id": "cover.persiana_salon"}, blocking=True)
    assert labs.r92.sent == []
    first, second = labs.r42.sent
    assert first.frequency == 433_420_000
    assert set(_decode(first)) == {somfy.Press(OWN, "up", 42)}
    assert set(_decode(second)) == {somfy.Press(OWN, "my", 43)}
    assert labs.hub.store.somfy_code(OWN) == 43
    assert len(_decode(first)) == somfy.DEFAULT_REPEATS + 1


async def test_somfy_invert_and_stale_save_keep_the_counter(hass: HomeAssistant, labs, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/devices"})
    blind = next(d for d in (await ws.receive_json())["result"] if d["id"] == "blind")
    assert blind["somfy_code"] == 41
    assert blind["somfy_note"] is None  # the radio is at 433.42 MHz
    blind["somfy"]["invert"] = True
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": blind})
    msg = await ws.receive_json()
    assert msg["success"], msg
    await hass.async_block_till_done()
    await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.persiana_salon"}, blocking=True)
    assert _decode(labs.r42.sent[-1])[0].button == "down"
    assert labs.entry.runtime_data.store.somfy_code(OWN) == 42  # reloaded: a new hub


async def test_somfy_through_a_433_92_radio_is_flagged(hass: HomeAssistant, labs) -> None:
    device = dict(labs.hub.store.devices["blind"], transmitter=TX92)
    tx = labs.hub.transmitter(TX92)
    assert "433.92 MHz" in tx.carrier_note(somfy.FREQUENCY_HZ)
    await labs.hub.async_send_somfy(device, "prog")
    assert labs.r92.sent[-1].frequency == 433_920_000  # the closest it can do
    assert _decode(labs.r92.sent[-1])[0].button == "prog"


async def test_pair_from_the_editor_copy(hass: HomeAssistant, labs, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/somfy/new_address"})
    address = (await ws.receive_json())["result"]["address"]
    assert 0 < address <= somfy.MAX_ADDRESS and address not in (OWN, REAL)
    await ws.send_json_auto_id({
        "type": "rf_devices/command/send",
        "device": {"name": "Nueva", "transmitter": TX42, "somfy": {"address": address}},
        "command": {"kind": "somfy", "button": "prog"},
    })
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert msg["result"]["somfy_code"] == 1
    assert _decode(labs.r42.sent[-1])[0] == somfy.Press(address, "prog", 1)


async def test_decode_a_captured_somfy_remote(hass: HomeAssistant, labs, hass_ws_client) -> None:
    code = codec.from_timings([somfy.encode(REAL, "up", 777, 2)])
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/somfy/decode", "code": code})
    result = (await ws.receive_json())["result"]
    assert result == [{"address": REAL, "hex": "ABCDEF", "button": "up", "rolling_code": 777}]


async def test_somfy_counter_travels_with_the_export(hass: HomeAssistant, labs) -> None:
    exported = labs.hub.store.export(["blind"])
    assert exported["somfy_codes"] == {f"{OWN:06X}": 41}
    labs.hub.store.somfy_codes[f"{OWN:06X}"] = 60
    exported["somfy_codes"][f"{OWN:06X}"] = 50
    await labs.hub.store.async_import(exported, replace=True)
    assert labs.hub.store.somfy_code(OWN) == 60  # never back


# ------------------------------------------------------- actions and links


async def test_action_button_calls_the_service(hass: HomeAssistant, labs) -> None:
    await hass.services.async_call("button", "press", {"entity_id": "button.botonera_cine"}, blocking=True)
    (call,) = labs.calls["press"]
    assert call.data == {"entity_id": "scene.cine", "transition": 2}


async def test_linked_cover_is_mirrored(hass: HomeAssistant, labs) -> None:
    state = hass.states.get("cover.cortina")
    assert state.attributes["current_position"] == 40
    hass.states.async_set("cover.esp_cortina", "closing", {"current_position": 30})
    await hass.async_block_till_done()
    assert hass.states.get("cover.cortina").state == "closing"
    await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.cortina"}, blocking=True)
    assert len(labs.calls["open"]) == 1
    assert hass.states.get("cover.cortina").attributes["current_position"] == 30  # no timing here


async def test_linked_fan_and_lamp_are_mirrored(hass: HomeAssistant, labs) -> None:
    fan = hass.states.get("fan.ventilador_dani")
    assert fan.state == "on" and fan.attributes["percentage"] == 50
    hass.states.async_set("fan.ble", "on", {"percentage": 100})
    hass.states.async_set("light.ble", "on")
    await hass.async_block_till_done()
    assert hass.states.get("fan.ventilador_dani").attributes["percentage"] == 100
    assert hass.states.get("light.ventilador_dani_light").state == "on"
    await hass.services.async_call("fan", "set_percentage",
                                   {"entity_id": "fan.ventilador_dani", "percentage": 34}, blocking=True)
    assert labs.calls["pct"][-1].data == {"entity_id": "fan.ble", "percentage": 33}


# ------------------------------------------------ following the remote


async def _press(hass: HomeAssistant, labs, key: int, bursts: list[list[int]]) -> None:
    for burst in bursts:
        labs.client.emit(key, burst)
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.25)
    await hass.async_block_till_done()


def _somfy_bursts(address: int, button: str, code: int) -> list[list[int]]:
    """As a receiver with ~12 ms idle reports it: one list per frame, without the gaps."""
    timings = somfy.encode(address, button, code, 3)
    bursts, current = [], []
    for t in timings:
        if t < -12_000:
            if current:
                bursts.append(current)
            current = []
        else:
            current.append(t)
    return bursts


async def test_follow_the_real_somfy_remote(hass: HomeAssistant, labs) -> None:
    events = async_capture_events(hass, listen.EVENT)
    assert hass.states.get("cover.persiana_salon").attributes["current_position"] == 100
    await _press(hass, labs, 4, _somfy_bursts(REAL, "down", 500))
    assert hass.states.get("cover.persiana_salon").state == "closing"
    assert labs.r42.sent == []  # nothing sent
    assert events[-1].data == {"device_id": "blind", "name": "Persiana salon", "role": "close",
                               "source": "somfy:ABCDEF", "applied": True}
    await _press(hass, labs, 4, _somfy_bursts(REAL, "my", 501))
    assert [e.data["role"] for e in events] == ["close", "stop"]
    assert hass.states.get("cover.persiana_salon").state == "open"  # stopped part-way
    # The same press heard again (same rolling code) is not applied twice.
    count = len(events)
    await _press(hass, labs, 4, _somfy_bursts(REAL, "my", 501))
    assert len(events) == count


async def test_own_somfy_frames_are_not_followed(hass: HomeAssistant, labs) -> None:
    events = async_capture_events(hass, listen.EVENT)
    await _press(hass, labs, 4, _somfy_bursts(OWN, "down", 99))
    assert events == []


async def test_follow_a_fixed_code_remote(hass: HomeAssistant, labs) -> None:
    events = async_capture_events(hass, listen.EVENT)
    assert hass.states.get("switch.alarma").state == "off"
    await _press(hass, labs, 2, _esphome_bursts(capture(BITS_A, frames=6)))
    assert hass.states.get("switch.alarma").state == "on"
    await _press(hass, labs, 2, _esphome_bursts(capture(BITS_B, frames=6)))
    assert hass.states.get("switch.alarma").state == "off"
    assert [e.data["role"] for e in events] == ["on", "off"]
    assert labs.r92.sent == []


async def test_nothing_is_followed_while_sending(hass: HomeAssistant, labs, monkeypatch) -> None:
    events = async_capture_events(hass, listen.EVENT)
    labs.hub.echo_until = float("inf")
    await _press(hass, labs, 2, _esphome_bursts(capture(BITS_A, frames=6)))
    assert events == []


async def test_resubscribes_after_reconnection(hass: HomeAssistant, labs) -> None:
    link = next(iter(labs.hub.follower._links.values()))
    assert len(labs.client.callbacks) == 1
    labs.client.callbacks.clear()  # the connection dropped with its callbacks
    labs.client._connection = object()  # a new connection
    link._check()
    assert len(labs.client.callbacks) == 1


async def test_learning_uses_the_matching_radio(hass: HomeAssistant, labs, hass_ws_client, monkeypatch) -> None:
    monkeypatch.setattr(rf_tx, "QUIET_AFTER_PRESS", 0.2)
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn", "transmitter": TX42})
    assert (await ws.receive_json())["success"]
    first = (await ws.receive_json(timeout=10))["event"]
    assert first["frequency"] == 433.42


# ---------------------------------------------------------------- model


def test_command_kinds_validate() -> None:
    from custom_components.rf_devices.models import validate_device

    base = {"name": "X", "type": "cover", "options": {}}
    device = validate_device({**base, "somfy": {"address": 5}, "commands": {
        "open": {"kind": "somfy", "button": "up"},
        "close": {"kind": "action", "service": "cover.close_cover", "entity_id": "cover.x"},
        "stop": {"code": CODE_A},
    }})
    assert device["somfy"] == {"address": 5, "invert": False, "repeats": somfy.DEFAULT_REPEATS}
    assert device["commands"]["close"]["data"] == {}
    import voluptuous as vol

    with pytest.raises(vol.Invalid, match="Somfy remote"):
        validate_device({**base, "commands": {"open": {"kind": "somfy", "button": "up"}}})
    with pytest.raises(vol.Invalid):
        validate_device({**base, "commands": {"open": {"kind": "action", "service": "nope"}}})
    with pytest.raises(vol.Invalid):
        validate_device({**base, "commands": {"open": {"kind": "laser"}}})
    with pytest.raises(vol.Invalid):
        validate_device({**base, "somfy": {"address": 0x1000000}})

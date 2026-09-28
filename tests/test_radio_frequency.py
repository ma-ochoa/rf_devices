"""radio_frequency transmitters (HA 2026.5+): sending raw timings and learning through ESPHome."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from aioesphomeapi import RadioFrequencyInfo
from homeassistant.components.radio_frequency import (
    DATA_COMPONENT,
    RadioFrequencyTransmitterEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockEntityPlatform

from custom_components.rf_devices import codec
from custom_components.rf_devices.const import DOMAIN
from custom_components.rf_devices.transmitters import radio_frequency as rf_tx
from custom_components.rf_devices.transmitters.radio_frequency import carrier_for, select_bursts

from .helpers import BITS_A, BITS_B, capture

TX = "radio_frequency.iotorero_433mhz_rf_transmitter"
CODE_A = codec.clean(capture(BITS_A))
CODE_B = codec.clean(capture(BITS_B))


# ---------- codec ----------


def test_timings_round_trip() -> None:
    timings, repeat = codec.to_timings(CODE_A)
    assert repeat == 0
    assert timings[0] > 0 and timings[1] < 0
    assert all((t > 0) == (i % 2 == 0) for i, t in enumerate(timings))
    back = codec.from_timings([timings])
    assert codec.fingerprint(back) == codec.fingerprint(CODE_A)
    assert codec.analyze(back)["good_frames"] == codec.analyze(CODE_A)["good_frames"]


def _esphome_bursts(code: str) -> list[list[int]]:
    """What an ESPHome receiver with a 10 ms idle reports: one list per frame, no trailing pause."""
    timings, _ = codec.to_timings(code)
    bursts, current = [], []
    for t in timings:
        if t < 0 and -t >= codec.MIN_GAP_US:
            bursts.append(current)
            current = []
        else:
            current.append(t)
    if current:
        bursts.append(current)
    return bursts


def test_from_split_bursts_matches_the_broadlink_capture() -> None:
    held = capture(BITS_A, frames=8)
    bursts = _esphome_bursts(held)
    assert len(bursts) == 9  # the cut frame + 8
    kept = select_bursts([[-500, 300, -200]] + bursts + [[120, -80] * 3])
    assert len(kept) == 8  # noise and the cut frame dropped
    code = codec.from_timings(kept)
    result = codec.capture_result(code, 433.92)
    assert result["fingerprint"] == codec.fingerprint(held)
    assert result["raw_analysis"]["bad_frames"] == 0
    assert result["analysis"]["good_frames"] == 8  # clean enough: kept as received
    assert result["analysis"]["bits"] == codec.analyze(CODE_A)["bits"]


def test_from_timings_skips_leading_silence_and_merges_same_sign() -> None:
    code = codec.from_timings([[-9000, 300, 300, -900, 900, -300]])
    pulses = codec.decode(code).pulses
    assert len(pulses) == 4
    assert round(pulses[0] * codec.TICK_US) == pytest.approx(600, abs=33)


def test_from_timings_rejects_nothing() -> None:
    with pytest.raises(codec.CodecError):
        codec.from_timings([[-300, 0]])


def test_carrier_choice() -> None:
    packet = codec.decode(CODE_A)
    assert carrier_for(packet, [(433_920_000, 433_920_000)]) == 433_920_000
    assert carrier_for(packet, [(433_050_000, 434_790_000)]) == 433_920_000
    assert carrier_for(packet, [(433_420_000, 433_420_000)]) == 433_420_000
    with pytest.raises(Exception, match="433.92 MHz"):
        carrier_for(packet, [(868_000_000, 868_600_000)])
    ir = codec.Packet(codec.TYPE_IR, 0, [10, 10])
    with pytest.raises(Exception, match="Only RF"):
        carrier_for(ir, [])


# ---------- Home Assistant ----------


class FakeTransmitter(RadioFrequencyTransmitterEntity):
    _attr_name = "IoTorero 433MHz RF Transmitter"
    _attr_unique_id = "iotorero-rf-tx"
    entity_id = TX

    def __init__(self) -> None:
        self.sent = []

    @property
    def supported_frequency_ranges(self) -> list[tuple[int, int]]:
        return [(433_920_000, 433_920_000)]

    async def async_send_command(self, command) -> None:
        self.sent.append(command)


class FakeClient:
    """Just enough of aioesphomeapi's APIClient."""

    def __init__(self) -> None:
        self.callbacks = []

    def subscribe_infrared_rf_receive(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)

    def emit(self, key: int, timings: list[int]) -> None:
        for callback in list(self.callbacks):
            callback(SimpleNamespace(key=key, device_id=0, timings=timings))


def _devices() -> dict:
    return {
        "lamp": {
            "id": "lamp", "name": "Luz cama", "type": "light", "transmitter": None,
            "options": {"mode": "on_off"},
            "commands": {"on": {"code": CODE_A}, "off": {"code": CODE_B}},
        },
    }


@pytest.fixture
async def rf(hass: HomeAssistant, hass_storage):
    """RF Devices on an ESPHome radio_frequency transmitter with an RF receiver."""
    esphome_entry = MockConfigEntry(domain="esphome")
    esphome_entry.add_to_hass(hass)
    client = FakeClient()
    esphome_entry.runtime_data = SimpleNamespace(
        client=client,
        available=True,
        info={
            RadioFrequencyInfo: {
                1: RadioFrequencyInfo(key=1, capabilities=1, frequency_min=433_920_000, frequency_max=433_920_000),
                2: RadioFrequencyInfo(key=2, capabilities=2, frequency_min=433_920_000, frequency_max=433_920_000),
            }
        },
    )
    assert await async_setup_component(hass, "radio_frequency", {})
    # Added as the ESPHome integration would: platform "esphome", its config entry.
    platform = MockEntityPlatform(hass, domain="radio_frequency", platform_name="esphome")
    platform.config_entry = esphome_entry
    entity = FakeTransmitter()
    await platform.async_add_entities([entity])
    assert entity.entity_id == TX
    assert hass.data[DATA_COMPONENT].get_entity(TX) is entity
    assert er.async_get(hass).async_get(TX).platform == "esphome"

    hass_storage[DOMAIN] = {
        "version": 1, "minor_version": 1, "key": DOMAIN,
        "data": {"devices": _devices(), "frequencies": {}},
    }
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, entity=entity, client=client, esphome=esphome_entry)


async def test_send_through_radio_frequency(hass: HomeAssistant, rf) -> None:
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.luz_cama"}, blocking=True)
    assert len(rf.entity.sent) == 1
    command = rf.entity.sent[0]
    assert command.frequency == 433_920_000
    assert command.repeat_count == 0
    assert command.get_raw_timings() == codec.to_timings(CODE_A)[0]
    assert hass.states.get(TX).state not in (None, "unknown")


async def test_info_lists_radio_frequency_transmitters(hass: HomeAssistant, rf, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/info"})
    info = (await ws.receive_json())["result"]
    tx = next(t for t in info["transmitters"] if t["entity_id"] == TX)
    assert tx["can_learn"] is True
    assert tx["sweeps"] is False


async def _stages(ws) -> tuple[list[str], dict]:
    stages = []
    while True:
        ev = (await ws.receive_json(timeout=10))["event"]
        stages.append(ev["stage"])
        if ev["stage"] in ("captured", "timeout", "error"):
            return stages, ev


async def test_learn_from_esphome(hass: HomeAssistant, rf, hass_ws_client, monkeypatch) -> None:
    monkeypatch.setattr(rf_tx, "QUIET_AFTER_PRESS", 0.2)
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    assert (await ws.receive_json())["success"]
    first = (await ws.receive_json(timeout=10))["event"]
    assert first["stage"] == "press"
    assert first["frequency"] == 433.92

    held = capture(BITS_B, frames=10)
    rf.client.emit(1, [300, -300] * 20)  # the transmitter's key: ignored
    rf.client.emit(2, [200, -150, 90])  # noise: ignored
    for burst in _esphome_bursts(held):
        rf.client.emit(2, burst)
        await asyncio.sleep(0.01)
    stages, ev = await _stages(ws)
    assert stages == ["captured"]
    assert ev["frequency"] == 433.92
    assert ev["analysis"]["bits"] == codec.analyze(CODE_B)["bits"]
    assert ev["analysis"]["good_frames"] == codec.DEFAULT_FRAMES
    assert ev["fingerprint"] == codec.fingerprint(held)
    assert rf.client.callbacks == []  # unsubscribed


async def test_learn_timeout_unsubscribes(hass: HomeAssistant, rf, hass_ws_client, monkeypatch) -> None:
    monkeypatch.setattr(rf_tx, "LEARN_TIMEOUT", 0.2)
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    assert (await ws.receive_json())["success"]
    stages, _ = await _stages(ws)
    assert stages == ["press", "timeout"]
    assert rf.client.callbacks == []


async def test_learn_refused_without_receiver(hass: HomeAssistant, rf, hass_ws_client) -> None:
    rf.esphome.runtime_data.info[RadioFrequencyInfo].pop(2)
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert "no RF receiver" in msg["error"]["message"]


async def test_learn_refused_when_disconnected(hass: HomeAssistant, rf, hass_ws_client) -> None:
    rf.esphome.runtime_data.available = False
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/learn"})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert "not connected" in msg["error"]["message"]

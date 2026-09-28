"""Live meter readings and the settle criterion."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_devices import calibration as cal
from custom_components.rf_devices.meter import Meter

URL = "http://192.168.1.50:80/rpc/Switch.GetStatus?id=0"


def _shelly(hass: HomeAssistant, **data) -> str:
    entry = MockConfigEntry(domain="shelly", data={"host": "192.168.1.50", "gen": 2, **data})
    entry.add_to_hass(hass)
    ent = er.async_get(hass).async_get_or_create(
        "sensor", "shelly", "FCB46733BC08-switch:0-power", config_entry=entry,
        suggested_object_id="terraza_switch_0_power",
    )
    hass.states.async_set(ent.entity_id, "4.0", {"unit_of_measurement": "W"})
    return ent.entity_id


async def test_reads_shelly_live(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL, json={"id": 0, "apower": 4.37, "current": 0.031})
    meter = Meter(hass, _shelly(hass))
    assert meter.direct
    assert await meter.async_read() == 4.37


async def test_falls_back_to_ha_state_per_read(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL, status=500)
    meter = Meter(hass, _shelly(hass))
    assert await meter.async_read() == 4.0  # device failed: HA's value this time
    assert meter.direct  # and it asks the device again next time
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json={"apower": 3.6})
    assert await meter.async_read() == 3.6


async def test_password_or_other_meters_use_ha_state(hass: HomeAssistant) -> None:
    assert not Meter(hass, _shelly(hass, password="x")).direct
    hass.states.async_set("sensor.other_power", "12.5")
    meter = Meter(hass, "sensor.other_power")
    assert not meter.direct
    assert await meter.async_read() == 12.5


class _Ramp:
    """Live meter that rises 1 W every 20 s for 3 min, then stays flat."""

    direct = True

    def __init__(self) -> None:
        self.t = -1.0

    async def async_read(self) -> float:
        self.t += 1.0
        return round(5 + min(self.t, 180) / 20, 2)


async def _no_sleep(_seconds) -> None:
    return None


async def test_slow_ramp_is_not_settled(monkeypatch) -> None:
    # One reading per simulated second, without really waiting.
    monkeypatch.setattr(cal, "asyncio", SimpleNamespace(sleep=_no_sleep))
    watts, took, settled = await cal.async_wait_motor(_Ramp())
    assert settled
    assert took >= 180  # waited for the ramp to end
    assert watts == 14.0


async def test_live_meter_subscription(hass: HomeAssistant, hass_ws_client, aioclient_mock) -> None:
    from custom_components.rf_devices import websocket_api as wsapi

    wsapi.async_register(hass)
    aioclient_mock.get(URL, json={"apower": 36.4})
    entity = _shelly(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/meter/live", "entity_id": entity})
    assert (await ws.receive_json())["success"]
    ev = (await ws.receive_json(timeout=5))["event"]
    assert ev == {"watts": 36.4, "direct": True}


async def test_reads_shelly_gen1_live(hass: HomeAssistant, aioclient_mock) -> None:
    entry = MockConfigEntry(domain="shelly", data={"host": "192.168.1.60", "gen": 1, "model": "SHSW-PM"})
    entry.add_to_hass(hass)
    ent = er.async_get(hass).async_get_or_create(
        "sensor", "shelly", "F4CFA2E37DD7-relay_0-power", config_entry=entry,
        suggested_object_id="luz_matrimonio_power",
    )
    hass.states.async_set(ent.entity_id, "22.0", {"unit_of_measurement": "W"})
    aioclient_mock.get("http://192.168.1.60:80/status", json={"meters": [{"power": 22.53, "is_valid": True}]})
    meter = Meter(hass, ent.entity_id)
    assert meter.direct
    assert await meter.async_read() == 22.53


class _Fast:
    """A fast motor: overshoots, then flat after ~20 s (bedroom fan, real shape)."""

    direct = True

    def __init__(self) -> None:
        self.t = -1.0

    async def async_read(self) -> float:
        self.t += 1.0
        if self.t < 5:
            return 22.7 + self.t * 4
        if self.t < 20:
            return round(43.8 - (self.t - 5) * 0.16, 2)
        return 41.45


async def test_fast_motor_settles_by_itself(monkeypatch) -> None:
    monkeypatch.setattr(cal, "asyncio", SimpleNamespace(sleep=_no_sleep))
    watts, took, settled = await cal.async_wait_motor(_Fast())
    assert settled and watts == 41.5  # rounded to 0.1 W
    assert took <= 45  # no fixed minute: a fast fan is done in well under a minute


async def test_readings_are_shared_between_callers(hass: HomeAssistant, aioclient_mock, monkeypatch) -> None:
    from custom_components.rf_devices import meter as meter_mod

    monkeypatch.setattr(meter_mod, "SHARE_FOR", 5)
    aioclient_mock.get(URL, json={"apower": 4.37})
    entity = _shelly(hass)
    assert await Meter(hass, entity).async_read() == 4.37
    assert await Meter(hass, entity).async_read() == 4.37  # another caller, same second
    assert aioclient_mock.call_count == 1  # the device was asked once

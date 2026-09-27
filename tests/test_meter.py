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

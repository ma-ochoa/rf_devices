"""Shelly relay adapter: detection, detaching and the fallback script."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_devices.relays import GenericAdapter, ShellyAdapter, get_adapter

RPC = "http://192.168.1.50:80/rpc"


def _shelly(hass: HomeAssistant, **data) -> str:
    entry = MockConfigEntry(domain="shelly", data={"host": "192.168.1.50", "gen": 2, **data})
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    relay = reg.async_get_or_create("switch", "shelly", "FCB46733BC08-switch:0", config_entry=entry,
                                    suggested_object_id="terraza_switch_0")
    reg.async_get_or_create("binary_sensor", "shelly", "FCB46733BC08-input:0-input", config_entry=entry,
                            suggested_object_id="terraza_input_0_input")
    reg.async_get_or_create("sensor", "shelly", "FCB46733BC08-switch:0-power", config_entry=entry,
                            suggested_object_id="terraza_switch_0_power")
    return relay.entity_id


async def test_detects_shelly_and_suggests_entities(hass: HomeAssistant) -> None:
    adapter = get_adapter(hass, _shelly(hass))
    assert isinstance(adapter, ShellyAdapter)
    caps = adapter.capabilities
    assert caps.set_detach and caps.fallback_script and caps.live_power
    assert adapter.suggested_input() == "binary_sensor.terraza_input_0_input"
    assert adapter.suggested_meter() == "sensor.terraza_switch_0_power"
    assert "binary_sensor.terraza_input_0_input" in adapter.related_entities()


async def test_password_protected_shelly_is_limited(hass: HomeAssistant) -> None:
    caps = get_adapter(hass, _shelly(hass, password="x")).capabilities
    assert not caps.set_detach and not caps.fallback_script


async def test_other_relays_are_generic(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.sonoff_relay", "on")
    assert isinstance(get_adapter(hass, "switch.sonoff_relay"), GenericAdapter)


async def test_detach_and_script(hass: HomeAssistant, aioclient_mock) -> None:
    adapter = get_adapter(hass, _shelly(hass))
    calls: list[tuple[str, dict]] = []

    async def rpc(method, params=None, timeout=None):
        calls.append((method, params or {}))
        if method == "Switch.GetConfig":
            return {"in_mode": "flip"}
        if method == "Script.List":
            return {"scripts": []}
        if method == "Script.Create":
            return {"id": 3}
        return {}

    adapter._rpc = rpc  # noqa: SLF001
    assert await adapter.async_get_detached() is False
    await adapter.async_set_detached(True)
    assert calls[-1] == ("Switch.SetConfig", {"id": 0, "config": {"in_mode": "detached"}})
    await adapter.async_install_fallback()
    methods = [m for m, _ in calls]
    assert methods[-5:] == ["Script.List", "Script.Create", "Script.PutCode", "Script.SetConfig",
                            "Script.Start"]
    code = "".join(p["code"] for m, p in calls if m == "Script.PutCode")
    assert "Switch.Toggle" in code and "function ack()" in code and "__" not in code
    assert "let WAIT_MS = 2000;" in code and "KVS" not in code  # no flash writes
    calls.clear()
    await adapter.async_ack()
    assert calls == [("Script.Eval", {"id": 3, "code": "ack()"})]

"""Modes A and B of a fan wired behind a relay and a wall switch."""

from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rf_devices import codec
from custom_components.rf_devices import relay as relay_mod
from custom_components.rf_devices.const import DOMAIN

from .helpers import capture

TX = "remote.rm_pro"
RELAY, WALL, METER = "switch.relay", "binary_sensor.wall_input", "sensor.fan_power"
CODES = {k: codec.clean(capture(format(i + 17, "024b"))) for i, k in enumerate(
    ["power", "s1", "s2", "light", "color", "up", "down"]
)}


class Room:
    """Relay + fan + lamp. The lamp lights when the relay gets power."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass, self.relay, self.light, self.speed, self.last = hass, True, False, 0, 1
        self.rf: list[str] = []
        self.drop_next_light = False  # simulate an RF command the receiver missed
        self.memory = False  # lamp keeps its previous state when it gets power
        self.remembered = False

    def publish(self) -> None:
        watts = (37.0 if self.light else 0) + (3.5 * self.speed) if self.relay else 0
        self.hass.states.async_set(RELAY, "on" if self.relay else "off")
        self.hass.states.async_set(METER, str(watts), {"unit_of_measurement": "W"})

    async def relay_call(self, call: ServiceCall) -> None:
        on = call.service == "turn_on"
        if on and not self.relay:
            self.speed = 0  # power-up: fan stopped; lamp on, unless it has memory
            self.light = self.remembered if self.memory else True
        if not on and self.relay:
            self.remembered = self.light
        if not on:
            self.light, self.speed = False, 0
        self.relay = on
        self.publish()

    async def rf_call(self, call: ServiceCall) -> None:
        code = call.data["command"][0].removeprefix("b64:")
        role = next((k for k, v in CODES.items() if v == code), "held")
        self.rf.append(role)
        if not self.relay:
            return
        if role == "light":
            if self.drop_next_light:
                self.drop_next_light = False
                return
            self.light = not self.light
        elif role == "power":
            self.speed = 0 if self.speed else self.last
        elif role in ("s1", "s2"):
            self.speed = self.last = int(role[1])
        self.publish()


def _device(**options) -> dict:
    return {
        "id": "terr", "name": "Terraza", "type": "fan",
        "options": {
            "speeds": 2, "power": "toggle", "light": "toggle", "light_name": "Luz de la terraza",
            "light_state_entity": METER, "light_state_threshold": 20,
            "power_entity": RELAY, "switch_entity": WALL,
            **options,
        },
        "commands": {"power": {"code": CODES["power"]}, "speed_1": {"code": CODES["s1"]},
                     "speed_2": {"code": CODES["s2"]}, "light_toggle": {"code": CODES["light"]},
                     "light_color": {"code": CODES["color"]}, "light_up": {"code": CODES["up"]},
                     "light_down": {"code": CODES["down"]}},
    }


async def _setup(hass: HomeAssistant, hass_storage, monkeypatch, **options) -> SimpleNamespace:
    monkeypatch.setattr(relay_mod, "READY_EXTRA", 0)
    monkeypatch.setattr(relay_mod, "READY_POLL", 0.01)
    monkeypatch.setattr(relay_mod, "LIGHT_CHECK_DELAY", 0.05)
    monkeypatch.setattr(relay_mod, "LAMP_ON_WAIT", 0.02)
    monkeypatch.setattr(relay_mod, "LAMP_CONFIRM_GAP", 0.02)
    room = Room(hass)
    room.publish()
    hass.states.async_set(WALL, "off")
    hass.states.async_set(TX, "on")
    hass.services.async_register("remote", "send_command", room.rf_call)
    hass.services.async_register("homeassistant", "turn_on", room.relay_call)
    hass.services.async_register("homeassistant", "turn_off", room.relay_call)
    hass_storage[DOMAIN] = {"version": 1, "minor_version": 1, "key": DOMAIN,
                            "data": {"devices": {"terr": _device(**options)}, "frequencies": {}}}
    entry = MockConfigEntry(domain=DOMAIN, data={"transmitter": TX}, options={"min_interval": 0})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, room=room)


async def call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)


LIGHT, FAN = "light.luz_de_la_terraza", "fan.terraza"


async def test_mode_a_light_powers_relay_fan_refused(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled")
    t.room.relay = False
    t.room.publish()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError):
        await call(hass, "fan", "turn_on", FAN)
    assert not t.room.relay
    await call(hass, "light", "turn_on", LIGHT)
    assert t.room.relay and t.room.light and t.room.rf == []
    assert hass.states.get(LIGHT).state == "on"


async def test_fan_power_on_switches_the_lamp_back_off(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", fan_power_on=True,
                     power_up_delay=0.05)
    t.room.relay = False
    t.room.publish()
    await hass.async_block_till_done()
    await call(hass, "fan", "set_percentage", FAN, percentage=100)
    assert t.room.relay
    assert t.room.rf == ["light", "s2"]  # lamp off first, then the fan
    assert not t.room.light and t.room.speed == 2
    assert hass.states.get(LIGHT).state == "off"
    assert hass.states.get(FAN).state == "on"


async def test_mode_b_wall_switch_toggles_lamp_by_rf(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached")
    for state, lamp in (("on", True), ("off", False), ("on", True)):
        hass.states.async_set(WALL, state)
        await hass.async_block_till_done()
        assert t.room.light is lamp
        assert hass.states.get(LIGHT).state == ("on" if lamp else "off")
    assert t.room.relay  # the relay never moved
    assert t.room.rf == ["light", "light", "light"]


async def test_mode_b_double_flip_cuts_power(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached", wall_actions={"1": "light_toggle", "2": "power_off"},
                     wall_window=0.1)
    await call(hass, "fan", "set_percentage", FAN, percentage=50)
    hass.states.async_set(WALL, "on")
    hass.states.async_set(WALL, "off")
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert not t.room.relay
    assert hass.states.get(FAN).state == "off"
    # A single flip toggles the lamp (powering the relay, since it is off).
    hass.states.async_set(WALL, "on")
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert t.room.relay and t.room.light


async def test_idle_off_respects_time_and_window(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached",
                     idle_off_minutes=30, idle_off_when="hours", idle_off_from="23:00", idle_off_to="07:00")
    ctrl = t.entry.runtime_data.relays["terr"]
    day = dt.datetime(2026, 9, 27, 15, 0, tzinfo=dt.UTC)
    night = dt.datetime(2026, 9, 27, 23, 30, tzinfo=dt.UTC)
    monkeypatch.setattr(relay_mod.dt_util, "as_local", lambda value: value)
    await ctrl.async_check_idle(day)
    await ctrl.async_check_idle(day + dt.timedelta(minutes=40))
    assert t.room.relay  # idle long enough, but outside the window
    await ctrl.async_check_idle(night)
    assert not t.room.relay  # idle since the afternoon: off as the window opens

    # Fresh idle period inside the window: waits the full 30 minutes.
    await call(hass, "light", "turn_on", LIGHT)
    await call(hass, "light", "turn_off", LIGHT)
    assert t.room.relay
    await ctrl.async_check_idle(night)
    await ctrl.async_check_idle(night + dt.timedelta(minutes=10))
    assert t.room.relay
    await ctrl.async_check_idle(night + dt.timedelta(minutes=31))
    assert not t.room.relay


def test_window_crossing_midnight() -> None:
    at = lambda h, m: dt.datetime(2026, 1, 1, h, m)  # noqa: E731
    assert relay_mod.in_window(at(23, 30), "23:00", "07:00")
    assert relay_mod.in_window(at(3, 0), "23:00", "07:00")
    assert not relay_mod.in_window(at(12, 0), "23:00", "07:00")
    assert relay_mod.in_window(at(12, 0), "09:00", "18:00")


async def test_hide_sources_and_give_them_back(hass, hass_storage, monkeypatch) -> None:
    reg = er.async_get(hass)
    relay_entry = reg.async_get_or_create("switch", "demo", "relay1", suggested_object_id="relay")
    assert relay_entry.entity_id == RELAY
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", hide_sources=True)
    assert reg.async_get(RELAY).hidden_by == er.RegistryEntryHider.INTEGRATION
    assert hass.states.get(RELAY) is not None  # still working
    hub = t.entry.runtime_data
    device = dict(hub.store.devices["terr"])
    device["options"] = {**device["options"], "hide_sources": False}
    await hub.store.async_upsert(device)
    await hass.config_entries.async_reload(t.entry.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get(RELAY).hidden_by is None


async def test_light_colour_temperature_and_brightness(hass, hass_storage, monkeypatch) -> None:
    """What Alexa uses: colour temperature in Kelvin and brightness in %."""
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached",
                     light_color=True, light_colors=3, light_color_names=["Frío", "Neutro", "Cálido"],
                     light_dim=True, light_dim_time=4)
    state = hass.states.get(LIGHT)
    assert state.attributes["supported_color_modes"] == ["color_temp"]
    assert state.attributes["min_color_temp_kelvin"] == 2700
    assert state.attributes["max_color_temp_kelvin"] == 6000
    await call(hass, "light", "turn_on", LIGHT, color_temp_kelvin=2800)
    assert t.room.rf == ["light", "color", "color"]  # on, then Frío -> Neutro -> Cálido
    state = hass.states.get(LIGHT)
    assert state.attributes["color_temp_kelvin"] == 2700
    assert hass.states.get("select.luz_de_la_terraza_colour_temperature").state == "Cálido"
    t.room.rf.clear()
    await call(hass, "light", "turn_on", LIGHT, brightness_pct=50)
    assert t.room.rf == ["held"]  # dimmer held for about half the full-range time
    assert hass.states.get(LIGHT).attributes["brightness"] == 128


async def test_take_the_relays_name_and_give_it_back(hass, hass_storage, monkeypatch, hass_ws_client) -> None:
    hass.config.language = "es"
    reg = er.async_get(hass)
    reg.async_get_or_create("switch", "demo", "relay1", suggested_object_id="relay")
    reg.async_update_entity(RELAY, name="Luz de la Terraza")
    await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled")
    ws = await hass_ws_client(hass)

    async def save(**changes):
        await ws.send_json_auto_id({"type": "rf_devices/devices"})
        device = (await ws.receive_json())["result"][0]
        device["options"].update(changes)
        await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
        msg = await ws.receive_json()
        assert msg["success"], msg
        await hass.async_block_till_done()
        return msg["result"]

    result = await save(take_relay_name=True)
    assert result["options"]["light_name"] == "Luz de la Terraza"
    assert reg.async_get(RELAY).name == "Interruptor luz de la Terraza"
    assert hass.states.get(LIGHT).name == "Luz de la Terraza"
    await save(fan_power_on=True)  # other edits keep the swap
    assert reg.async_get(RELAY).name == "Interruptor luz de la Terraza"
    result = await save(take_relay_name=False)
    assert result["options"]["light_name"] == "Luz de la terraza"  # as before
    assert reg.async_get(RELAY).name == "Luz de la Terraza"

    # Names already swapped by hand: ticking recognises it, unticking restores.
    reg.async_update_entity(RELAY, name="Interruptor luz de la terraza")
    result = await save(take_relay_name=True, light_name="Luz de la terraza")
    assert reg.async_get(RELAY).name == "Interruptor luz de la terraza"
    assert result["options"]["light_name"] == "Luz de la terraza"
    await save(take_relay_name=False)
    assert reg.async_get(RELAY).name == "Luz de la terraza"


async def test_fan_power_on_saved_from_panel_is_used(hass, hass_storage, monkeypatch, hass_ws_client) -> None:
    """Regression: ticking "allow powering to start the fan" in mode A and saving."""
    t = await _setup(hass, hass_storage, monkeypatch, power_up_delay=0.05)  # legacy → A
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "rf_devices/devices"})
    device = (await ws.receive_json())["result"][0]
    device["options"]["fan_power_on"] = True
    await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert msg["result"]["options"]["fan_power_on"] is True
    await hass.async_block_till_done()
    t.room.relay = False
    t.room.publish()
    await hass.async_block_till_done()
    await call(hass, "fan", "turn_on", FAN)
    assert t.room.relay and t.room.speed == 1


async def test_power_up_wait_meter_stops_early(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", fan_power_on=True,
                     power_up_delay=5, power_up_wait_meter=True)
    t.room.relay = False
    t.room.publish()
    await hass.async_block_till_done()
    loop = hass.loop
    start = loop.time()
    await call(hass, "fan", "turn_on", FAN)
    assert loop.time() - start < 1  # the lamp was seen at once, not 5 s
    assert t.room.rf == ["light", "s1"]


async def test_per_device_command_interval(hass, hass_storage, monkeypatch) -> None:
    from custom_components.rf_devices import hub as hub_mod

    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled")
    hub = t.entry.runtime_data
    waits: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds):
        waits.append(round(seconds, 1))
        await real_sleep(0)

    monkeypatch.setattr(hub_mod.asyncio, "sleep", fake_sleep)
    await hub.async_send(CODES["light"], interval=2.0)
    await hub.async_send(CODES["light"], interval=2.0)
    assert waits and 1.5 <= waits[-1] <= 2.0


async def test_lamp_off_is_resent_if_the_receiver_missed_it(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", fan_power_on=True,
                     power_up_delay=0.02, power_up_gap=0.02)
    t.room.relay = False
    t.room.publish()
    await hass.async_block_till_done()
    t.room.drop_next_light = True  # the first "light off" after power-up is lost
    await call(hass, "fan", "set_percentage", FAN, percentage=50)
    await asyncio.sleep(0.2)
    await hass.async_block_till_done()
    assert t.room.rf == ["light", "s1", "light"]  # sent again by the check
    assert not t.room.light and t.room.speed == 1
    assert hass.states.get(LIGHT).state == "off"


async def test_colour_after_power_cut(hass, hass_storage, monkeypatch) -> None:
    from custom_components.rf_devices import select as select_mod

    names = {"light_color": True, "light_colors": 3, "light_color_names": ["Frío", "Neutro", "Cálido"]}
    sel = "select.luz_de_la_terraza_colour_temperature"

    async def cycle(t, quick=True):
        t.room.relay = False
        t.room.publish()
        await hass.async_block_till_done()
        if not quick:
            monkeypatch.setattr(select_mod, "QUICK_CYCLE", -1)
        t.room.relay = True
        t.room.publish()
        await hass.async_block_till_done()
        monkeypatch.setattr(select_mod, "QUICK_CYCLE", 3.0)

    for mode, quick, expected in (("memory", True, "Cálido"), ("fixed", True, "Frío"),
                                  ("quick_cycle", True, "Frío"), ("quick_cycle", False, "Cálido")):
        hass_storage.clear()
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_remove(entry.entry_id)
        t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled",
                         light_color_power_up=mode, **names)
        await call(hass, "light", "turn_on", LIGHT)
        await call(hass, "select", "select_option", sel, option="Cálido")
        await cycle(t, quick)
        assert hass.states.get(sel).state == expected, mode


async def test_wall_only_toggles_the_fan_light_by_rf(hass, hass_storage, monkeypatch) -> None:
    """Bedroom: fan always powered, detached Shelly input only reports the wall switch."""
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="wall_only", power_entity=None)
    assert t.entry.runtime_data.relays == {}
    for state, lamp in (("on", True), ("off", False)):
        hass.states.async_set(WALL, state)
        await hass.async_block_till_done()
        assert t.room.light is lamp
    assert t.room.rf == ["light", "light"]


async def test_take_the_relays_entity_id_and_give_it_back(hass, hass_storage, monkeypatch, hass_ws_client) -> None:
    """Alexa knows "light.relay" as the terrace light: give that id to the RF light."""
    hass.config.language = "es"
    reg = er.async_get(hass)
    reg.async_get_or_create("light", "demo", "relay_light", suggested_object_id="relay_light")
    relay = "light.relay_light"  # registry only: a real entity would move its state along
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", power_entity=relay)
    ws = await hass_ws_client(hass)

    async def save(**changes):
        await ws.send_json_auto_id({"type": "rf_devices/devices"})
        device = (await ws.receive_json())["result"][0]
        device["options"].update(changes)
        await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
        msg = await ws.receive_json()
        assert msg["success"], msg
        await hass.async_block_till_done()
        return msg["result"]

    result = await save(take_relay_name=True, take_relay_entity_id=True)
    assert reg.async_get(relay).platform == DOMAIN  # our light now answers to the relay's id
    assert reg.async_get("light.interruptor_relay_light").platform == "demo"
    assert result["options"]["power_entity"] == "light.interruptor_relay_light"
    assert t.entry.runtime_data.relays["terr"].relay == "light.interruptor_relay_light"
    result = await save(take_relay_entity_id=False, take_relay_name=False)
    assert reg.async_get(relay).platform == "demo"
    assert reg.async_get(LIGHT).platform == DOMAIN
    assert result["options"]["power_entity"] == relay


async def test_unticking_the_name_gives_everything_back(hass, hass_storage, monkeypatch, hass_ws_client) -> None:
    """Names swapped by hand, then entity ids taken; unticking only the name undoes both."""
    hass.config.language = "es"
    reg = er.async_get(hass)
    reg.async_get_or_create("light", "demo", "relay_light", suggested_object_id="relay_light")
    relay = "light.relay_light"
    reg.async_update_entity(relay, name="Interruptor luz de la terraza")  # swapped by hand
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", power_entity=relay,
                     light_name="Luz de la terraza")
    ws = await hass_ws_client(hass)

    async def save(**changes):
        await ws.send_json_auto_id({"type": "rf_devices/devices"})
        device = (await ws.receive_json())["result"][0]
        device["options"].update(changes)
        await ws.send_json_auto_id({"type": "rf_devices/device/save", "device": device})
        msg = await ws.receive_json()
        assert msg["success"], msg
        await hass.async_block_till_done()
        return msg["result"]

    await save(take_relay_name=True, take_relay_entity_id=True)
    assert reg.async_get(relay).platform == DOMAIN
    result = await save(take_relay_name=False)  # the entity-id box is left ticked
    assert result["options"]["take_relay_entity_id"] is False
    assert reg.async_get(relay).platform == "demo"
    assert reg.async_get(relay).name == "Luz de la terraza"  # the relay's original name
    assert result["options"]["light_name"] == "Luz terraza"  # a name of its own, not the relay's
    assert result["options"]["power_entity"] == relay
    assert t.entry.runtime_data.relays["terr"].relay == relay


async def _cut_and_restore(hass, room) -> None:
    """The wall switch (mode A) cuts and restores the relay."""
    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": RELAY}, blocking=True)
    await hass.async_block_till_done()
    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": RELAY}, blocking=True)
    await hass.async_block_till_done()
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()


async def test_lamp_with_memory_is_switched_on_at_power_up(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", power_up_delay=0.01)
    t.room.memory, t.room.light = True, False
    t.room.remembered = False
    await _cut_and_restore(hass, t.room)
    assert t.room.light  # RF Devices saw no lamp draw and switched it on
    assert t.room.rf == ["light"]
    assert hass.states.get(LIGHT).state == "on"


async def test_lamp_that_lights_by_itself_gets_no_command(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", power_up_delay=0.01)
    await _cut_and_restore(hass, t.room)
    assert t.room.light and t.room.rf == []


async def test_ensure_light_on_can_be_turned_off(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", power_up_delay=0.01,
                     ensure_light_on_power_up=False)
    t.room.memory, t.room.remembered = True, False
    await _cut_and_restore(hass, t.room)
    assert not t.room.light and t.room.rf == []


async def test_power_up_for_the_fan_does_not_switch_the_lamp_on(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", fan_power_on=True,
                     power_up_delay=0.01, power_up_gap=0.01)
    t.room.relay = False
    t.room.publish()
    await hass.async_block_till_done()
    await call(hass, "fan", "set_percentage", FAN, percentage=50)
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()
    assert not t.room.light and t.room.speed == 1


async def test_slow_lamp_is_not_switched_off_by_mistake(hass, hass_storage, monkeypatch) -> None:
    """The lamp lights a moment after the first check: no command must be sent."""
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled", power_up_delay=0.01)
    monkeypatch.setattr(relay_mod, "LAMP_CONFIRM_GAP", 0.1)
    real_turn_on = t.room.relay_call

    async def slow_lamp(call):
        await real_turn_on(call)
        if call.service == "turn_on":
            t.room.light = False
            t.room.publish()

            async def lights_later():
                await asyncio.sleep(0.05)
                t.room.light = True
                t.room.publish()

            hass.async_create_task(lights_later())

    hass.services.async_register("homeassistant", "turn_on", slow_lamp)
    await _cut_and_restore(hass, t.room)
    assert t.room.light and t.room.rf == []


async def test_mode_b_confirms_every_press_to_the_fallback_script(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached", fallback_script=True)
    ctrl = t.entry.runtime_data.relays["terr"]
    acks = []

    async def ack():
        acks.append(hass.loop.time())

    monkeypatch.setattr(type(ctrl.adapter), "capabilities",
                        property(lambda self: relay_mod.RelayAdapter.capabilities.fget(self).__class__(fallback_script=True)))
    monkeypatch.setattr(ctrl.adapter, "async_ack", ack)
    hass.states.async_set(WALL, "on")
    await hass.async_block_till_done()
    assert len(acks) == 1 and t.room.light  # confirmed, and the lamp toggled by RF


async def _flips(hass, n: int, settle: float = 0.25) -> None:
    for _ in range(n):
        new = "off" if hass.states.get(WALL).state == "on" else "on"
        hass.states.async_set(WALL, new)
        await hass.async_block_till_done()
    await asyncio.sleep(settle)
    await hass.async_block_till_done()


GESTURES = {"1": "light_toggle", "2": "fan_step", "3": "fan_off", "4": "none"}


async def test_gestures_light_fan_step_bounce_and_off(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached",
                     wall_actions=GESTURES, wall_window=0.1)
    events = []
    hass.bus.async_listen("rf_devices_wall_gesture", lambda e: events.append(e.data["flips"]))
    await _flips(hass, 1)
    assert t.room.light and t.room.rf == ["light"]
    await _flips(hass, 2)  # fan off → on at speed 1
    assert t.room.speed == 1
    await _flips(hass, 2)  # → 2 (the top)
    assert t.room.speed == 2
    await _flips(hass, 2)  # at the top: back down
    assert t.room.speed == 1
    await _flips(hass, 2)  # at the bottom: up again
    assert t.room.speed == 2
    await _flips(hass, 3)
    assert t.room.speed == 0 and hass.states.get(FAN).state == "off"
    assert t.room.light and t.room.relay  # lamp and relay untouched
    await _flips(hass, 4)  # nothing
    assert t.room.rf == ["light", "s1", "s2", "s1", "s2", "power"]
    assert events == [1, 2, 2, 2, 2, 3, 4]


async def test_single_action_acts_without_waiting(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached",
                     wall_actions={"1": "light_toggle"}, wall_window=2.0)
    hass.states.async_set(WALL, "on")
    await hass.async_block_till_done()
    assert t.room.light  # no 2 s wait: nothing else to wait for


async def test_every_flip_is_confirmed_before_the_gesture_ends(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached", fallback_script=True,
                     wall_actions=GESTURES, wall_window=0.3)
    ctrl = t.entry.runtime_data.relays["terr"]
    acks = []

    async def ack():
        acks.append(hass.loop.time())

    monkeypatch.setattr(type(ctrl.adapter), "capabilities",
                        property(lambda self: relay_mod.RelayAdapter.capabilities.fget(self).__class__(fallback_script=True)))
    monkeypatch.setattr(ctrl.adapter, "async_ack", ack)
    hass.states.async_set(WALL, "on")
    await hass.async_block_till_done()
    assert len(acks) == 1 and not t.room.light  # confirmed at once, gesture still open
    hass.states.async_set(WALL, "off")
    await hass.async_block_till_done()
    assert len(acks) == 2
    await asyncio.sleep(0.4)
    await hass.async_block_till_done()
    assert t.room.speed == 1 and not t.room.light


async def test_wall_only_gestures(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="wall_only", power_entity=None,
                     wall_actions=GESTURES, wall_window=0.1)
    await _flips(hass, 2)
    assert t.room.speed == 1
    await _flips(hass, 1)
    assert t.room.light
    await _flips(hass, 3)
    assert t.room.speed == 0


async def test_five_or_more_flips_count_as_four(hass, hass_storage, monkeypatch) -> None:
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached", wall_window=0.1,
                     wall_actions={"1": "light_toggle", "2": "fan_step", "3": "fan_off", "4": "fan_off"})
    await _flips(hass, 2)
    assert t.room.speed == 1
    await _flips(hass, 5)
    assert t.room.speed == 0 and not t.room.light


async def test_saving_an_old_copy_is_refused(hass, hass_storage, monkeypatch, hass_ws_client) -> None:
    await _setup(hass, hass_storage, monkeypatch, relay_mode="detached")
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "rf_devices/devices"})
    old = next(d for d in (await ws.receive_json())["result"] if d["id"] == "terr")
    newer = {**old, "options": {**old["options"], "fallback_wait": 1.0}}
    await ws.send_json({"id": 2, "type": "rf_devices/device/save", "device": newer})
    saved = (await ws.receive_json())["result"]
    assert saved["rev"] == old["rev"] + 1
    await hass.async_block_till_done()
    # A panel still holding the old copy must not undo that change.
    await ws.send_json({"id": 3, "type": "rf_devices/device/save", "device": old})
    msg = await ws.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "stale"
    # Saving the current copy works.
    await ws.send_json({"id": 4, "type": "rf_devices/device/save", "device": {**saved, "name": "Terraza"}})
    assert (await ws.receive_json())["success"]


async def test_diagnostics_summarise_devices(hass, hass_storage, monkeypatch) -> None:
    from custom_components.rf_devices.diagnostics import async_get_config_entry_diagnostics

    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="detached", wall_actions=GESTURES)
    diag = await async_get_config_entry_diagnostics(hass, t.entry)
    device = diag["devices"][0]
    assert device["relay"]["mode"] == "detached"
    assert device["relay"]["wall_gestures"]["actions"][2] == "fan_step"
    assert device["commands"]["speed_1"]["kind"] == "rf433"
    assert "code" not in device["commands"]["speed_1"]  # codes are summarised, not included


async def test_own_entities_cannot_be_the_relay(hass, hass_storage, monkeypatch, hass_ws_client) -> None:
    """Choosing the device's own light as its relay (and taking its name) renamed it after itself."""
    await _setup(hass, hass_storage, monkeypatch, relay_mode="coupled")
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "rf_devices/devices"})
    device = (await ws.receive_json())["result"][0]
    bad = {**device, "options": {**device["options"], "power_entity": LIGHT, "take_relay_name": True}}
    await ws.send_json({"id": 2, "type": "rf_devices/device/save", "device": bad})
    msg = await ws.receive_json()
    assert not msg["success"] and "RF Devices entity" in msg["error"]["message"]
    state = hass.states.get(LIGHT)
    assert state is not None and state.name == "Luz de la terraza"  # untouched


async def test_quick_light_calibration_follows_the_lamp(hass, hass_storage, monkeypatch) -> None:
    from custom_components.rf_devices import light as light_mod

    monkeypatch.setattr(light_mod, "FAN_QUIET", 0)
    monkeypatch.setattr(light_mod, "LAMP_COMMAND_GRACE", 0)
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="none", power_entity=None,
                     light_calibration={"idle": 0.0, "light": 37.0})
    assert hass.states.get(LIGHT).state == "off"
    t.room.light = True  # someone used the original remote, fan stopped
    t.room.publish()
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == "on"
    await call(hass, "fan", "set_percentage", FAN, percentage=100)  # motor adds 7 W
    t.room.publish()
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == "on"  # a motor change is not the lamp
    t.room.light = False  # remote again, with the fan running: a -37 W jump
    t.room.publish()
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == "off"


async def test_lamp_rechecked_after_the_fan_settles(hass, hass_storage, monkeypatch) -> None:
    """The lamp lit while the fan was changing, and the meter then stayed flat: check again later."""
    from custom_components.rf_devices import light as light_mod

    monkeypatch.setattr(light_mod, "FAN_QUIET", 0.3)
    monkeypatch.setattr(light_mod, "LAMP_COMMAND_GRACE", 0)
    t = await _setup(hass, hass_storage, monkeypatch, relay_mode="none", power_entity=None,
                     light_calibration={"idle": 0.0, "light": 37.0})
    await call(hass, "fan", "set_percentage", FAN, percentage=50)
    await call(hass, "fan", "turn_off", FAN)  # fan just changed: readings are not trusted yet
    t.room.light, t.room.speed = True, 0
    t.room.publish()
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == "off"  # too soon
    await asyncio.sleep(1.0)  # no new meter report; the deferred check reads it again
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == "on"

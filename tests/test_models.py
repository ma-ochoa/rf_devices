"""Device model tests."""

import pytest
import voluptuous as vol

from custom_components.rf_devices.models import entity_plan, missing_roles, roles, validate_device

from .helpers import BITS_A, capture


def test_light_toggle_defaults() -> None:
    d = validate_device({"name": "Luz cama", "type": "light"})
    assert len(d["id"]) == 8
    assert {k: d["options"][k] for k in ("mode", "switch_entity", "state_entity", "power_entity")} == {
        "mode": "toggle", "switch_entity": None, "state_entity": None, "power_entity": None,
    }
    assert d["options"]["idle_off_minutes"] == 0 and d["options"]["fan_power_on"] is False
    assert [s["role"] for s in roles(d)] == ["toggle"]
    assert missing_roles(d) == ["toggle"]
    assert entity_plan(d) == [("light", "light"), ("button", "sync_light")]
    d["options"]["state_entity"] = "sensor.lamp_power"
    assert entity_plan(d) == [("light", "light"), ("sensor", "power")]  # feedback: no sync button


def test_fan_with_light_and_extra_button() -> None:
    code = capture(BITS_A)
    d = validate_device(
        {
            "name": "Ventilador",
            "type": "fan",
            "options": {"speeds": 2, "light": "toggle"},
            "commands": {"off": {"code": "b64:" + code}, "x_timer": {"code": code, "label": "Timer"}},
        }
    )
    assert d["commands"]["off"]["code"] == code  # prefix stripped
    assert [s["role"] for s in roles(d)] == ["off", "speed_1", "speed_2", "light_toggle", "x_timer"]
    assert missing_roles(d) == ["speed_1", "speed_2", "light_toggle"]
    assert entity_plan(d) == [
        ("fan", "fan"), ("light", "fan_light"), ("button", "sync_fan_light"), ("button", "x_timer")
    ]


def test_fan_toggle_power_direction_presets() -> None:
    d = validate_device(
        {
            "name": "Ventilador cama",
            "type": "fan",
            "options": {"speeds": 6, "power": "toggle", "direction": "buttons", "presets": ["Brisa"]},
        }
    )
    assert [s["role"] for s in roles(d)] == [
        "power", "speed_1", "speed_2", "speed_3", "speed_4", "speed_5", "speed_6",
        "forward", "reverse", "preset_1",
    ]
    assert ("button", "sync_fan") in entity_plan(d)
    d = validate_device({"name": "x", "type": "fan", "options": {"direction": "toggle"}})
    assert "direction" in [s["role"] for s in roles(d)]


def test_invalid() -> None:
    with pytest.raises(vol.Invalid):
        validate_device({"name": "x", "type": "toaster"})
    with pytest.raises(vol.Invalid):
        validate_device({"name": "x", "type": "light", "commands": {"toggle": {"code": "zzz"}}})
    with pytest.raises(vol.Invalid):
        validate_device({"name": "x", "type": "light", "commands": {"Bad Role": {"code": capture(BITS_A)}}})

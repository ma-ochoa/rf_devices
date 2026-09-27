"""Integration services that correct assumed state without transmitting."""

from __future__ import annotations

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import live_entities

SET_STATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required("is_on"): cv.boolean,
        vol.Optional("percentage"): vol.All(vol.Coerce(int), vol.Range(0, 100)),
    }
)
SET_COLOR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required("option"): cv.string,
    }
)
SET_POSITION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(0, 100)),
    }
)


def _targets(hass: HomeAssistant, call: ServiceCall, method: str) -> list:
    entities = live_entities(hass)
    found = []
    for entity_id in call.data[ATTR_ENTITY_ID]:
        entity = entities.get(entity_id)
        if entity is None or not hasattr(entity, method):
            raise ServiceValidationError(f"{entity_id} is not a suitable RF Devices entity")
        found.append(entity)
    return found


@callback
def async_register(hass: HomeAssistant) -> None:
    async def set_state(call: ServiceCall) -> None:
        for entity in _targets(hass, call, "async_set_assumed_state"):
            if "percentage" in call.data and hasattr(entity, "_speeds"):
                await entity.async_set_assumed_state(call.data["is_on"], call.data["percentage"])
            else:
                await entity.async_set_assumed_state(call.data["is_on"])

    async def set_position_state(call: ServiceCall) -> None:
        for entity in _targets(hass, call, "async_set_assumed_position"):
            await entity.async_set_assumed_position(call.data["position"])

    async def set_color_mode(call: ServiceCall) -> None:
        for entity in _targets(hass, call, "async_set_measured"):
            options = entity.options
            if call.data["option"] not in options:
                raise ServiceValidationError(f"{call.data['option']} is not one of {options}")
            entity.async_set_measured(options.index(call.data["option"]))

    hass.services.async_register(DOMAIN, "set_state", set_state, SET_STATE_SCHEMA)
    hass.services.async_register(DOMAIN, "set_color_mode", set_color_mode, SET_COLOR_SCHEMA)
    hass.services.async_register(DOMAIN, "set_position_state", set_position_state, SET_POSITION_SCHEMA)

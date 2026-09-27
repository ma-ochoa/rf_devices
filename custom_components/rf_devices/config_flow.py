"""Config flow: pick the Broadlink remote that sends (and learns) the codes."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_MIN_INTERVAL,
    CONF_POWER_SWITCH,
    CONF_TRANSMITTER,
    DEFAULT_MIN_INTERVAL,
    DOMAIN,
)

TRANSMITTER_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="remote"))


class RFDevicesConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if self.hass.states.get(user_input[CONF_TRANSMITTER]) is None:
                errors[CONF_TRANSMITTER] = "not_found"
            else:
                return self.async_create_entry(title="RF Devices", data=user_input)

        default = next(
            (s.entity_id for s in self.hass.states.async_all("remote")), None
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_TRANSMITTER, default=default): TRANSMITTER_SELECTOR}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RFDevicesOptionsFlow()


class RFDevicesOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRANSMITTER, default=current[CONF_TRANSMITTER]): TRANSMITTER_SELECTOR,
                    vol.Required(
                        CONF_MIN_INTERVAL,
                        default=current.get(CONF_MIN_INTERVAL, DEFAULT_MIN_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=5, step=0.1, unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_POWER_SWITCH,
                        description={"suggested_value": current.get(CONF_POWER_SWITCH)},
                    ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
                }
            ),
        )

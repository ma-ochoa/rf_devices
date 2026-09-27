"""Binary sensor on the device page: whether the relay feeding it is on."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .entity import RFEntity, setup_platform_entities

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_platform_entities(hass, entry, async_add_entities, "binary_sensor", RFPoweredSensor)


class RFPoweredSensor(RFEntity, BinarySensorEntity):
    _attr_translation_key = "powered"
    _attr_device_class = BinarySensorDeviceClass.POWER

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self.power_entity], self._changed)
        )

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        state = self.hass.states.get(self.power_entity)
        return state is not None and state.state in (STATE_ON, STATE_OFF)

    @property
    def is_on(self) -> bool:
        return self.powered

    @callback
    def power_changed(self, on: bool) -> None:
        """Already handled by _changed."""

    @property
    def extra_state_attributes(self) -> dict:
        return {"source": self.power_entity}

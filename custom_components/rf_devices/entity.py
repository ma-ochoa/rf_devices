"""Base entity of every RF Devices entity."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from . import codec
from .const import ATTR_HOLD, DEFAULT_DIM_HOLD, DOMAIN, MANUFACTURER, ROLE_LIGHT_DOWN, ROLE_LIGHT_UP
from .hub import RFHub
from .models import device_model, entity_plan, light_device_id, on_light_device


class RFEntity(RestoreEntity, Entity):
    """An entity driven by stored RF codes.

    RF is one-way, so the state is what RF Devices last sent. It is not flagged
    as ``assumed_state`` because dashboards would then show two on/off buttons
    instead of a toggle; ``rf_devices.set_state`` corrects it when needed.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: RFHub, device: dict, key: str) -> None:
        self.hub = hub
        self.device = device
        self._key = key
        self._attr_unique_id = f"{device['id']}_{key}"
        language = hub.hass.config.language
        if on_light_device(device, key):
            # A fan's named light is a device of its own in Home Assistant.
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, light_device_id(device))},
                name=device["options"]["light_name"],
                manufacturer=MANUFACTURER,
                model=device_model({"type": "light"}, language),
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, device["id"])},
                name=device["name"],
                manufacturer=MANUFACTURER,
                model=device_model(device, language),
            )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        live_entities(self.hass)[self.entity_id] = self
        if self.power_entity:
            self.async_on_remove(
                async_track_state_change_event(self.hass, [self.power_entity], self._power_event)
            )

    @property
    def relay(self):
        """The relay controller of this device (modes A/B), if it is wired to one."""
        return self.hub.relays.get(self.device["id"])

    # --- power relay -------------------------------------------------------
    @property
    def power_entity(self) -> str | None:
        """Relay feeding the device; relay.py decides when it may be switched."""
        return self.device["options"].get("power_entity")

    @property
    def powered(self) -> bool:
        """False only when the relay is known to be off; unknown counts as powered."""
        if not self.power_entity:
            return True
        state = self.hass.states.get(self.power_entity)
        return state is None or state.state != STATE_OFF

    def require_power(self) -> None:
        if not self.powered:
            raise HomeAssistantError(
                f"{self.device['name']} has no power: {self.power_entity} is off"
            )

    @callback
    def _power_event(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if new is None or new.state not in (STATE_ON, STATE_OFF):
            return
        if old is not None and old.state == new.state:
            return
        self.power_changed(new.state == STATE_ON)
        self.async_write_ha_state()

    @callback
    def power_changed(self, on: bool) -> None:
        """The relay feeding the device was switched; update the known state."""

    async def async_will_remove_from_hass(self) -> None:
        live_entities(self.hass).pop(self.entity_id, None)
        await super().async_will_remove_from_hass()

    def code(self, role: str) -> str | None:
        cmd = self.device.get("commands", {}).get(role)
        return cmd["code"] if cmd else None

    async def async_send_role(
        self, role: str, hold: float | None = None, interval: float | None = None
    ) -> None:
        cmd = self.device.get("commands", {}).get(role)
        if cmd is None:
            raise HomeAssistantError(
                f"{self.device['name']}: command '{role}' has not been learned"
            )
        code = cmd["code"]
        if hold is None:
            hold = cmd.get(ATTR_HOLD) or (
                DEFAULT_DIM_HOLD if role in (ROLE_LIGHT_UP, ROLE_LIGHT_DOWN) else 0
            )
        if hold:
            code = codec.hold(code, hold)
        await self.hub.async_send(
            code,
            self.hub.transmitter_for(self.device),
            interval if interval is not None else self.device.get("command_interval"),
        )


def setup_platform_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    platform: str,
    factory: Callable[[RFHub, dict, str], Entity | None],
) -> None:
    """Create this platform's entities for every stored device."""
    hub: RFHub = entry.runtime_data
    entities = []
    for device in hub.store.devices.values():
        for plat, key in entity_plan(device):
            if plat == platform and (entity := factory(hub, device, key)) is not None:
                entities.append(entity)
    async_add_entities(entities)


@callback
def live_entities(hass: HomeAssistant) -> dict[str, RFEntity]:
    """RF Devices entities currently in HA, by entity_id (used by services)."""
    return hass.data.setdefault(DOMAIN, {}).setdefault("entities", {})


@callback
def last_on(state) -> bool | None:
    if state is None or state.state not in ("on", "off"):
        return None
    return state.state == "on"


def feedback_on(state: State | None, threshold: float) -> bool | None:
    """Read a feedback entity: on/off entities directly, numbers against ``threshold``.

    Returns None when the entity is missing or its value is not usable.
    """
    if state is None:
        return None
    if state.state in (STATE_ON, STATE_OFF):
        return state.state == STATE_ON
    try:
        return float(state.state) > threshold
    except ValueError:
        return None


@callback
def find_by_unique_id(hass: HomeAssistant, unique_id: str) -> RFEntity | None:
    return next((e for e in live_entities(hass).values() if e.unique_id == unique_id), None)

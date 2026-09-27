"""Button entities: extra remote buttons (``x_*``) and sync buttons (``sync_*``)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EXTRA_PREFIX, LIGHT_EXTRA_ROLES, ROLE_LIGHT_COLOR, SYNC_PREFIX, TIMER_PREFIX
from .entity import RFEntity, find_by_unique_id, setup_platform_entities

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(hub, device, key):
        return RFSyncButton(hub, device, key) if key.startswith(SYNC_PREFIX) else RFButton(hub, device, key)

    setup_platform_entities(hass, entry, async_add_entities, "button", factory)


class RFButton(RFEntity, ButtonEntity):
    """Sends one remote button (optionally held for its configured time)."""

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        if key.startswith(TIMER_PREFIX):
            timers = device["options"].get("timers", [])
            index = int(key.removeprefix(TIMER_PREFIX)) - 1
            self._attr_translation_key = "timer"
            self._attr_translation_placeholders = {
                "label": timers[index] if index < len(timers) else str(index + 1)
            }
        elif key in LIGHT_EXTRA_ROLES:
            self._attr_translation_key = key
        else:
            label = device["commands"][key].get("label")
            self._attr_name = label or key.removeprefix(EXTRA_PREFIX).replace("_", " ").capitalize()

    async def async_press(self) -> None:
        self.require_power()
        await self.async_send_role(self._key)
        if self._key == ROLE_LIGHT_COLOR:
            # Keep the remembered colour mode in step with the lamp.
            select = find_by_unique_id(self.hass, f"{self.device['id']}_color")
            if select is not None:
                select.advance()


class RFSyncButton(RFEntity, ButtonEntity):
    """Flips the state of a toggle-only entity in HA without transmitting.

    For when the original remote was used and HA shows the opposite state.
    """

    _attr_icon = "mdi:sync"

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        self._target_key = key.removeprefix(SYNC_PREFIX)
        self._attr_translation_key = "sync_fan" if self._target_key == "fan" else (
            "sync_fan_light" if self._target_key == "fan_light" else "sync"
        )

    async def async_press(self) -> None:
        target = find_by_unique_id(self.hass, f"{self.device['id']}_{self._target_key}")
        if target is None or not hasattr(target, "async_sync"):
            raise HomeAssistantError("Nothing to sync")
        await target.async_sync()

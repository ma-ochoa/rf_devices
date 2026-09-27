"""RF Devices: learn, clean and use Broadlink RF codes from a visual panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from . import services, websocket_api
from .const import DOMAIN, MANUFACTURER, PANEL_URL, PLATFORMS, STATIC_URL, VERSION
from .hub import RFHub
from .models import device_model, entity_plan, registry_device_ids
from .relay import RelayController, relay_mode
from .store import RFStore
from .wall import WallGestures

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type RFConfigEntry = ConfigEntry[RFHub]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
    )
    websocket_api.async_register(hass)
    services.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RFConfigEntry) -> bool:
    store = RFStore(hass)
    await store.async_load()
    hub = entry.runtime_data = RFHub(hass, entry, store)
    _prune_registries(hass, entry, store)
    for device in store.devices.values():
        if relay_mode(device) in ("coupled", "detached"):
            hub.relays[device["id"]] = RelayController(hass, hub, device)
    await _async_sync_hidden(hass, store, hub)
    dev_reg = dr.async_get(hass)
    for device in store.devices.values():
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device["id"])},
            name=device["name"],
            manufacturer=MANUFACTURER,
            model=device_model(device, hass.config.language),
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for controller in hub.relays.values():
        entry.async_on_unload(controller.async_start())
    for device in store.devices.values():
        # Always powered, only a wall switch: its flips are read here.
        if relay_mode(device) == "wall_only" and device["options"].get("switch_entity"):
            wall = WallGestures(hass, device, device["options"]["switch_entity"])
            entry.async_on_unload(wall.async_start())
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if PANEL_URL not in hass.data.get(frontend.DATA_PANELS, {}):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="rf-devices-panel",
            module_url=f"{STATIC_URL}/rf-devices-panel.js?v={VERSION}",
            sidebar_title="RF Devices",
            sidebar_icon="mdi:remote",
            require_admin=True,
            config={},
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RFConfigEntry) -> bool:
    # The panel stays registered across reloads; it is removed with the entry.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RFConfigEntry) -> None:
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    store = RFStore(hass)
    await store.async_load()
    store.devices = {}
    await _async_sync_hidden(hass, store, None)  # give back what was hidden


async def _async_options_updated(hass: HomeAssistant, entry: RFConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _prune_registries(hass: HomeAssistant, entry: ConfigEntry, store: RFStore) -> None:
    """Remove devices and entities that are no longer in the store."""
    wanted_entities = {
        f"{device['id']}_{key}"
        for device in store.devices.values()
        for _, key in entity_plan(device)
    }
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id not in wanted_entities:
            ent_reg.async_remove(ent.entity_id)
    wanted_devices = set().union(*(registry_device_ids(d) for d in store.devices.values()))
    dev_reg = dr.async_get(hass)
    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        ids = {i[1] for i in dev.identifiers if i[0] == DOMAIN}
        if not ids & wanted_devices:
            dev_reg.async_remove_device(dev.id)


async def _async_sync_hidden(hass: HomeAssistant, store: RFStore, hub: RFHub | None) -> None:
    """Hide the relay's own entities for devices that ask for it, unhide the rest.

    They stay fully working (RF Devices switches the relay through them); they
    are only hidden from dashboards and pickers so the RF Devices light and fan
    are the ones people see. Only entities RF Devices hid are ever unhidden.
    """
    wanted: set[str] = set()
    for controller in (hub.relays.values() if hub else []):
        if controller.device["options"].get("hide_sources"):
            wanted.add(controller.relay)
            wanted.update(controller.adapter.related_entities())
    reg = er.async_get(hass)
    changed = False
    for entity_id in wanted - set(store.hidden):
        entry = reg.async_get(entity_id)
        if entry is not None and entry.hidden_by is None:
            reg.async_update_entity(entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
            store.hidden.append(entity_id)
            changed = True
    for entity_id in [e for e in store.hidden if e not in wanted]:
        entry = reg.async_get(entity_id)
        if entry is not None and entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
            reg.async_update_entity(entity_id, hidden_by=None)
        store.hidden.remove(entity_id)
        changed = True
    if changed:
        await store.async_save()

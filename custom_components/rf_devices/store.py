"""Persistent storage of the devices, plus export and import."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import EXPORT_FORMAT, STORAGE_KEY, STORAGE_VERSION, VERSION
from .models import new_id, validate_device


class RFStore:
    """Devices live in ``.storage/rf_devices``, so HA backups include them."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.devices: dict[str, dict] = {}
        self.frequencies: dict[str, float] = {}
        # Other integrations' entities RF Devices hid (and must unhide later).
        self.hidden: list[str] = []
        # Last rolling code sent by each Somfy virtual remote, by address ("%06X").
        # Kept apart from the devices: an editor saving an older copy of a
        # device must never take the counter back (the motor ignores old codes).
        self.somfy_codes: dict[str, int] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.devices = data.get("devices", {})
        self.frequencies = data.get("frequencies", {})
        self.hidden = data.get("hidden", [])
        self.somfy_codes = data.get("somfy_codes", {})

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                "devices": self.devices,
                "frequencies": self.frequencies,
                "hidden": self.hidden,
                "somfy_codes": self.somfy_codes,
            }
        )

    def somfy_code(self, address: int) -> int:
        """Last rolling code sent with this address (0 = never used)."""
        return int(self.somfy_codes.get(f"{address:06X}", 0))

    async def async_next_somfy_code(self, address: int) -> int:
        """The rolling code for the next press, saved BEFORE it is sent.

        A press that fails after this only skips a code, which motors accept;
        sending a code twice (after a crash or restart) would be ignored.
        """
        code = (self.somfy_code(address) + 1) & 0xFFFF
        self.somfy_codes[f"{address:06X}"] = code
        await self.async_save()
        return code

    async def async_upsert(self, data: dict) -> dict:
        device = validate_device(data)
        previous = self.devices.get(device["id"])
        device["rev"] = (previous.get("rev", 0) if previous else 0) + 1
        self.devices[device["id"]] = device
        await self.async_save()
        return device

    async def async_delete(self, device_id: str) -> None:
        if self.devices.pop(device_id, None) is not None:
            await self.async_save()

    async def async_remember_frequency(self, transmitter: str, frequency: float) -> None:
        self.frequencies[transmitter] = frequency
        await self.async_save()

    def export(self, device_ids: list[str] | None = None) -> dict:
        devices = [
            copy.deepcopy(d)
            for d in self.devices.values()
            if device_ids is None or d["id"] in device_ids
        ]
        addresses = {f"{d['somfy']['address']:06X}" for d in devices if d.get("somfy")}
        return {
            "format": EXPORT_FORMAT,
            "version": 1,
            "integration_version": VERSION,
            "exported": dt_util.utcnow().isoformat(),
            "devices": devices,
            # The motors only accept codes above the last one they saw.
            "somfy_codes": {a: c for a, c in self.somfy_codes.items() if a in addresses},
        }

    async def async_import(self, data: dict, replace: bool = False) -> dict:
        """Import an export file.

        Devices whose id already exists are overwritten when ``replace`` is
        true, otherwise they are added as copies with a new id. Nothing is
        written unless every device validates.
        """
        if data.get("format") != EXPORT_FORMAT:
            raise vol.Invalid("Not an RF Devices export file")
        incoming = [validate_device(d) for d in data.get("devices", [])]
        added = replaced = 0
        for device in incoming:
            if device["id"] in self.devices:
                if replace:
                    replaced += 1
                else:
                    device["id"] = new_id()
                    device["name"] = f"{device['name']} (2)"
                    added += 1
            else:
                added += 1
            self.devices[device["id"]] = device
        for address, code in (data.get("somfy_codes") or {}).items():
            # Never go back: keep the highest code known for the address.
            self.somfy_codes[address] = max(int(code), int(self.somfy_codes.get(address, 0)))
        await self.async_save()
        return {"added": added, "replaced": replaced}


async def async_read_broadlink_codes(hass: HomeAssistant) -> dict[str, dict[str, dict]]:
    """Codes learned with the core Broadlink integration (read only).

    Returns ``{storage_file: {device: {command: code | [codes]}}}``.
    """
    storage = Path(hass.config.path(".storage"))

    def _list() -> list[str]:
        return sorted(p.name for p in storage.glob("broadlink_remote_*_codes"))

    result: dict[str, dict[str, dict]] = {}
    for key in await hass.async_add_executor_job(_list):
        data = await Store(hass, 1, key).async_load()
        if data:
            result[key] = data
    return result

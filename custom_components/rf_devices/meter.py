"""Reading a power meter, directly from the device when possible.

Home Assistant only learns what a Shelly pushes, and a Shelly pushes power in
~1 W steps, sometimes a minute apart. A ceiling fan's speeds are ~1 W apart
and take minutes to settle, so that is too coarse. Shelly devices answer a
local HTTP call with the live value (Gen2+: RPC; Gen1: ``/status``), so RF
Devices asks them directly and falls back to the HA state for any other meter
(or a password-protected one).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# "<mac>-switch:0-power" → component, channel
_SHELLY_UID = re.compile(r"^[0-9A-Fa-f]{12}-(switch|pm1|em1|cover):(\d+)-(power|current|apower)$")
_METHODS = {
    "switch": ("Switch.GetStatus", "apower"),
    "pm1": ("PM1.GetStatus", "apower"),
    "em1": ("EM1.GetStatus", "act_power"),
    "cover": ("Cover.GetStatus", "apower"),
}
# Gen1: "<mac>-relay_0-power" / "<mac>-emeter_0-power" → /status meters[0].power
_SHELLY_GEN1_UID = re.compile(r"^[0-9A-Fa-f]{12}-(relay|emeter)_(\d+)-(power|current)$")
_GEN1_LISTS = {"relay": "meters", "emeter": "emeters"}
TIMEOUT = aiohttp.ClientTimeout(total=2)
# Several parts may read the same device within a second (aligner, sensor,
# panel): share one answer instead of asking it again. A Shelly measures
# about once per second anyway, and a Gen1 (ESP8266) times out when flooded.
SHARE_FOR = 0.8
_LAST: dict[str, tuple[float, float]] = {}  # url -> (monotonic time, value)


@dataclass
class _Direct:
    url: str
    path: tuple  # keys/indexes into the JSON answer


class Meter:
    """A power meter entity, read live from the device when it allows it."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self._direct = _shelly_source(hass, entity_id)

    @property
    def direct(self) -> bool:
        """True when readings come live from the device."""
        return self._direct is not None

    def state_value(self) -> float | None:
        state = self.hass.states.get(self.entity_id)
        try:
            return float(state.state) if state else None
        except ValueError:
            return None

    async def async_read(self) -> float | None:
        if not self.direct:
            return self.state_value()
        cached = _LAST.get(self._direct.url + repr(self._direct.path))
        if cached and time.monotonic() - cached[0] < SHARE_FOR:
            return cached[1]
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(self._direct.url, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
            for key in self._direct.path:
                data = data[key]
            value = float(data)
            _LAST[self._direct.url + repr(self._direct.path)] = (time.monotonic(), value)
            return value
        except (
            TimeoutError, aiohttp.ClientError, RuntimeError, IndexError, KeyError, TypeError, ValueError
        ) as err:  # RuntimeError: the HTTP session closing while Home Assistant stops
            # Usually a Wi-Fi hiccup: use HA's last value this time, ask again next time.
            _LOGGER.debug("Live reading of %s failed (%r); using HA's value", self.entity_id, err)
            return self.state_value()


def _shelly_source(hass: HomeAssistant, entity_id: str) -> _Direct | None:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != "shelly" or not entry.config_entry_id:
        return None
    config = hass.config_entries.async_get_entry(entry.config_entry_id)
    if config is None:
        return None
    data = config.data
    if data.get("password") or not data.get("host"):
        return None
    port = data.get("port", 80)
    uid = entry.unique_id or ""
    if int(data.get("gen") or 1) >= 2:
        if (match := _SHELLY_UID.match(uid)) is None:
            return None
        method, field = _METHODS[match.group(1)]
        if match.group(3) == "current":
            field = "current"
        return _Direct(f"http://{data['host']}:{port}/rpc/{method}?id={match.group(2)}", (field,))
    if (match := _SHELLY_GEN1_UID.match(uid)) is None or match.group(3) != "power":
        return None
    kind, channel = match.group(1), int(match.group(2))
    return _Direct(f"http://{data['host']}:{port}/status", (_GEN1_LISTS[kind], channel, "power"))

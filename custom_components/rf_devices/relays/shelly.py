"""Shelly Gen2+ (Plus, Pro, Gen3, Gen4): local RPC over HTTP.

* Reads power live (``Switch.GetStatus``), see ``meter.py``.
* Detaches the wall switch: ``Switch.SetConfig`` with ``in_mode`` set to
  ``detached`` (mode B) or ``flip``/``follow`` (mode A).
* Installs a fallback script (mode B): Home Assistant confirms each
  wall-switch press; without a confirmation within a couple of seconds the
  script toggles the relay itself, like a coupled switch.

Password-protected devices are not supported yet (only HA entities are used).
"""

from __future__ import annotations

import re

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base import Capabilities, RelayAdapter

_SWITCH_UID = re.compile(r"^([0-9A-Fa-f]{12})-switch:(\d+)$")
TIMEOUT = aiohttp.ClientTimeout(total=3)
ACK_TIMEOUT = aiohttp.ClientTimeout(total=1)
SCRIPT_NAME = "rfdevices_fallback"
DEFAULT_WAIT_MS = 2000

# Mode B fallback: confirmation per press. The wall switch is read by Home
# Assistant, which confirms every press by calling ack() (Script.Eval) before
# acting. If no confirmation arrives within WAIT_MS (Home Assistant down,
# restarting or hung), the script toggles the relay itself, as if coupled.
# Idle cost: nothing (no timers, no traffic, no flash writes). Per press:
# one timer, and one incoming call from Home Assistant.
FALLBACK_SCRIPT = """// RF Devices fallback (installed by Home Assistant). Mode B: Home Assistant
// confirms each wall-switch press with ack(); without it, toggle the relay.
let SWITCH_ID = __SWITCH__;
let INPUT_ID = __INPUT__;
let WAIT_MS = __WAIT__;
let pending = null;
let early = false;

function ack() {
  if (pending !== null) {
    Timer.clear(pending);
    pending = null;
  } else {
    // The confirmation beat our own event handler: remember it briefly.
    early = true;
    Timer.set(1500, false, function () { early = false; });
  }
}

function onPress() {
  if (early) { early = false; return; }
  if (pending !== null) Timer.clear(pending);
  pending = Timer.set(WAIT_MS, false, function () {
    pending = null;
    Shelly.call("Switch.Toggle", { id: SWITCH_ID });
  });
}

Shelly.addEventHandler(function (ev) {
  if (ev.component !== "input:" + JSON.stringify(INPUT_ID)) return;
  if (ev.info.event !== "toggle") return;
  onPress();
});
"""


class ShellyAdapter(RelayAdapter):
    name = "shelly"
    label = "Shelly (Gen2 or newer)"

    def __init__(self, hass, relay_entity, source_entity, entry) -> None:
        super().__init__(hass, relay_entity, source_entity, entry)
        config = hass.config_entries.async_get_entry(entry.config_entry_id)
        data = config.data if config else {}
        match = _SWITCH_UID.match(entry.unique_id or "")
        self.mac = match.group(1) if match else None
        self.channel = int(match.group(2)) if match else 0
        self.host = data.get("host")
        self.port = data.get("port", 80)
        self.protected = bool(data.get("password"))
        self._script: int | None = None  # id of the fallback script, once known

    @classmethod
    def matches(cls, hass: HomeAssistant, entry: er.RegistryEntry) -> bool:
        if entry.platform != "shelly" or not _SWITCH_UID.match(entry.unique_id or ""):
            return False
        config = hass.config_entries.async_get_entry(entry.config_entry_id or "")
        return config is not None and int(config.data.get("gen") or 1) >= 2

    @property
    def usable(self) -> bool:
        return bool(self.host) and not self.protected

    @property
    def capabilities(self) -> Capabilities:
        if not self.usable:
            return Capabilities(detach=True, notes=["shelly_password"])
        return Capabilities(detach=True, set_detach=True, fallback_script=True, live_power=True)

    # --- RPC -----------------------------------------------------------------
    async def _rpc(
        self, method: str, params: dict | None = None, timeout: aiohttp.ClientTimeout = TIMEOUT
    ) -> dict:
        session = async_get_clientsession(self.hass)
        url = f"http://{self.host}:{self.port}/rpc"
        async with session.post(
            url, json={"id": 1, "method": method, "params": params or {}}, timeout=timeout
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        if "error" in data:
            raise RuntimeError(f"{method}: {data['error']}")
        return data.get("result", data)

    async def async_get_detached(self) -> bool | None:
        if not self.usable:
            return None
        config = await self._rpc("Switch.GetConfig", {"id": self.channel})
        return config.get("in_mode") == "detached"

    async def async_set_detached(self, detached: bool) -> None:
        await self._rpc(
            "Switch.SetConfig",
            {"id": self.channel, "config": {"in_mode": "detached" if detached else "flip"}},
        )

    async def _script_id(self) -> int | None:
        scripts = await self._rpc("Script.List")
        for script in scripts.get("scripts", []):
            if script.get("name") == SCRIPT_NAME:
                return script["id"]
        return None

    async def async_install_fallback(self, wait_ms: int = DEFAULT_WAIT_MS) -> None:
        code = (
            FALLBACK_SCRIPT.replace("__SWITCH__", str(self.channel))
            .replace("__INPUT__", str(self.channel))
            .replace("__WAIT__", str(int(wait_ms)))
        )
        script_id = await self._script_id()
        if script_id is None:
            script_id = (await self._rpc("Script.Create", {"name": SCRIPT_NAME}))["id"]
        else:
            await self._rpc("Script.Stop", {"id": script_id})
        # PutCode accepts the code in chunks; append after the first one.
        chunk = 1024
        for index in range(0, len(code), chunk):
            await self._rpc(
                "Script.PutCode",
                {"id": script_id, "code": code[index:index + chunk], "append": index > 0},
            )
        await self._rpc("Script.SetConfig", {"id": script_id, "config": {"enable": True}})
        await self._rpc("Script.Start", {"id": script_id})
        self._script = script_id

    async def async_remove_fallback(self) -> None:
        script_id = await self._script_id()
        if script_id is not None:
            await self._rpc("Script.Stop", {"id": script_id})
            await self._rpc("Script.Delete", {"id": script_id})
        self._script = None

    async def async_ack(self) -> None:
        """Confirm a wall-switch press to the fallback script (must be fast)."""
        if self._script is None:
            self._script = await self._script_id()
        if self._script is not None:
            await self._rpc("Script.Eval", {"id": self._script, "code": "ack()"}, ACK_TIMEOUT)

    def related_entities(self) -> list[str]:
        """The relay switch and its wall-switch inputs."""
        result = super().related_entities()
        if self.mac is None:
            return result
        reg = er.async_get(self.hass)
        for uid in (f"{self.mac}-switch:{self.channel}", f"{self.mac}-input:{self.channel}-input"):
            for domain in ("switch", "binary_sensor"):
                if (eid := reg.async_get_entity_id(domain, "shelly", uid)) and eid not in result:
                    if eid != self.relay_entity:
                        result.append(eid)
        return result

    def _entity(self, domain: str, suffix: str) -> str | None:
        if self.mac is None:
            return None
        return er.async_get(self.hass).async_get_entity_id(domain, "shelly", f"{self.mac}-{suffix}")

    def suggested_input(self) -> str | None:
        return self._entity("binary_sensor", f"input:{self.channel}-input")

    def suggested_meter(self) -> str | None:
        return self._entity("sensor", f"switch:{self.channel}-power")

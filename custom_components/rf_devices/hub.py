"""Sending codes and learning new ones through a Broadlink remote."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import codec
from .const import (
    CONF_MIN_INTERVAL,
    CONF_POWER_SWITCH,
    CONF_TRANSMITTER,
    DEFAULT_MIN_INTERVAL,
    HEALTH_DELAY,
    HEALTH_TIMEOUT,
    LEARN_COOLDOWN,
    LEARN_TIMEOUT,
    MAX_POLL_MISSES,
    POLL_INTERVAL,
    POWER_BOOT_TIME,
    POWER_OFF_TIME,
)
from .store import RFStore

_LOGGER = logging.getLogger(__name__)

BROADLINK = "broadlink"
NOTIFICATION_ID = "rf_devices_broadlink_health"


class LearnError(HomeAssistantError):
    """Learning could not start or finish."""


@dataclass
class LearnEvent:
    stage: str  # sweep | frequency | press | captured | timeout | error
    data: dict[str, Any]


class RFHub:
    """Shared state of the config entry: store, transmit queue and learner."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: RFStore) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self._lock = asyncio.Lock()
        self._learn_lock = asyncio.Lock()
        self._last_send = 0.0
        self._last_learn = 0.0
        self.calibrating = False
        self.relays: dict = {}  # device id -> RelayController

    @property
    def default_transmitter(self) -> str:
        return self.entry.options.get(CONF_TRANSMITTER) or self.entry.data[CONF_TRANSMITTER]

    @property
    def min_interval(self) -> float:
        return float(self.entry.options.get(CONF_MIN_INTERVAL, DEFAULT_MIN_INTERVAL))

    def transmitter_for(self, device: dict | None) -> str:
        return (device or {}).get("transmitter") or self.default_transmitter

    async def async_send(
        self, code: str, transmitter: str | None = None, interval: float | None = None
    ) -> None:
        """Send one code. Calls are queued, never dropped, and spaced out.

        A toggle-only receiver would read two back-to-back bursts as a single
        long press, so each transmission waits ``min_interval`` after the
        previous one finished.
        """
        codec.decode(code)  # fail early on garbage
        if self.learning:
            raise HomeAssistantError("RF Devices is capturing a code; try again in a moment")
        entity_id = transmitter or self.default_transmitter
        async with self._lock:
            pause = self.min_interval if interval is None else interval
            wait = self._last_send + pause - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                await self.hass.services.async_call(
                    "remote",
                    "send_command",
                    {"entity_id": entity_id, "command": [f"b64:{code}"]},
                    blocking=True,
                )
            finally:
                self._last_send = time.monotonic()

    def _broadlink_device(self, transmitter: str):
        """The core Broadlink integration's device object for a remote entity."""
        entry_id = None
        if (ent := er.async_get(self.hass).async_get(transmitter)) is not None:
            if ent.platform == BROADLINK:
                entry_id = ent.config_entry_id
        if entry_id is None:
            raise LearnError(f"{transmitter} is not a Broadlink remote")
        data = self.hass.data.get(BROADLINK)
        device = getattr(data, "devices", {}).get(entry_id) if data else None
        if device is None or getattr(device, "api", None) is None:
            raise LearnError("The Broadlink integration is not loaded for this remote")
        if not hasattr(device.api, "find_rf_packet"):
            raise LearnError("This Broadlink model cannot learn RF codes")
        return device

    def can_learn(self, transmitter: str) -> bool:
        try:
            self._broadlink_device(transmitter)
        except LearnError:
            return False
        return True

    @property
    def learning(self) -> bool:
        return self._learn_lock.locked()

    async def _async_alive(self, device) -> bool:
        """Ask the Broadlink to identify itself (a harmless discovery packet)."""
        try:
            await asyncio.wait_for(self.hass.async_add_executor_job(device.api.hello), HEALTH_TIMEOUT)
        except Exception:  # noqa: BLE001 - any failure means "not answering"
            return False
        return True

    async def async_learn(
        self, transmitter: str | None = None, frequency: float | None = None
    ) -> AsyncIterator[LearnEvent]:
        """Learn one RF code, yielding progress for the UI.

        Without ``frequency`` the Broadlink first sweeps: the button must be
        held until the frequency is found, released, and pressed once more.
        With a known frequency a single short press is enough.

        Safeguards, because a Broadlink stuck in learning mode may stop
        answering until it is power-cycled:

        * only one capture at a time, with a pause between captures;
        * the Broadlink must answer before learning starts;
        * RF Devices sends nothing while a capture runs;
        * every unfinished capture (timeout, error, cancelled) takes the
          Broadlink out of learning mode;
        * afterwards its health is checked, and if it stopped answering the
          user is notified and, when configured, its plug is power-cycled.
        """
        from broadlink.exceptions import (
            BroadlinkException,
            NetworkTimeoutError,
            ReadError,
            StorageError,
        )

        transmitter = transmitter or self.default_transmitter
        device = self._broadlink_device(transmitter)
        if self._learn_lock.locked():
            raise LearnError("Another capture is already running")

        async with self._learn_lock:
            wait = self._last_learn + LEARN_COOLDOWN - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            if not await self._async_alive(device):
                yield LearnEvent("error", {"reason": "unreachable", "message": "Broadlink not answering"})
                self._last_learn = time.monotonic()
                return
            captured = False
            try:
                # Leave any learning mode a previous, interrupted capture left open.
                await self._async_exit_learning(device)
                if not frequency:
                    await device.async_request(device.api.sweep_frequency)
                    yield LearnEvent("sweep", {})
                    for _ in range(LEARN_TIMEOUT):
                        await asyncio.sleep(1)
                        found, freq = await device.async_request(device.api.check_frequency)
                        if found:
                            # Some models (RM Pro+) report 0: found, but no value.
                            frequency = freq or None
                            break
                    else:
                        yield LearnEvent("timeout", {"during": "sweep"})
                        return
                    if frequency:
                        await self.store.async_remember_frequency(transmitter, frequency)
                    yield LearnEvent("frequency", {"frequency": frequency})
                    await asyncio.sleep(1)

                await device.async_request(device.api.find_rf_packet, frequency)
                yield LearnEvent("press", {"frequency": frequency})
                misses = 0
                for _ in range(int(LEARN_TIMEOUT / POLL_INTERVAL)):
                    # Same pace as the core integration: an RM Pro+ that is
                    # listening copes badly with faster polling.
                    await asyncio.sleep(POLL_INTERVAL)
                    try:
                        raw = await device.async_request(device.api.check_data)
                    except (ReadError, StorageError):
                        misses = 0
                        continue
                    except NetworkTimeoutError:
                        # Busy receiving: give it a moment before giving up.
                        misses += 1
                        if misses > MAX_POLL_MISSES:
                            raise
                        await asyncio.sleep(POLL_INTERVAL)
                        continue
                    captured = True
                    yield LearnEvent("captured", capture_result(codec.to_b64(raw), frequency))
                    return
                yield LearnEvent("timeout", {"during": "press"})
            except (BroadlinkException, OSError) as err:
                _LOGGER.warning("Learning failed: %s", err)
                reason = "unreachable" if isinstance(err, (NetworkTimeoutError, OSError)) else None
                yield LearnEvent("error", {"message": str(err), "reason": reason})
            finally:
                self._last_learn = time.monotonic()
                if not captured:
                    await self._async_exit_learning(device)
                # Checked in the background so a closed subscription cannot skip it.
                self.hass.async_create_background_task(
                    self._async_after_learning(device), "rf_devices health check"
                )

    async def _async_exit_learning(self, device) -> None:
        """Best effort: take the Broadlink out of RF sweep/learning mode."""
        from broadlink.exceptions import BroadlinkException

        try:
            await device.async_request(device.api.cancel_sweep_frequency)
        except (BroadlinkException, OSError) as err:
            _LOGGER.debug("Could not exit learning mode: %s", err)

    async def _async_after_learning(self, device) -> None:
        """Make sure the Broadlink still answers after a capture; try to recover if not."""
        await asyncio.sleep(HEALTH_DELAY)
        if await self._async_alive(device):
            return
        _LOGGER.warning("Broadlink stopped answering after a capture, retrying")
        await self._async_exit_learning(device)
        await asyncio.sleep(HEALTH_DELAY)
        if await self._async_alive(device):
            return
        power = self.entry.options.get(CONF_POWER_SWITCH)
        if power and self.hass.states.get(power) is not None:
            _LOGGER.warning("Power-cycling the Broadlink through %s", power)
            await self.hass.services.async_call("homeassistant", "turn_off", {"entity_id": power}, blocking=True)
            await asyncio.sleep(POWER_OFF_TIME)
            await self.hass.services.async_call("homeassistant", "turn_on", {"entity_id": power}, blocking=True)
            for _ in range(POWER_BOOT_TIME // 5):
                await asyncio.sleep(5)
                if await self._async_alive(device):
                    persistent_notification.async_create(
                        self.hass,
                        "The Broadlink stopped answering after a capture and was restarted "
                        f"by switching {power} off and on. It is working again.",
                        title="RF Devices",
                        notification_id=NOTIFICATION_ID,
                    )
                    return
        persistent_notification.async_create(
            self.hass,
            "The Broadlink is not answering after a capture. Unplug it for a few seconds. "
            "To make RF Devices do this automatically, plug it into a smart plug and choose "
            "that plug in the RF Devices options.",
            title="RF Devices",
            notification_id=NOTIFICATION_ID,
        )


def capture_result(code: str, frequency: float | None) -> dict[str, Any]:
    """Raw capture, its analysis and the cleaned version the UI proposes."""
    analysis = codec.analyze(code)
    cleaned = codec.clean(code) if analysis["needs_cleaning"] else code
    return {
        "frequency": frequency,
        "raw": code,
        "raw_analysis": analysis,
        "code": cleaned,
        "analysis": codec.analyze(cleaned),
        "fingerprint": codec.fingerprint(code),
    }

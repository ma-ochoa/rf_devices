"""``remote`` entities: Broadlink (send and learn) and any other remote (send only)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from homeassistant.components import persistent_notification

from .. import codec
from ..const import (
    CONF_POWER_SWITCH,
    HEALTH_DELAY,
    HEALTH_TIMEOUT,
    LEARN_TIMEOUT,
    MAX_POLL_MISSES,
    POLL_INTERVAL,
    POWER_BOOT_TIME,
    POWER_OFF_TIME,
)
from .base import LearnError, LearnEvent, Transmitter

_LOGGER = logging.getLogger(__name__)

BROADLINK = "broadlink"
NOTIFICATION_ID = "rf_devices_broadlink_health"


class RemoteTransmitter(Transmitter):
    """Sends through ``remote.send_command`` with a ``b64:`` Broadlink packet.

    Learning needs the core Broadlink integration's device object, so it is
    only available when the remote belongs to a Broadlink that can learn RF.
    """

    sweeps = True

    async def async_send(self, code: str) -> None:
        await self.hass.services.async_call(
            "remote",
            "send_command",
            {"entity_id": self.entity_id, "command": [f"b64:{code}"]},
            blocking=True,
        )

    def _device(self):
        """The core Broadlink integration's device object for this remote."""
        if self.platform != BROADLINK:
            raise LearnError(f"{self.entity_id} is not a Broadlink remote")
        data = self.hass.data.get(BROADLINK)
        device = getattr(data, "devices", {}).get(self.registry_entry.config_entry_id) if data else None
        if device is None or getattr(device, "api", None) is None:
            raise LearnError("The Broadlink integration is not loaded for this remote")
        if not hasattr(device.api, "find_rf_packet"):
            raise LearnError("This Broadlink model cannot learn RF codes")
        return device

    def learn_problem(self) -> str | None:
        try:
            self._device()
        except LearnError as err:
            return str(err)
        return None

    async def _async_alive(self, device) -> bool:
        """Ask the Broadlink to identify itself (a harmless discovery packet)."""
        try:
            await asyncio.wait_for(self.hass.async_add_executor_job(device.api.hello), HEALTH_TIMEOUT)
        except Exception:  # noqa: BLE001 - any failure means "not answering"
            return False
        return True

    async def async_learn(self, frequency: float | None) -> AsyncIterator[LearnEvent]:
        """Learn one RF code with the Broadlink.

        Without ``frequency`` the Broadlink first sweeps: the button must be
        held until the frequency is found, released, and pressed once more.
        With a known frequency a single short press is enough.

        Safeguards, because a Broadlink stuck in learning mode may stop
        answering until it is power-cycled:

        * the Broadlink must answer before learning starts;
        * every unfinished capture (timeout, error, cancelled) takes the
          Broadlink out of learning mode;
        * afterwards its health is checked, and if it stopped answering the
          user is notified and, when configured, its plug is power-cycled.

        The hub adds the rest: one capture at a time, a pause between
        captures and nothing sent while a capture runs.
        """
        from broadlink.exceptions import (
            BroadlinkException,
            NetworkTimeoutError,
            ReadError,
            StorageError,
        )

        device = self._device()
        if not await self._async_alive(device):
            yield LearnEvent("error", {"reason": "unreachable", "message": "Broadlink not answering"})
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
                    await self.hub.store.async_remember_frequency(self.entity_id, frequency)
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
                yield LearnEvent("captured", codec.capture_result(codec.to_b64(raw), frequency))
                return
            yield LearnEvent("timeout", {"during": "press"})
        except (BroadlinkException, OSError) as err:
            _LOGGER.warning("Learning failed: %s", err)
            reason = "unreachable" if isinstance(err, (NetworkTimeoutError, OSError)) else None
            yield LearnEvent("error", {"message": str(err), "reason": reason})
        finally:
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
        power = self.hub.entry.options.get(CONF_POWER_SWITCH)
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

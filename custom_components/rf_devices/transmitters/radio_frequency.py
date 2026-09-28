"""``radio_frequency`` entities (Home Assistant 2026.5+): any RF adapter HA knows.

Sending goes through the core ``radio_frequency`` helper, so it works with
every integration that provides such an entity (ESPHome ``ir_rf_proxy``
devices such as the Athom/IoTorero RF-IR remote, Broadlink…). Codes are
converted from the stored Broadlink packet to signed microseconds.

Home Assistant has no RF *receiver* entity yet, so learning listens to the
ESPHome device directly: an ``ir_rf_proxy`` receiver on the same device
streams every burst it hears as raw timings. A fixed-frequency receiver
needs no sweep: one press is enough.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator

from homeassistant.exceptions import HomeAssistantError

from .. import codec, debug
from ..const import LEARN_TIMEOUT
from .base import LearnError, LearnEvent, Transmitter

_LOGGER = logging.getLogger(__name__)

ESPHOME = "esphome"
RF_RECEIVER = 1 << 1  # aioesphomeapi RadioFrequencyCapability.RECEIVER

# Carrier used when the stored code says 433 or 315 MHz but not the exact value.
DEFAULT_FREQUENCY = {codec.TYPE_RF433: 433_920_000, codec.TYPE_RF315: 315_000_000}

# A press is over when nothing new arrives for this long…
QUIET_AFTER_PRESS = 0.6
# …or, at most, this long after the first burst (a held button).
MAX_PRESS = 3.0
# Bursts whose length differs from the most common one by more than this are noise.
LENGTH_TOLERANCE = 0.1


def carrier_for(packet: codec.Packet, ranges: list[tuple[int, int]]) -> int:
    """The carrier to ask for: the band's usual one, moved into the transmitter's range.

    A Broadlink code only says "433" or "315 MHz" (its sweep value is not
    reliable), and fixed-frequency adapters accept exactly one value.
    """
    if packet.type not in DEFAULT_FREQUENCY:
        raise HomeAssistantError("Only RF codes can be sent through a radio_frequency transmitter")
    wanted = DEFAULT_FREQUENCY[packet.type]
    if not ranges or any(low <= wanted <= high for low, high in ranges):
        return wanted
    low, high = min(ranges, key=lambda r: min(abs(r[0] - wanted), abs(r[1] - wanted)))
    if min(abs(low - wanted), abs(high - wanted)) > 5_000_000:
        raise HomeAssistantError(
            f"This transmitter does not work at {wanted / 1_000_000:g} MHz"
        )
    return min(max(wanted, low), high)


def select_bursts(bursts: list[list[int]]) -> list[list[int]]:
    """Keep the bursts that look like the remote: long enough and of the usual length."""
    long_enough = [b for b in bursts if sum(1 for v in b if v) >= codec.MIN_RECEIVED_PULSES]
    if not long_enough:
        return []
    usual, _ = Counter(len(b) for b in long_enough).most_common(1)[0]
    margin = max(2, round(usual * LENGTH_TOLERANCE))
    return [b for b in long_enough if abs(len(b) - usual) <= margin]


class RadioFrequencyTransmitter(Transmitter):
    """Sends through Home Assistant's ``radio_frequency`` domain."""

    def _ranges(self) -> list[tuple[int, int]]:
        from homeassistant.components.radio_frequency import DATA_COMPONENT

        component = self.hass.data.get(DATA_COMPONENT)
        entity = component.get_entity(self.entity_id) if component else None
        if entity is None:
            raise HomeAssistantError(f"{self.entity_id} is not available")
        return list(entity.supported_frequency_ranges)

    async def async_send(self, code: str) -> None:
        from homeassistant.components.radio_frequency import async_send_command
        from rf_protocols.commands.ook import OOKCommand

        packet = codec.decode(code)
        timings, repeat = codec.to_timings(code)
        command = OOKCommand(
            frequency=carrier_for(packet, self._ranges()), timings=timings, repeat_count=repeat
        )
        debug.trace(
            self.hass, "rf_send", transmitter=self.entity_id, carrier=command.frequency,
            repeat=repeat, pulses=len(timings), timings=debug.clip(timings),
        )
        await async_send_command(self.hass, self.entity_id, command)
        # Some adapters (ESPHome) return before the radio is done. Wait for
        # the burst to end so the hub's pause between codes starts after it.
        await asyncio.sleep(sum(abs(t) for t in timings) * (repeat + 1) / 1_000_000)

    # ---------- learning (ESPHome only) ----------

    def _esphome(self):
        """The ESPHome runtime data and the keys of its RF receivers."""
        if self.platform != ESPHOME:
            raise LearnError(
                "Only ESPHome devices can learn through a radio_frequency transmitter"
            )
        entry = self.hass.config_entries.async_get_entry(self.registry_entry.config_entry_id)
        data = getattr(entry, "runtime_data", None) if entry else None
        if data is None or not hasattr(data, "client"):
            raise LearnError("The ESPHome integration is not loaded for this device")
        receivers = {
            info.key: info
            for infos in getattr(data, "info", {}).values()
            for info in infos.values()
            if type(info).__name__ == "RadioFrequencyInfo"
            and getattr(info, "capabilities", 0) & RF_RECEIVER
        }
        if not receivers:
            raise LearnError(
                "This ESPHome device has no RF receiver (ir_rf_proxy with remote_receiver_id)"
            )
        if not getattr(data, "available", False):
            raise LearnError("The ESPHome device is not connected")
        return data, receivers

    def learn_problem(self) -> str | None:
        try:
            self._esphome()
        except LearnError as err:
            return str(err)
        return None

    async def async_learn(self, frequency: float | None) -> AsyncIterator[LearnEvent]:
        data, receivers = self._esphome()
        debug.trace(self.hass, "rx_receivers", receivers=[debug.info_dict(i) for i in receivers.values()])
        info = next(iter(receivers.values()))
        fixed = info.frequency_min if info.frequency_min and info.frequency_min == info.frequency_max else 0
        frequency_mhz = round(fixed / 1_000_000, 2) if fixed else None

        bursts: list[list[int]] = []
        first: float | None = None
        last = 0.0
        arrived = asyncio.Event()

        def on_receive(event) -> None:
            nonlocal first, last
            timings = list(event.timings)
            ignored = None
            if event.key not in receivers:
                ignored = "other receiver (IR?)"
            elif sum(1 for v in timings if v) < codec.MIN_RECEIVED_PULSES:
                ignored = "too short (noise)"
            debug.trace(
                self.hass, "rx", key=event.key, pulses=len(timings), ignored=ignored,
                timings=debug.clip(timings),
            )
            if ignored:
                return
            now = time.monotonic()
            first = first or now
            last = now
            bursts.append(timings)
            arrived.set()

        try:
            unsubscribe = data.client.subscribe_infrared_rf_receive(on_receive)
        except Exception as err:  # noqa: BLE001 - aioesphomeapi raises its own errors
            yield LearnEvent("error", {"message": str(err), "reason": "unreachable"})
            return
        try:
            yield LearnEvent("press", {"frequency": frequency_mhz})
            try:
                await asyncio.wait_for(arrived.wait(), LEARN_TIMEOUT)
            except TimeoutError:
                yield LearnEvent("timeout", {"during": "press"})
                return
            while True:
                now = time.monotonic()
                if now - last >= QUIET_AFTER_PRESS or now - first >= MAX_PRESS:
                    break
                await asyncio.sleep(0.1)
        finally:
            unsubscribe()

        kept = select_bursts(bursts)
        _LOGGER.debug("Received %d bursts, kept %d: %s", len(bursts), len(kept), bursts)
        if not kept:
            yield LearnEvent("timeout", {"during": "press"})
            return
        yield LearnEvent("captured", codec.capture_result(codec.from_timings(kept), frequency_mhz))

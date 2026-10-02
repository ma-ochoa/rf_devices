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
BROADLINK = "broadlink"
DATA_RECEIVERS = "rf_devices_esphome_receivers"  # entry id -> (runtime data, {key: info})
LIST_TIMEOUT = 10  # seconds for the device to list its entities

# Carrier used when the stored code says 433 or 315 MHz but not the exact value.
DEFAULT_FREQUENCY = {codec.TYPE_RF433: 433_920_000, codec.TYPE_RF315: 315_000_000}

# A press is over when nothing new arrives for this long…
QUIET_AFTER_PRESS = 0.6
# …or, at most, this long after the first burst (a held button).
MAX_PRESS = 3.0
# Bursts whose length differs from the most common one by more than this are noise.
LENGTH_TOLERANCE = 0.1
# A capture needs the same frame at least this many times: a remote repeats it, noise does not.
MIN_REPEATS = 2


def fit_carrier(wanted: int, ranges: list[tuple[int, int]]) -> int:
    """The carrier to ask for: ``wanted`` moved into the transmitter's range.

    Fixed-frequency adapters accept exactly one value; one within 5 MHz is
    used instead (e.g. a 433.92 MHz module for a 433.42 MHz Somfy motor: it
    may work at a short distance). A range of (0, 0) means "not declared".
    """
    ranges = [(low, high) for low, high in ranges if high > 0]
    if not ranges or any(low <= wanted <= high for low, high in ranges):
        return wanted
    low, high = min(ranges, key=lambda r: min(abs(r[0] - wanted), abs(r[1] - wanted)))
    if min(abs(low - wanted), abs(high - wanted)) > 5_000_000:
        raise HomeAssistantError(
            f"This transmitter does not work at {wanted / 1_000_000:g} MHz"
        )
    return min(max(wanted, low), high)


def carrier_for(packet: codec.Packet, ranges: list[tuple[int, int]]) -> int:
    """The carrier for a stored code: the band's usual one, moved into the range.

    A Broadlink code only says "433" or "315 MHz" (its sweep value is not
    reliable), and fixed-frequency adapters accept exactly one value.
    """
    if packet.type not in DEFAULT_FREQUENCY:
        raise HomeAssistantError("Only RF codes can be sent through a radio_frequency transmitter")
    return fit_carrier(DEFAULT_FREQUENCY[packet.type], ranges)


def frames_in(burst: list[int]) -> list[list[int]]:
    """Split what a receiver delivered at its long silences (each frame keeps its pause)."""
    frames: list[list[int]] = []
    current: list[int] = []
    for value in burst:
        if not value:
            continue
        current.append(value)
        if value < 0 and -value >= codec.MIN_GAP_US:
            frames.append(current)
            current = []
    if current:
        frames.append(current)
    return frames


def _pulses(frame: list[int]) -> int:
    """Pulses of a frame, not counting the silence that closes it."""
    return len(frame) - (1 if frame and frame[-1] < 0 and -frame[-1] >= codec.MIN_GAP_US else 0)


def has_frame(burst: list[int]) -> bool:
    """Whether a burst holds something frame-like (a simple receiver also delivers noise:
    a few stray pulses with long silences between them)."""
    return any(_pulses(f) >= codec.MIN_RECEIVED_PULSES for f in frames_in(burst))


def _select(bursts: list[list[int]]) -> list[list[int]]:
    """The frames that look like the remote: long enough and of the usual length."""
    frames = [f for b in bursts for f in frames_in(b) if _pulses(f) >= codec.MIN_RECEIVED_PULSES]
    if not frames:
        return []
    usual, _ = Counter(_pulses(f) for f in frames).most_common(1)[0]
    margin = max(2, round(usual * LENGTH_TOLERANCE))
    return [f for f in frames if abs(_pulses(f) - usual) <= margin]


def _repeats(frames: list[list[int]]) -> int:
    if not frames:
        return 0
    try:
        return codec.analyze(codec.from_timings(frames))["good_frames"]
    except codec.CodecError:
        return 0


def best_polarity(bursts: list[list[int]]) -> tuple[list[list[int]], int, bool]:
    """The remote's frames, how many are identical, and whether the receiver was inverted.

    Some receivers report "carrier" and "silence" swapped (the Athom RF-IR
    remote does): the pause between two frames then arrives as one long
    pulse and the whole burst looks like a single, never repeated frame.
    Both readings are tried and the one where a frame repeats most wins;
    codes are always stored (and sent) with the real polarity.
    """
    normal = _select(bursts)
    flipped = _select([[-v for v in b] for b in bursts])
    n, f = _repeats(normal), _repeats(flipped)
    return (flipped, f, True) if f > n else (normal, n, False)


def select_bursts(bursts: list[list[int]]) -> list[list[int]]:
    """The frames that look like the remote, whatever the receiver's polarity."""
    return best_polarity(bursts)[0]


def repeated_frames(bursts: list[list[int]]) -> int:
    """How many identical frames the bursts hold. A remote repeats its frame; noise does not."""
    return best_polarity(bursts)[1]


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
        packet = codec.decode(code)
        timings, repeat = codec.to_timings(code)
        await self._async_send_ook(carrier_for(packet, self._ranges()), timings, repeat)

    async def async_send_timings(self, timings: list[int], frequency_hz: int, repeat: int = 0) -> None:
        await self._async_send_ook(fit_carrier(int(frequency_hz), self._ranges()), timings, repeat)

    def carrier_note(self, frequency_hz: int) -> str | None:
        try:
            carrier = fit_carrier(int(frequency_hz), self._ranges())
        except HomeAssistantError as err:
            return str(err)
        if abs(carrier - frequency_hz) > 50_000:
            return (
                f"This transmitter works at {carrier / 1_000_000:g} MHz, not "
                f"{frequency_hz / 1_000_000:g} MHz: it may only reach the receiver from close by"
            )
        return None

    async def _async_send_ook(self, carrier: int, timings: list[int], repeat: int) -> None:
        from homeassistant.components.radio_frequency import async_send_command
        from rf_protocols.commands.ook import OOKCommand

        command = OOKCommand(frequency=carrier, timings=timings, repeat_count=repeat)
        debug.trace(
            self.hass, "rf_send", transmitter=self.entity_id, carrier=command.frequency,
            repeat=repeat, pulses=len(timings), timings=debug.clip(timings),
        )
        await async_send_command(self.hass, self.entity_id, command)
        # Some adapters (ESPHome) return before the radio is done. Wait for
        # the burst to end so the hub's pause between codes starts after it.
        await asyncio.sleep(sum(abs(t) for t in timings) * (repeat + 1) / 1_000_000)

    # ---------- receiving (ESPHome only) ----------

    @property
    def sweeps(self) -> bool:
        return self.platform == BROADLINK

    def _broadlink(self):
        """A Broadlink's radio_frequency entity learns as its remote does: same device."""
        from .remote import RemoteTransmitter

        return RemoteTransmitter(self.hass, self.hub, self.entity_id)

    def _esphome(self):
        """The ESPHome runtime data and its RF receivers (see ``esphome_receivers``)."""
        if self.platform != ESPHOME:
            raise LearnError(
                "Only ESPHome and Broadlink devices can learn through a radio_frequency transmitter"
            )
        if not getattr(_esphome_data(self.hass, self.registry_entry.config_entry_id), "available", False):
            raise LearnError("The ESPHome device is not connected")
        return esphome_receivers(self.hass, self.registry_entry.config_entry_id)

    def learn_problem(self) -> str | None:
        if self.platform == BROADLINK:
            return self._broadlink().learn_problem()
        try:
            self._esphome()
        except ReceiversUnknown:
            # Not asked yet: ask now for the next look, and let a capture try
            # (it asks again and reports the real answer).
            self._refresh_soon()
        except LearnError as err:
            return str(err)
        return None

    def _refresh_soon(self) -> None:
        self.hass.async_create_background_task(
            async_refresh_receivers(self.hass, self.registry_entry.config_entry_id),
            "rf_devices list ESPHome receivers",
        )

    def receiver_problem(self) -> str | None:
        if self.platform != ESPHOME:
            return "Only ESPHome devices can listen through a radio_frequency transmitter"
        try:
            esphome_receivers(self.hass, self.registry_entry.config_entry_id)
        except ReceiversUnknown:
            self._refresh_soon()
        except LearnError as err:
            return str(err)
        return None

    @property
    def esphome_entry_id(self) -> str | None:
        return self.registry_entry.config_entry_id if self.platform == ESPHOME else None

    def _receiver_for_me(self, receivers: dict) -> object:
        """With several radios, the receiver whose frequency is closest to this transmitter's."""
        try:
            ranges = [(lo, hi) for lo, hi in self._ranges() if hi > 0]
        except HomeAssistantError:
            ranges = []
        if not ranges or len(receivers) == 1:
            return next(iter(receivers.values()))
        mine = (ranges[0][0] + ranges[0][1]) / 2
        return min(receivers.values(), key=lambda i: abs(receiver_frequency(i) - mine) if receiver_frequency(i) else 1e12)

    async def async_learn(self, frequency: float | None) -> AsyncIterator[LearnEvent]:
        if self.platform == BROADLINK:
            async for event in self._broadlink().async_learn(frequency):
                yield event
            return
        await async_refresh_receivers(self.hass, self.registry_entry.config_entry_id)
        try:
            data, receivers = self._esphome()
        except LearnError as err:
            yield LearnEvent("error", {"message": str(err)})
            return
        debug.trace(self.hass, "rx_receivers", receivers=[debug.info_dict(i) for i in receivers.values()])
        info = self._receiver_for_me(receivers)
        fixed = receiver_frequency(info)
        frequency_mhz = round(fixed / 1_000_000, 2) if fixed else None
        receivers = {info.key: info}  # only the radio that matches this transmitter

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
            elif not has_frame(timings):
                ignored = "no frame (noise)"
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
            deadline = time.monotonic() + LEARN_TIMEOUT
            while True:
                arrived.clear()
                try:
                    await asyncio.wait_for(arrived.wait(), max(0.0, deadline - time.monotonic()))
                except TimeoutError:
                    debug.trace(self.hass, "rx_nothing_repeated", bursts=len(bursts))
                    yield LearnEvent("timeout", {"during": "press"})
                    return
                while True:
                    now = time.monotonic()
                    if now - last >= QUIET_AFTER_PRESS or now - first >= MAX_PRESS:
                        break
                    await asyncio.sleep(0.1)
                if repeated_frames(bursts) >= MIN_REPEATS:
                    break
                # Something frame-like, but it did not repeat: stray noise.
                # Forget it and keep waiting for the remote.
                debug.trace(self.hass, "rx_discarded", bursts=len(bursts))
                bursts.clear()
                first = None
        finally:
            unsubscribe()

        kept, repeats, inverted = best_polarity(bursts)
        debug.trace(self.hass, "rx_kept", bursts=len(bursts), frames=len(kept), repeats=repeats, inverted=inverted)
        _LOGGER.debug("Received %d bursts, kept %d (inverted: %s): %s", len(bursts), len(kept), inverted, bursts)
        yield LearnEvent("captured", codec.capture_result(codec.from_timings(kept), frequency_mhz))


def receiver_frequency(info) -> int:
    """The fixed frequency a receiver declares (Hz), or 0."""
    low = getattr(info, "frequency_min", 0) or 0
    high = getattr(info, "frequency_max", 0) or 0
    if low and low == high:
        return int(low)
    return int(getattr(info, "receiver_frequency", 0) or 0)


class ReceiversUnknown(LearnError):
    """The device has not been asked for its receivers yet (``async_refresh_receivers``)."""


def _esphome_data(hass, config_entry_id: str | None):
    entry = hass.config_entries.async_get_entry(config_entry_id) if config_entry_id else None
    data = getattr(entry, "runtime_data", None) if entry else None
    if data is None or not hasattr(data, "client"):
        raise LearnError("The ESPHome integration is not loaded for this device")
    return data


def _is_receiver(info) -> bool:
    return type(info).__name__ == "RadioFrequencyInfo" and bool(
        getattr(info, "capabilities", 0) & RF_RECEIVER
    )


async def async_refresh_receivers(hass, config_entry_id: str | None) -> None:
    """Ask an ESPHome device for its RF receivers and remember them.

    Home Assistant's ESPHome integration keeps only the entity infos it
    makes entities from, and it makes none for RF receivers, so they are
    not in its runtime data: the device's own entity list is the only place
    that names them.
    """
    try:
        data = _esphome_data(hass, config_entry_id)
    except LearnError:
        return
    if not getattr(data, "available", False):
        return
    try:
        infos, _services = await asyncio.wait_for(data.client.list_entities_services(), LIST_TIMEOUT)
    except Exception as err:  # noqa: BLE001 - aioesphomeapi raises its own errors
        _LOGGER.warning("Could not list the entities of the ESPHome device: %s", err)
        debug.trace(hass, "rx_list_error", entry=config_entry_id, message=f"{type(err).__name__}: {err}")
        return
    receivers = {info.key: info for info in infos if _is_receiver(info)}
    hass.data.setdefault(DATA_RECEIVERS, {})[config_entry_id] = (data, receivers)
    debug.trace(
        hass, "rx_listed", entry=config_entry_id,
        rf_ir=[debug.info_dict(i) for i in infos if type(i).__name__ in debug.RF_INFO_TYPES],
    )


def listed_receivers(hass, config_entry_id: str | None) -> dict | None:
    """Receivers found by the last ``async_refresh_receivers`` (None: never asked)."""
    cached = hass.data.get(DATA_RECEIVERS, {}).get(config_entry_id)
    if cached is None:
        return None
    entry = hass.config_entries.async_get_entry(config_entry_id) if config_entry_id else None
    if cached[0] is not getattr(entry, "runtime_data", None):
        return None  # the ESPHome entry was reloaded since
    return cached[1]


def esphome_receivers(hass, config_entry_id: str | None) -> tuple[object, dict]:
    """ESPHome runtime data of a config entry and its RF receivers by key.

    Raises ``ReceiversUnknown`` until the device has been asked
    (``async_refresh_receivers``), and ``LearnError`` when it has none.
    """
    data = _esphome_data(hass, config_entry_id)
    receivers = {
        info.key: info
        for infos in getattr(data, "info", {}).values()
        for info in infos.values()
        if _is_receiver(info)
    }
    listed = listed_receivers(hass, config_entry_id)
    receivers.update(listed or {})
    if not receivers:
        if listed is None:
            raise ReceiversUnknown("The ESPHome device has not been asked for its RF receivers yet")
        raise LearnError(
            "This ESPHome device has no RF receiver (ir_rf_proxy with remote_receiver_id)"
        )
    return data, receivers

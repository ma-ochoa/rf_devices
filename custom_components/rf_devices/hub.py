"""Sending codes and learning new ones through the chosen transmitter."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import aclosing

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import codec, debug
from .codec import capture_result
from .const import (
    CONF_MIN_INTERVAL,
    CONF_TRANSMITTER,
    DEFAULT_MIN_INTERVAL,
    LEARN_COOLDOWN,
)
from .models import KIND_ACTION, KIND_SOMFY, command_kind
from .protocols import somfy
from .store import RFStore
from .transmitters import LearnError, LearnEvent, Transmitter, get_transmitter

_LOGGER = logging.getLogger(__name__)

__all__ = ["LearnError", "LearnEvent", "RFHub", "capture_result"]

# Seconds after one of our transmissions during which a receiver may still be
# hearing it (repeats, receiver buffering): not a press of the original remote.
ECHO_MARGIN = 1.5

SOMFY_INVERTED = {"up": "down", "down": "up", "my_up": "my_down", "my_down": "my_up"}


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
        # Until when a receiver may be hearing our own transmission (loop.monotonic):
        # the follower (listen.py) ignores what arrives before this.
        self.echo_until = 0.0
        self.follower = None  # listen.Follower when some device follows its remote

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
        entity_id = transmitter or self.default_transmitter

        async def send() -> None:
            await self.transmitter(entity_id).async_send(code)

        await self._async_transmit(entity_id, interval, send, fingerprint=_fingerprint(code))

    async def async_send_command(
        self,
        device: dict,
        cmd: dict,
        hold: float = 0,
        interval: float | None = None,
    ) -> None:
        """Send one stored command of ``device``, whatever its kind."""
        kind = command_kind(cmd)
        if kind == KIND_ACTION:
            await self.async_call_action(cmd)
        elif kind == KIND_SOMFY:
            await self.async_send_somfy(device, cmd["button"], hold, interval)
        else:
            code = codec.hold(cmd["code"], hold) if hold else cmd["code"]
            await self.async_send(code, self.transmitter_for(device), interval)

    async def async_send_somfy(
        self, device: dict, button: str, hold: float = 0, interval: float | None = None
    ) -> None:
        """Press a button of the device's Somfy virtual remote (new rolling code each time)."""
        cfg = device.get("somfy")
        if not cfg:
            raise HomeAssistantError(f"{device.get('name')}: no Somfy remote configured")
        if cfg.get("invert"):
            button = SOMFY_INVERTED.get(button, button)
        repeats = somfy.repeats_for(hold) if hold else int(cfg.get("repeats", somfy.DEFAULT_REPEATS))
        address = int(cfg["address"])
        entity_id = self.transmitter_for(device)
        tx = self.transmitter(entity_id)

        async def send() -> None:
            # The counter moves forward (and is saved) inside the queue, so
            # codes leave in order even when presses pile up.
            code = await self.store.async_next_somfy_code(address)
            timings = somfy.encode(address, button, code, repeats)
            debug.trace(
                self.hass, "somfy", transmitter=entity_id, address=f"{address:06X}",
                button=button, rolling_code=code, repeats=repeats,
            )
            await tx.async_send_timings(timings, somfy.FREQUENCY_HZ)

        await self._async_transmit(entity_id, interval, send, fingerprint=f"somfy:{address:06X}:{button}")

    async def async_call_action(self, cmd: dict) -> None:
        """A command that is a service call on another integration's entity."""
        domain, service = cmd["service"].split(".", 1)
        data = dict(cmd.get("data") or {})
        if cmd.get("entity_id"):
            data["entity_id"] = cmd["entity_id"]
        error = None
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except Exception as err:
            error = f"{type(err).__name__}: {err}"
            raise
        finally:
            debug.trace(self.hass, "action", service=cmd["service"], data=data, error=error)

    async def _async_transmit(self, entity_id: str, interval: float | None, send, fingerprint=None) -> None:
        if self.learning:
            raise HomeAssistantError("RF Devices is capturing a code; try again in a moment")
        async with self._lock:
            pause = self.min_interval if interval is None else interval
            wait = self._last_send + pause - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            started = time.monotonic()
            self.echo_until = float("inf")
            error = None
            try:
                await send()
            except Exception as err:
                error = f"{type(err).__name__}: {err}"
                raise
            finally:
                self._last_send = time.monotonic()
                self.echo_until = self._last_send + ECHO_MARGIN
                debug.trace(
                    self.hass, "send", transmitter=entity_id, fingerprint=fingerprint,
                    took_ms=round((self._last_send - started) * 1000), error=error,
                )

    def transmitter(self, entity_id: str | None = None) -> Transmitter:
        return get_transmitter(self.hass, self, entity_id or self.default_transmitter)

    def learn_problem(self, entity_id: str) -> str | None:
        """Why this transmitter cannot learn, or None if it can."""
        try:
            return self.transmitter(entity_id).learn_problem()
        except LearnError as err:
            return str(err)

    def can_learn(self, entity_id: str) -> bool:
        return self.learn_problem(entity_id) is None

    @property
    def learning(self) -> bool:
        return self._learn_lock.locked()

    async def async_learn(
        self, transmitter: str | None = None, frequency: float | None = None
    ) -> AsyncIterator[LearnEvent]:
        """Learn one RF code, yielding progress for the UI.

        Whatever the transmitter: only one capture at a time, a pause between
        captures, and RF Devices sends nothing while a capture runs.
        """
        tx = self.transmitter(transmitter)
        if (problem := tx.learn_problem()) is not None:
            raise LearnError(problem)
        if self._learn_lock.locked():
            raise LearnError("Another capture is already running")

        async with self._learn_lock:
            wait = self._last_learn + LEARN_COOLDOWN - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            debug.trace(self.hass, "learn_start", transmitter=tx.entity_id, frequency=frequency)
            try:
                # Closing the inner generator runs its clean-up even when the
                # UI unsubscribes while it is waiting at a yield.
                async with aclosing(tx.async_learn(frequency)) as events:
                    async for event in events:
                        debug.trace(self.hass, "learn_" + event.stage, **_learn_summary(event.data))
                        yield event
            except BaseException as err:
                debug.trace(self.hass, "learn_end", reason=type(err).__name__, message=str(err))
                raise
            finally:
                self._last_learn = time.monotonic()


def _fingerprint(code: str) -> str | None:
    try:
        return codec.fingerprint(code)
    except codec.CodecError:
        return None


def _learn_summary(data: dict) -> dict:
    """What the trace keeps of a learning event: the codes, not the UI's analysis."""
    if "raw" not in data:
        return dict(data)
    return {
        "frequency": data.get("frequency"),
        "raw": data["raw"],
        "code": data["code"],
        "fingerprint": data.get("fingerprint"),
        "frames": data["raw_analysis"]["frames"],
        "good_frames": data["raw_analysis"]["good_frames"],
        "bits": data["analysis"]["bits"],
    }

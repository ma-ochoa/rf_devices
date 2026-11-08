"""Follow the original remotes: listen to an RF receiver and update the state.

A remote used by hand changes the device without Home Assistant knowing. When
the transmitter has a receiver next to it (an ESPHome ``ir_rf_proxy`` with
``remote_receiver_id``, e.g. an ESP32 with a CC1101), RF Devices listens all
the time and, for the devices that ask for it (``follow``):

* recognises a stored fixed code by its fingerprint (the same comparison the
  panel uses to spot duplicates) and applies that button's effect;
* decodes Somfy RTS frames and matches the address of the real remote
  (``follow_somfy``), whatever its rolling code.

Nothing is sent. What RF Devices sends itself is heard too, so everything
received while sending (and ``ECHO_MARGIN`` after) is ignored, as is anything
while a code is being learned. Every recognised press also fires the
``rf_devices_remote`` event, so automations can use remotes that have no
entity of their own (an alarm fob, an extra button).
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable
from datetime import timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from . import codec, debug
from .const import (
    EXTRA_PREFIX,
    ROLE_CLOSE,
    ROLE_LIGHT_COLOR,
    ROLE_OFF,
    ROLE_ON,
    ROLE_OPEN,
    ROLE_STOP,
    TIMER_PREFIX,
    TYPE_BUTTONS,
    TYPE_COVER,
    TYPE_FAN,
)
from .entity import find_by_unique_id
from .models import KIND_RF, command_kind
from .protocols import somfy
from .transmitters import LearnError
from .transmitters.radio_frequency import (
    RadioFrequencyTransmitter,
    ReceiversUnknown,
    async_refresh_receivers,
    esphome_receivers,
    has_frame,
    listed_receivers,
    receiver_frequency,
    select_bursts,
)

_LOGGER = logging.getLogger(__name__)

EVENT = "rf_devices_remote"

# A press is over when nothing arrives for this long, or this long after it began.
PRESS_QUIET = 0.35
MAX_PRESS = 3.0
# How often the subscriptions are checked (the ESPHome device may reconnect).
RECHECK = timedelta(seconds=30)

# What a Somfy button does, per device type.
SOMFY_ROLES = {
    TYPE_COVER: {"up": ROLE_OPEN, "down": ROLE_CLOSE, "my": ROLE_STOP},
    "light": {"up": ROLE_ON, "down": ROLE_OFF},
    "switch": {"up": ROLE_ON, "down": ROLE_OFF},
}
SOMFY_INVERTED = {"up": "down", "down": "up"}


def entity_key_for(device: dict, role: str) -> str | None:
    """Which of the device's entities a remote button changes (None: only the event)."""
    kind = device["type"]
    if role == ROLE_LIGHT_COLOR:
        return "color"
    if role.startswith((EXTRA_PREFIX, TIMER_PREFIX)) or kind == TYPE_BUTTONS:
        return None
    if kind == TYPE_FAN and role.startswith("light_"):
        return "fan_light"
    return kind


def follow_problem(hub, device: dict) -> str | None:
    """Why the device's original remote cannot be followed, or None."""
    try:
        tx = hub.transmitter(hub.transmitter_for(device))
    except LearnError as err:
        return str(err)
    return tx.receiver_problem()


class Follower:
    """Listens to the receivers and applies the presses of the original remotes."""

    def __init__(self, hass: HomeAssistant, hub) -> None:
        self.hass = hass
        self.hub = hub
        self._links: dict[str, _EsphomeLink] = {}
        self._fixed: dict[str, list[tuple[str, str]]] = {}  # fingerprint -> (device id, role)
        self._bits: dict[tuple[str, str], list[tuple[str, str]]] = {}  # (kind, bits) -> …
        self._somfy: dict[int, list[str]] = {}  # real remote address -> device ids
        self._own_somfy: set[int] = set()
        self._last_somfy: dict[int, int] = {}  # address -> last rolling code applied
        self._pending: dict[tuple[str, int], _Press] = {}
        self.index()

    # ---------------------------------------------------------------- setup
    def index(self) -> None:
        """What to recognise, from the devices that follow their remote."""
        self._fixed.clear()
        self._bits.clear()
        self._somfy.clear()
        self._own_somfy = {
            int(d["somfy"]["address"]) for d in self.hub.store.devices.values() if d.get("somfy")
        }
        for device in self.hub.store.devices.values():
            if not device.get("follow"):
                continue
            for address in device.get("follow_somfy") or []:
                self._somfy.setdefault(int(address), []).append(device["id"])
            for role, cmd in device.get("commands", {}).items():
                if command_kind(cmd) != KIND_RF:
                    continue
                try:
                    fp = codec.fingerprint(cmd["code"])
                    analysis = codec.analyze(cmd["code"])
                except codec.CodecError:
                    continue
                self._fixed.setdefault(fp, []).append((device["id"], role))
                if analysis["bits"]:
                    key = (analysis["kind"], analysis["bits"])
                    self._bits.setdefault(key, []).append((device["id"], role))

    def entry_ids(self) -> set[str]:
        """ESPHome config entries whose receivers must be listened to."""
        ids = set()
        for device in self.hub.store.devices.values():
            if not device.get("follow"):
                continue
            try:
                tx = self.hub.transmitter(self.hub.transmitter_for(device))
            except LearnError:
                continue
            if isinstance(tx, RadioFrequencyTransmitter) and tx.esphome_entry_id:
                ids.add(tx.esphome_entry_id)
        return ids

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        for entry_id in self.entry_ids():
            link = _EsphomeLink(self.hass, entry_id, self._on_burst)
            self._links[entry_id] = link
            link.start()
        debug.trace(self.hass, "follow_start", entries=sorted(self._links),
                    fixed=len(self._fixed), somfy=[f"{a:06X}" for a in self._somfy])

        @callback
        def stop() -> None:
            for link in self._links.values():
                link.stop()
            self._links.clear()
            for press in self._pending.values():
                press.cancel()
            self._pending.clear()

        return stop

    # ------------------------------------------------------------ receiving
    @callback
    def _on_burst(self, entry_id: str, key: int, frequency: int, timings: list[int]) -> None:
        now = time.monotonic()
        if self.hub.learning or now < self.hub.echo_until:
            return  # our own transmission, or a capture in progress
        slot = (entry_id, key)
        press = self._pending.get(slot)
        if press is None:
            press = self._pending[slot] = _Press(now, frequency)
        press.add(timings, now)
        press.cancel()
        wait = PRESS_QUIET if now - press.first < MAX_PRESS else 0

        @callback
        def flush(_now) -> None:
            self._flush(slot)

        press.timer = async_call_later(self.hass, wait, flush)

    @callback
    def _flush(self, slot: tuple[str, int]) -> None:
        press = self._pending.pop(slot, None)
        if press is None or not press.bursts:
            return
        if time.monotonic() < self.hub.echo_until:
            return  # we started sending meanwhile: what was heard may be ours
        self.hass.async_create_task(self._async_recognise(press.bursts, press.frequency))

    async def _async_recognise(self, bursts: list[list[int]], frequency: int) -> None:
        matches: list[tuple[str, str, str]] = []  # (device id, role, source)
        presses = {p for b in bursts for p in somfy.decode(b)}
        if not presses:  # a receiver that reports carrier and silence swapped
            presses = {p for b in bursts for p in somfy.decode([-v for v in b])}
        if presses:
            for p in sorted(presses, key=lambda p: p.rolling_code):
                if p.address in self._own_somfy or self._last_somfy.get(p.address) == p.rolling_code:
                    continue
                self._last_somfy[p.address] = p.rolling_code
                for device_id in self._somfy.get(p.address, []):
                    device = self.hub.store.devices.get(device_id)
                    if device is None:
                        continue
                    button = p.button
                    if (device.get("somfy") or {}).get("invert"):
                        button = SOMFY_INVERTED.get(button, button)
                    role = SOMFY_ROLES.get(device["type"], {}).get(button, f"somfy_{button}")
                    matches.append((device_id, role, f"somfy:{p.address:06X}"))
            debug.trace(self.hass, "follow_rx", somfy=[
                {"address": f"{p.address:06X}", "button": p.button, "code": p.rolling_code} for p in presses
            ], matched=len(matches))
        else:
            kept = select_bursts(bursts)
            if not kept:
                return
            try:
                code = codec.from_timings(kept)
                fp = codec.fingerprint(code)
                analysis = codec.analyze(code)
            except codec.CodecError:
                return
            found = self._fixed.get(fp) or self._bits.get((analysis["kind"], analysis["bits"])) or []
            matches = [(device_id, role, "code") for device_id, role in found]
            debug.trace(self.hass, "follow_rx", fingerprint=fp, bits=analysis["bits"],
                        frequency=frequency, matched=len(matches))
        for device_id, role, source in matches:
            await self._async_apply(device_id, role, source)

    async def _async_apply(self, device_id: str, role: str, source: str) -> None:
        device = self.hub.store.devices.get(device_id)
        if device is None:
            return
        handled = False
        key = entity_key_for(device, role)
        entity = find_by_unique_id(self.hass, f"{device_id}_{key}") if key else None
        if entity is not None:
            try:
                handled = await entity.async_follow_remote(role)
            except Exception:  # one bad entity must not stop listening
                _LOGGER.exception("Could not follow %s / %s", device["name"], role)
        _LOGGER.debug("Original remote of %s: %s (%s, applied: %s)", device["name"], role, source, handled)
        self.hass.bus.async_fire(
            EVENT,
            {"device_id": device_id, "name": device["name"], "role": role,
             "source": source, "applied": handled},
        )


class _Press:
    """Bursts from one receiver that belong to one press of a remote."""

    def __init__(self, now: float, frequency: int) -> None:
        self.first = now
        self.last = now
        self.frequency = frequency
        self.bursts: list[list[int]] = []
        self.timer: CALLBACK_TYPE | None = None

    def add(self, timings: list[int], now: float) -> None:
        self.bursts.append(timings)
        self.last = now

    def cancel(self) -> None:
        if self.timer is not None:
            self.timer()
            self.timer = None


class _EsphomeLink:
    """Subscription to the RF receivers of one ESPHome device, kept across reconnections."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        on_burst: Callable[[str, int, int, list[int]], None],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._on_burst = on_burst
        self._data = None
        self._connection = None
        self._unsub_rx: Callable[[], None] | None = None
        self._unsub_updates: Callable[[], None] | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._receivers: dict[int, int] = {}  # key -> frequency (Hz)
        self._listing = False

    @callback
    def start(self) -> None:
        self._unsub_timer = async_track_time_interval(self.hass, self._check, RECHECK)
        self._check()

    @callback
    def stop(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        self._drop()
        if self._unsub_updates:
            with contextlib.suppress(Exception):
                self._unsub_updates()
            self._unsub_updates = None

    @callback
    def _drop(self) -> None:
        if self._unsub_rx is not None:
            with contextlib.suppress(Exception):  # the connection may be gone already
                self._unsub_rx()
        self._unsub_rx = None
        self._connection = None

    @callback
    def _check(self, _now=None) -> None:
        try:
            data, receivers = esphome_receivers(self.hass, self.entry_id)
        except ReceiversUnknown:
            # Home Assistant does not keep the receivers: ask the device, then look again.
            self._drop()
            if not self._listing:
                self._listing = True
                self.hass.async_create_background_task(self._async_list(), "rf_devices list ESPHome receivers")
            return
        except LearnError:
            self._drop()
            return
        if data is not self._data:
            # The ESPHome entry was reloaded: listen to its new runtime data.
            if self._unsub_updates:
                with contextlib.suppress(Exception):
                    self._unsub_updates()
            self._data = data
            self._drop()
            if hasattr(data, "async_subscribe_device_updated"):
                self._unsub_updates = data.async_subscribe_device_updated(self._check)
        self._receivers = {key: receiver_frequency(info) for key, info in receivers.items()}
        if not getattr(data, "available", False):
            self._drop()
            return
        connection = getattr(data.client, "_connection", None)
        if self._unsub_rx is not None and connection is self._connection:
            return
        self._drop()
        try:
            self._unsub_rx = data.client.subscribe_infrared_rf_receive(self._receive)
        except Exception as err:  # noqa: BLE001 - aioesphomeapi raises its own errors
            _LOGGER.debug("Cannot listen to %s yet: %s", self.entry_id, err)
            return
        self._connection = connection
        if not self._listing:
            # A new connection may be a new firmware: ask for its receivers again.
            self._listing = True
            self.hass.async_create_background_task(self._async_list(), "rf_devices list ESPHome receivers")
        debug.trace(self.hass, "follow_subscribed", entry=self.entry_id,
                    receivers={str(k): v for k, v in self._receivers.items()})

    async def _async_list(self) -> None:
        try:
            await async_refresh_receivers(self.hass, self.entry_id)
        finally:
            self._listing = False
        if listed_receivers(self.hass, self.entry_id) is not None and self._unsub_timer:
            self._check()

    @callback
    def _receive(self, event) -> None:
        if event.key not in self._receivers:
            return  # an infrared receiver, or another radio's entity
        timings = list(event.timings)
        if not has_frame(timings):
            return  # noise
        self._on_burst(self.entry_id, event.key, self._receivers[event.key], timings)


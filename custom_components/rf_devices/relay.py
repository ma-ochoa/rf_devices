"""A device wired behind a relay and a wall switch (modes A and B).

::

    wall switch ──► relay (Shelly, Sonoff…) ──► fan + lamp  ◄── RF (Broadlink)
                      │ meter

Mode A, coupled: the wall switch drives the relay itself. RF Devices only
observes it: relay on = lamp on (it lights when it gets power), relay off =
everything off. Asking for the lamp with the relay off switches the relay on.

Mode B, detached: the wall switch no longer drives the relay; Home Assistant
reads it and RF Devices toggles the lamp by RF, so the relay stays on and the
fan can always be used. Several quick flips make gestures (wall.py). An optional
script on the device takes over the wall switch if Home Assistant does not
confirm a press within a couple of seconds (down, restarting or hung).

In both modes, starting the fan with the relay off means powering it, which
lights the lamp for a moment; that is only done if explicitly allowed. The
relay may also be switched off after a while with everything off, because a
relay kept energised for years can weld its contacts.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .entity import find_by_unique_id
from .meter import Meter
from .relays import RelayAdapter, get_adapter
from .wall import WallGestures

if TYPE_CHECKING:
    from .hub import RFHub

_LOGGER = logging.getLogger(__name__)

MODE_NONE = "none"
MODE_COUPLED = "coupled"
MODE_DETACHED = "detached"
MODE_WALL_ONLY = "wall_only"  # no relay: the wall switch only toggles the light

READY_POLL = 0.2  # seconds between live meter reads while waiting for the lamp
READY_EXTRA = 0.3  # after the meter sees the lamp, a moment for the receiver
LIGHT_CHECK_DELAY = 2.0  # after a power-up for the fan: when to check the lamp is off
FAN_POWER_WINDOW = 10.0  # s: a relay power-up this soon after one done for the fan is that one
# After a power-up (plus power_up_delay): when to check the lamp lit. The
# a tested fan lamp takes ~2 s to light; a "light on" sent to a toggle-only lamp
# that was about to light would switch it off, so wait well past that and
# confirm with a second reading.
LAMP_ON_WAIT = 3.0
LAMP_CONFIRM_GAP = 1.0
LIGHT_CHECK_RETRIES = 2
CHECK_EVERY = dt.timedelta(minutes=1)  # idle-off check


def relay_mode(device: dict) -> str:
    opts = device.get("options", {})
    mode = opts.get("relay_mode")
    if mode is None:  # not chosen: a relay means mode A
        return MODE_COUPLED if opts.get("power_entity") else MODE_NONE
    if mode == MODE_WALL_ONLY:
        return mode
    return mode if opts.get("power_entity") else MODE_NONE


def in_window(now: dt.datetime, start: str, end: str) -> bool:
    """Whether ``now`` (local) is within HH:MM–HH:MM, which may cross midnight."""
    def minutes(text: str) -> int:
        hours, _, mins = text.partition(":")
        return int(hours) * 60 + int(mins or 0)

    current, a, b = now.hour * 60 + now.minute, minutes(start), minutes(end)
    return a <= current < b if a <= b else current >= a or current < b


class RelayController:
    """Runs the relay rules for one RF Devices device."""

    def __init__(self, hass: HomeAssistant, hub: RFHub, device: dict) -> None:
        self.hass = hass
        self.hub = hub
        self.device = device
        opts = device["options"]
        self.mode = relay_mode(device)
        self.relay: str = opts["power_entity"]
        self.adapter: RelayAdapter = get_adapter(hass, self.relay)
        self.input: str | None = opts.get("switch_entity")
        self.meter: str | None = opts.get("light_state_entity") or opts.get("state_entity")
        self.fan_power_on = bool(opts.get("fan_power_on"))
        self.power_up_delay = float(opts.get("power_up_delay", 0.5))
        self.power_up_wait_meter = bool(opts.get("power_up_wait_meter"))
        self.power_up_gap = float(opts.get("power_up_gap", 0.4))
        self.power_up_check = bool(opts.get("power_up_check", True))
        self.ensure_light_on = bool(opts.get("ensure_light_on_power_up", True))
        self._fan_power_at = float("-inf")  # loop time of a power-up done for the fan
        self.idle_minutes = int(opts.get("idle_off_minutes") or 0)
        self.idle_when = opts.get("idle_off_when", "always")
        self.idle_from = opts.get("idle_off_from", "23:00")
        self.idle_to = opts.get("idle_off_to", "08:00")
        self.fallback = bool(opts.get("fallback_script"))
        self._idle_since: dt.datetime | None = None
        self.wall: WallGestures | None = None
        if self.mode == MODE_DETACHED and self.input:
            self.wall = WallGestures(hass, device, self.input, self._flipped, self._async_cut)
        self._lock = asyncio.Lock()

    # --- state ------------------------------------------------------------
    @property
    def powered(self) -> bool:
        state = self.hass.states.get(self.relay)
        return state is None or state.state != STATE_OFF

    def _entity(self, key: str):
        return find_by_unique_id(self.hass, f"{self.device['id']}_{key}")

    def light(self):
        return self._entity("fan_light" if self.device["type"] == "fan" else self.device["type"])

    def fan(self):
        return self._entity("fan") if self.device["type"] == "fan" else None

    def _all_off(self) -> bool:
        light, fan = self.light(), self.fan()
        return (light is None or not light.is_on) and (fan is None or not fan.is_on)

    # --- lifecycle --------------------------------------------------------
    @callback
    def async_start(self) -> Callable[[], None]:
        unsubs = [
            async_track_time_interval(self.hass, self._async_tick, CHECK_EVERY),
            async_track_state_change_event(self.hass, [self.relay], self._relay_changed),
        ]
        if self.wall is not None:
            unsubs.append(self.wall.async_start())

        def stop() -> None:
            for unsub in unsubs:
                unsub()

        return stop

    # --- power ------------------------------------------------------------
    async def async_power(self, on: bool) -> None:
        await self.hass.services.async_call(
            "homeassistant", "turn_on" if on else "turn_off", {"entity_id": self.relay}, blocking=True
        )

    async def _async_wait_ready(self) -> None:
        """After powering: give the receiver ``power_up_delay`` seconds to boot.

        With ``power_up_wait_meter`` the wait ends as soon as the meter (read
        live when possible) sees the lamp, which means the receiver is up.
        """
        if not (self.power_up_wait_meter and self.meter):
            await asyncio.sleep(self.power_up_delay)
            return
        threshold = float(self.device["options"].get("light_state_threshold") or 3.0)
        meter = Meter(self.hass, self.meter)
        waited = 0.0
        while waited < self.power_up_delay:
            await asyncio.sleep(READY_POLL)
            waited += READY_POLL
            if ((await meter.async_read()) or 0) > threshold:
                await asyncio.sleep(READY_EXTRA)
                return

    async def async_light_needs_power(self) -> bool:
        """The lamp was asked to turn on with the relay off: power it (it lights by itself).

        Returns True when that already turned the lamp on.
        """
        if self.powered:
            return False
        await self.async_power(True)
        return True

    async def async_fan_needs_power(self) -> float | None:
        """The fan was asked for something with the relay off.

        Only if allowed: power the relay (the lamp lights), wait for the
        receiver, switch the lamp off by RF, and let the caller send the fan
        command. Otherwise refuse, so nothing lights up unexpectedly.

        Returns the pause the caller must leave before its fan command, or
        None if the relay was already on.
        """
        if self.powered:
            return None
        if not self.fan_power_on:
            raise HomeAssistantError(
                f"{self.device['name']} has no power ({self.relay} is off) and starting "
                "the fan by powering it is not allowed"
            )
        async with self._lock:
            if self.powered:
                return None
            self._fan_power_at = self.hass.loop.time()  # the lamp must end up off: no "ensure on"
            await self.async_power(True)
            await self._async_wait_ready()
            light = self.light()
            if light is not None:
                light._attr_is_on = True  # noqa: SLF001 - it lit at power-up
                await light.async_turn_off()
            return self.power_up_gap

    # --- lamp with memory: make sure it lights when the relay powers up ----
    @callback
    def _relay_changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None or old.state != STATE_OFF or new.state != STATE_ON:
            return
        if self.hass.loop.time() - self._fan_power_at < FAN_POWER_WINDOW:
            return
        if self.ensure_light_on and self.meter:
            self.hass.async_create_background_task(
                self._async_ensure_lamp_on(self.hass.loop.time()),
                f"rf_devices lamp on {self.device['id']}",
            )

    async def _async_ensure_lamp_on(self, since: float) -> None:
        """The relay just powered up: the lamp should be on; if not, switch it on by RF.

        Lamps without memory light by themselves; lamps with memory stay as
        they were. Checked on the meter (live when possible), twice at most.
        """
        meter = Meter(self.hass, self.meter)
        await asyncio.sleep(self.power_up_delay + LAMP_ON_WAIT)
        for _ in range(LIGHT_CHECK_RETRIES):
            light = self.light()
            if light is None or not self.powered or getattr(light, "user_off_at", 0) >= since:
                return  # power cut again, or someone asked for the light off meanwhile
            watts = await meter.async_read()
            if watts is None or self._lamp_seen(watts):
                return
            await asyncio.sleep(LAMP_CONFIRM_GAP)  # still dark a moment later?
            watts = await meter.async_read()
            if watts is None or self._lamp_seen(watts) or not self.powered:
                return
            _LOGGER.info("%s: relay on but the lamp stayed off (%s W), switching it on", self.device["name"], watts)
            role = light._roles["toggle"] if light._toggle_mode else light._roles["on"]  # noqa: SLF001
            await light.async_send_role(role)
            await light.async_set_assumed_state(True)
            await asyncio.sleep(LIGHT_CHECK_DELAY)

    @callback
    def schedule_light_check(self) -> None:
        """After a power-up for the fan: make sure the lamp really went off."""
        if self.power_up_check and self.meter:
            since = self.hass.loop.time()
            self.hass.async_create_background_task(
                self._async_light_check(since), f"rf_devices light check {self.device['id']}"
            )

    def _lamp_seen(self, watts: float) -> bool:
        calibration = self.device["options"].get("calibration")
        if calibration:
            from .calibration import classify  # noqa: PLC0415 - avoid an import cycle

            estimate = classify(calibration, watts)
            return bool(estimate and estimate.light)
        threshold = float(self.device["options"].get("light_state_threshold") or 3.0)
        return watts > threshold

    async def _async_light_check(self, since: float) -> None:
        meter = Meter(self.hass, self.meter)
        for _ in range(LIGHT_CHECK_RETRIES):
            await asyncio.sleep(LIGHT_CHECK_DELAY)
            light = self.light()
            if light is None or not self.powered or getattr(light, "user_on_at", 0) >= since:
                return  # power was cut, or someone asked for the light meanwhile
            watts = await meter.async_read()
            if watts is None or not self._lamp_seen(watts):
                return
            _LOGGER.info("%s: lamp still on after power-up (%s W), sending off again", self.device["name"], watts)
            role = light._roles["toggle"] if light._toggle_mode else light._roles["off"]  # noqa: SLF001
            await light.async_send_role(role)
            await light.async_set_assumed_state(False)

    # --- wall switch (mode B) ---------------------------------------------
    @callback
    def _flipped(self) -> None:
        if self.fallback and self.adapter.capabilities.fallback_script:
            # First of all: tell the device's fallback script we got this press.
            self.hass.async_create_background_task(self._async_ack(), "rf_devices ack")

    async def _async_cut(self) -> None:
        _LOGGER.info("Wall switch gesture: cutting power to %s", self.device["name"])
        await self.async_power(False)

    # --- periodic: idle-off -------------------------------------------------
    def idle_allowed_now(self, now: dt.datetime) -> bool:
        if self.idle_when == "night":
            sun = self.hass.states.get("sun.sun")
            return sun is None or sun.state == "below_horizon"
        if self.idle_when == "hours":
            return in_window(dt_util.as_local(now), self.idle_from, self.idle_to)
        return True

    async def _async_ack(self) -> None:
        try:
            await self.adapter.async_ack()
        except Exception as err:  # noqa: BLE001 - the script will act on its own
            _LOGGER.warning("Could not confirm the wall-switch press to %s: %s", self.relay, err)

    async def _async_tick(self, now: dt.datetime) -> None:
        await self.async_check_idle(now)

    async def async_check_idle(self, now: dt.datetime) -> None:
        """Switch the relay off after ``idle_minutes`` with everything off."""
        if not self.idle_minutes or not self.powered or not self._all_off():
            self._idle_since = None
            return
        if self._idle_since is None:
            self._idle_since = now
            return
        if now - self._idle_since < dt.timedelta(minutes=self.idle_minutes):
            return
        if not self.idle_allowed_now(now):
            return
        _LOGGER.info("%s: relay off after %s min with everything off", self.device["name"], self.idle_minutes)
        self._idle_since = None
        await self.async_power(False)

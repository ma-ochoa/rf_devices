"""Covers (blinds, shutters, awnings…) driven by RF codes.

With travel times configured the position is estimated from how long the
cover has been moving, and set_position sends "stop" at the right moment.

Optionally (all independent of each other):

* a relay feeds the motor: with it off nothing is sent, or it is switched on
  first (powering a cover moves nothing, unlike a ceiling fan's lamp);
* a power meter (or an on/off "moving" entity) tells when the motor really
  runs. A full travel then ends when the motor stops at its limit switch, not
  when the time is up, which re-aligns the position at 0 % and 100 %; and a
  move made with the original remote marks the position as not reliable until
  the next full travel;
* wall buttons, with or without a relay: one input steps open → stop → close →
  stop; two inputs are "up" and "down".
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import ROLE_CLOSE, ROLE_OPEN, ROLE_STOP
from .entity import RFEntity, feedback_on, setup_platform_entities
from .meter import Meter

TICK = 0.5  # seconds between position updates while moving
# With a meter:
START_GRACE = 4.0  # s for the motor to show after a command; else it was already at the limit
STOP_READINGS = 2  # readings in a row without draw = the motor stopped
OVERRUN = 1.5  # a full travel may last this many times the configured time...
OVERRUN_EXTRA = 10.0  # ... plus these seconds, before giving the motor up as stopped
UNTIMED_MAX = 300.0  # longest travel followed when no times are configured
OWN_WINDOW = 5.0  # s after our own command or stop that the motor's draw is still ours

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_platform_entities(hass, entry, async_add_entities, "cover", RFCover)


class RFCover(RFEntity, CoverEntity):
    _attr_name = None

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        opts = device["options"]
        self._open_time = float(opts.get("open_time") or 0)
        self._close_time = float(opts.get("close_time") or 0)
        self._timed = self._open_time > 0 and self._close_time > 0
        self._attr_device_class = CoverDeviceClass(opts.get("device_class", "shutter"))
        # A linked cover (ESPSomfy RTS…) knows its real position: copy it and
        # let it do "go to 40 %" itself instead of timing the movement here.
        self._linked = device.get("linked_entity") if device.get("mirror") else None
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if self.has_command(ROLE_STOP):
            features |= CoverEntityFeature.STOP
            if self._timed and not self._linked:
                features |= CoverEntityFeature.SET_POSITION
        if self._linked:
            self._timed = False
            if (self._linked or "").startswith("cover."):
                features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features
        self._position: float | None = 100.0 if self._timed else None
        self._closed: bool | None = None
        self._direction = 0  # +1 opening, -1 closing
        self._last_direction = 0  # of the last move, for the wall button
        self._state_entity: str | None = opts.get("state_entity")
        self._threshold = float(opts.get("state_threshold", 3.0))
        self._switch_entity: str | None = opts.get("switch_entity")
        self._switch_close_entity: str | None = opts.get("switch_close_entity")
        self._wall_maintained = opts.get("wall_type") == "maintained"
        self._power_on_allowed = bool(opts.get("power_on_allowed", True))
        self._power_up_delay = float(opts.get("power_up_delay", 1.0))
        self._meter = Meter(hub.hass, self._state_entity) if self._state_entity else None
        self._reliable = True  # False: the motor ran without a command of ours
        self._last_run: float | None = None  # seconds the motor ran in the last full travel
        self._own_at = float("-inf")  # monotonic time of our last command or stop
        self._move_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # --- state -----------------------------------------------------------
    @property
    def current_cover_position(self) -> int | None:
        return None if self._position is None else round(self._position)

    @property
    def is_closed(self) -> bool | None:
        if self._position is not None:
            return self._position <= 0
        return self._closed

    @property
    def is_opening(self) -> bool:
        return self._direction > 0

    @property
    def is_closing(self) -> bool:
        return self._direction < 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._meter is None:
            return None
        attrs: dict[str, Any] = {"position_reliable": self._reliable}
        if self._last_run is not None:
            attrs["last_run_seconds"] = round(self._last_run, 1)
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._state_entity:
            self.async_on_remove(
                async_track_state_change_event(self.hass, [self._state_entity], self._meter_event)
            )
        if walls := [e for e in (self._switch_entity, self._switch_close_entity) if e]:
            self.async_on_remove(async_track_state_change_event(self.hass, walls, self._wall_event))
        state = await self.async_get_last_state()
        if state is None:
            return
        if state.attributes.get("position_reliable") is False:
            self._reliable = False
        if self._timed and (pos := state.attributes.get("current_position")) is not None:
            self._position = float(pos)
        elif state.state in ("open", "closed"):
            self._closed = state.state == "closed"

    async def async_will_remove_from_hass(self) -> None:
        await self._async_cancel_move()
        await super().async_will_remove_from_hass()

    # --- relay, meter and wall button --------------------------------------
    async def _async_ensure_power(self) -> None:
        """Switch the motor's relay on when allowed; refuse the command otherwise."""
        if self.powered:
            return
        if not self._power_on_allowed:
            self.require_power()
        await self.hass.services.async_call(
            "homeassistant", "turn_on", {"entity_id": self.power_entity}, blocking=True
        )
        await asyncio.sleep(self._power_up_delay)  # the receiver boots

    @callback
    def power_changed(self, on: bool) -> None:
        if not on and self._move_task and not self._move_task.done():
            self._move_task.cancel()  # no power: it stopped where it was

    async def _async_running(self) -> bool | None:
        """Whether the motor runs, by the meter; None when it cannot be read."""
        state = self.hass.states.get(self._state_entity)
        if state is not None and state.state in (STATE_ON, STATE_OFF):
            return state.state == STATE_ON
        watts = await self._meter.async_read()
        return None if watts is None else watts > self._threshold

    @callback
    def _meter_event(self, event: Event[EventStateChangedData]) -> None:
        """The motor running without a command of ours: the original remote moved it."""
        if not feedback_on(event.data["new_state"], self._threshold) or not self._reliable:
            return
        if self._move_task and not self._move_task.done():
            return
        if time.monotonic() - self._own_at < OWN_WINDOW:
            return
        self._reliable = False  # which way it went cannot be told from the draw
        self.async_write_ha_state()

    @callback
    def _wall_event(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None:
            return
        valid = (STATE_ON, STATE_OFF)
        if old.state not in valid or new.state not in valid or old.state == new.state:
            return
        which = -1 if event.data["entity_id"] == self._switch_close_entity else 1
        self.hass.async_create_task(self.async_wall(which, new.state == STATE_ON))

    async def async_wall(self, which: int, pressed: bool) -> None:
        """A wall input changed: ``which`` is +1 for the only/up input, -1 for the down one."""
        can_stop = self.has_command(ROLE_STOP)
        if not self._wall_maintained and not pressed:
            return  # a push button being released
        if not self._switch_close_entity:
            await self.async_wall_step()
        elif self._wall_maintained and not pressed:
            if self._direction == which and can_stop:  # the rocker went back to 0
                await self.async_stop_cover()
        elif not self._wall_maintained and self._direction and can_stop:
            await self.async_stop_cover()
        elif which > 0:
            await self.async_open_cover()
        else:
            await self.async_close_cover()

    async def async_wall_step(self) -> None:
        """One wall input: stop while moving, else the other way than last time."""
        if self._direction and self.has_command(ROLE_STOP):
            await self.async_stop_cover()
        elif self.is_closed or (self._position != 100 and self._last_direction < 0):
            await self.async_open_cover()
        else:
            await self.async_close_cover()

    # --- movement --------------------------------------------------------
    async def _async_cancel_move(self) -> None:
        """Stop tracking movement and wait until the position estimate is final."""
        task, self._move_task = self._move_task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._direction = 0

    async def _async_move(self, direction: int, target: float) -> None:
        """Track the estimated position until ``target``; sends stop if mid-way.

        With a meter, a full travel (to 0 or 100) follows the motor instead of
        the clock: it ends when the motor stops at its limit switch.
        """
        travel = (self._open_time if direction > 0 else self._close_time) if self._timed else 0
        rate = 100 / travel if travel else 0  # % per second
        start_pos = self._position if self._position is not None else (0 if direction > 0 else 100)
        start = time.monotonic()
        full = target in (0, 100)
        follow = self._meter is not None and full
        if follow:
            duration = travel * OVERRUN + OVERRUN_EXTRA if travel else UNTIMED_MAX
        else:
            duration = abs(target - start_pos) / rate
        seen, quiet, stopped, last_running = False, 0, False, start
        try:
            while True:
                elapsed = time.monotonic() - start
                if self._meter is not None:
                    running = await self._async_running()
                    if running:
                        seen, quiet, last_running = True, 0, time.monotonic()
                    elif running is False:
                        quiet += 1
                        if (seen and quiet >= STOP_READINGS) or (not seen and elapsed >= START_GRACE):
                            stopped = True  # by itself: a limit switch, or the original remote
                            break
                    elapsed = time.monotonic() - start
                if elapsed >= duration:
                    break
                if rate:
                    position = start_pos + direction * rate * elapsed
                    if follow:  # not at the end until the motor says so
                        position = min(position, 99.0) if direction > 0 else max(position, 1.0)
                    self._position = max(0.0, min(100.0, position))
                self.async_write_ha_state()
                await asyncio.sleep(min(TICK, duration - elapsed))
            self._direction = 0
            if stopped and not seen and not full:
                self._position = start_pos  # the motor never ran
            elif full or not stopped:
                if rate:
                    self._position = target
                if follow:
                    self._reliable = True
                    self._last_run = last_running - start if seen else None
            if not full and not stopped:
                await self.async_send_role(ROLE_STOP)
        except asyncio.CancelledError:
            if rate:
                elapsed = time.monotonic() - start
                self._position = max(0.0, min(100.0, start_pos + direction * rate * elapsed))
            raise
        finally:
            self._direction = 0
            self._own_at = time.monotonic()
            self.async_write_ha_state()

    async def _async_go(self, direction: int, target: float) -> None:
        async with self._lock:
            await self._async_cancel_move()
            await self._async_ensure_power()
            self._own_at = time.monotonic()
            await self.async_send_role(ROLE_OPEN if direction > 0 else ROLE_CLOSE)
            self._last_direction = direction
            if self._linked:
                return  # the linked cover reports how it moves
            if not self._timed:
                self._closed = direction < 0
                if self._meter is None:
                    self.async_write_ha_state()
                    return
            self._direction = direction
            self.async_write_ha_state()
            self._move_task = self.hass.async_create_background_task(
                self._async_move(direction, target), f"rf_devices cover {self.entity_id}"
            )

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_go(1, 100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_go(-1, 0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        async with self._lock:
            await self._async_cancel_move()
            if self.powered:  # without power it is already stopped
                self._own_at = time.monotonic()
                await self.async_send_role(ROLE_STOP)
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        if self._linked:
            await self.hass.services.async_call(
                "cover", "set_cover_position",
                {"entity_id": self._linked, ATTR_POSITION: kwargs[ATTR_POSITION]}, blocking=True,
            )
            return
        target = float(kwargs[ATTR_POSITION])
        current = self._position if self._position is not None else 0
        if abs(target - current) < 1:
            return
        await self._async_go(1 if target > current else -1, target)

    @callback
    def mirror_state(self, state) -> None:
        """Copy the linked cover: position, movement, open/closed."""
        position = state.attributes.get("current_position")
        if position is not None:
            self._position = float(position)
        else:
            self._position = None
            if state.state in ("open", "closed"):
                self._closed = state.state == "closed"
        self._direction = 1 if state.state == "opening" else -1 if state.state == "closing" else 0

    async def async_follow_remote(self, role: str) -> bool:
        """The original remote moved the cover: track it without sending."""
        if role not in (ROLE_OPEN, ROLE_CLOSE, ROLE_STOP):
            return False
        if self._linked:
            return True  # the linked cover reports it
        async with self._lock:
            await self._async_cancel_move()
            if role != ROLE_STOP:
                direction = 1 if role == ROLE_OPEN else -1
                if self._timed:
                    self._direction = direction
                    self._move_task = self.hass.async_create_background_task(
                        self._async_move(direction, 100 if direction > 0 else 0),
                        f"rf_devices cover {self.entity_id}",
                    )
                else:
                    self._closed = direction < 0
            self.async_write_ha_state()
        return True

    async def async_set_assumed_position(self, position: int) -> None:
        """Service handler: correct the estimate without transmitting."""
        await self._async_cancel_move()
        self._reliable = True
        if self._timed:
            self._position = float(position)
        else:
            self._closed = position == 0
        self.async_write_ha_state()

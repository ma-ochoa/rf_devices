"""Shared on/off behaviour for lights and switches (toggle-only or on/off remotes)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .const import MODE_TOGGLE, ROLE_OFF, ROLE_ON, ROLE_TOGGLE
from .entity import RFEntity, feedback_on, last_on
from .meter import Meter

_LOGGER = logging.getLogger(__name__)

RETRY_EVERY = 0.5  # s between meter readings while checking a light command
RETRY_DEFAULT_AFTER = 4.0  # s for the lamp to show on the meter before resending
RETRY_MIN_JUMP_W = 3.0  # a smaller change on the meter is not the lamp
RETRY_MIN_SHOW = 2.5  # s a lamp needs to show a code on the meter; never resend sooner
RETRY_MAX = 3  # resends left for one command (one automatic, one more per "again")
RETRY_LAMP_FRACTION = 0.2  # a lamp is lit from this share of its draw: LED lamps start up slowly
RETRY_MOVING_W = 0.5  # W between two readings 0.5 s apart: the meter is still moving, do not judge


@dataclass
class _Pending:
    """A light command not yet seen on the meter."""

    target: bool
    role: str
    baseline: float  # meter reading before the code went out
    meter: Meter
    last_send: float  # loop time the code last went out
    resends: int = 1
    urgent: bool = False  # someone asked again: resend as soon as it is safe
    sending: bool = False
    task: asyncio.Task | None = field(default=None, repr=False)


class OnOffMixin(RFEntity):
    """On/off entity whose remote may only have a single toggle button.

    * Asking for the state it already believes it has sends nothing, so
      "Alexa, turn on" twice does not switch the light off.
    * An optional wall switch (e.g. a detached Shelly input) toggles the
      device on every change, whatever position it is in.
    * An optional feedback entity (a power sensor or any on/off entity)
      gives the real state, so it stays right even when the original
      remote is used.
    * With a power relay: while it is off the device is off and nothing is
      sent. It is only switched on for lights that allow it; never for fans.
    * ``rf_devices.set_state`` and the sync button correct the state without
      sending, for when there is no feedback.
    """

    _roles = {"toggle": ROLE_TOGGLE, "on": ROLE_ON, "off": ROLE_OFF}
    _state_key = "state_entity"
    _threshold_key = "state_threshold"
    # State after the relay feeding the device is switched on. Lights (and
    # ceiling fan lamps) normally come on by themselves.
    _on_at_power_up = True

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        # Assigned per instance (not as a class attribute of this mixin) so the
        # entity's cached ``is_on`` property is invalidated on every change.
        self._attr_is_on = False
        self._op_lock = asyncio.Lock()
        self.user_on_at = float("-inf")  # loop time someone last asked to turn it on
        self.user_off_at = float("-inf")  # ... and to turn it off
        self.sent_at = float("-inf")  # loop time the last on/off/toggle code was sent
        self._pending: _Pending | None = None  # last command, until the meter shows it

    @property
    def _mode(self) -> str:
        return self.device["options"].get("mode", MODE_TOGGLE)

    @property
    def _toggle_mode(self) -> bool:
        return self._mode == MODE_TOGGLE

    @property
    def _switch_entity(self) -> str | None:
        return self.device["options"].get("switch_entity")

    @property
    def _state_entity(self) -> str | None:
        return self.device["options"].get(self._state_key)

    @property
    def _threshold(self) -> float:
        return float(self.device["options"].get(self._threshold_key, 3.0))

    @property
    def _power_on_allowed(self) -> bool:
        return bool(self.device["options"].get("power_on_allowed"))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (restored := last_on(await self.async_get_last_state())) is not None:
            self._attr_is_on = restored
        if not self.powered:
            self._attr_is_on = False
        if self._state_entity:
            real = feedback_on(self.hass.states.get(self._state_entity), self._threshold)
            if real is not None:
                self._attr_is_on = real
            self.async_on_remove(
                async_track_state_change_event(self.hass, [self._state_entity], self._feedback_event)
            )
        # With a relay the wall switch drives the relay (mode A) or the relay
        # controller reads it (mode B); "wall only" is read by wall.py. Only
        # on its own does the entity listen.
        wall_only = self.device["options"].get("relay_mode") == "wall_only"
        if self._switch_entity and self.relay is None and not wall_only:
            self.async_on_remove(
                async_track_state_change_event(self.hass, [self._switch_entity], self._switch_changed)
            )

    # --- inputs ----------------------------------------------------------
    @callback
    def _switch_changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is None or new is None:
            return
        valid = (STATE_ON, STATE_OFF)
        if old.state not in valid or new.state not in valid or old.state == new.state:
            return
        self.hass.async_create_task(self._async_set(None))

    @callback
    def _feedback_event(self, event: Event[EventStateChangedData]) -> None:
        real = feedback_on(event.data["new_state"], self._threshold)
        if real is not None and real != self._attr_is_on:
            self._attr_is_on = real
            self.async_write_ha_state()

    @callback
    def power_changed(self, on: bool) -> None:
        if self._state_entity:
            return  # the feedback entity will tell
        self._attr_is_on = on and self._on_at_power_up

    # --- actions ---------------------------------------------------------
    async def _async_set(self, on: bool | None) -> None:
        """Set the state; ``None`` flips it. Serialised so fast flips stay in step."""
        pending = self._pending
        if pending is not None and on is not None and on == pending.target:
            # The same state asked for again before the lamp showed the last command on
            # the meter (an automation or a voice command repeating itself): insist on it,
            # never send a second toggle that would cancel the first.
            pending.resends = min(RETRY_MAX, pending.resends + 1)
            pending.urgent = True
            _LOGGER.debug("%s: asked again while unconfirmed; insisting on %s", self.entity_id, pending.target)
            return
        # A flip (``on is None``, the wall switch) is a new request to change the light, even if
        # the last command is not confirmed yet: the person sees the state change at once and
        # flips to switch it back. The check that follows aims at the new state, so a lost code
        # is resent by itself and the lamp ends up as the last flip says.
        self._cancel_retry()  # a different command replaces the check of the previous one
        async with self._op_lock:
            if on is None:
                on = not self._attr_is_on
            elif on == self._attr_is_on and self._toggle_mode:
                return
            if not self.powered:
                if not on:
                    self._attr_is_on = False
                    self.async_write_ha_state()
                    return
                if self.relay is not None and self._lights_at_power_up:
                    await self.relay.async_light_needs_power()
                elif self._power_on_allowed:
                    await self.hass.services.async_call(
                        "homeassistant", "turn_on", {"entity_id": self.power_entity}, blocking=True
                    )
                else:
                    raise HomeAssistantError(
                        f"{self.device['name']} has no power: {self.power_entity} is off"
                    )
                # The lamp comes on by itself when it gets power; nothing to send.
                self._attr_is_on = True
                self.async_write_ha_state()
                return
            await self._async_send_state(on)

    async def _async_send_state(self, on: bool) -> None:
        self.sent_at = self.hass.loop.time()
        role = self._roles["toggle"] if self._toggle_mode else self._roles["on" if on else "off"]
        meter = self._retry_meter()
        # The reading before the lamp can react, taken while the code goes out.
        before = self.hass.async_create_task(meter.async_read()) if meter else None
        # Show the new state when the code starts going out: the transmitter takes
        # 0.5-1 s to send it and everything that follows the entity (the mirror,
        # automations, the app) should not wait for that. If it fails, go back.
        previous = self._attr_is_on
        self._attr_is_on = on
        self.async_write_ha_state()
        try:
            await self.async_send_role(role)
        except BaseException:
            if before is not None:
                before.cancel()
            self._attr_is_on = previous
            self.async_write_ha_state()
            raise
        if meter is not None and before is not None:
            baseline = await before
            if baseline is not None:
                pending = _Pending(on, role, baseline, meter, self.hass.loop.time())
                self._pending = pending
                pending.task = self.hass.async_create_background_task(
                    self._async_watch(pending), f"rf_devices check {self.entity_id}"
                )

    # --- check a command on the meter, resend if the lamp ignored it ------
    @property
    def _retry_after(self) -> float:
        return float(self.device["options"].get("light_retry_after") or RETRY_DEFAULT_AFTER)

    def _retry_meter(self) -> Meter | None:
        """The meter that shows this light, if resending a missed command is on."""
        opts = self.device["options"]
        entity = opts.get(self._state_key)
        if not opts.get("light_retry") or not entity or not entity.startswith("sensor."):
            return None
        if self.hub.calibrating or self._motor_busy():
            return None
        return Meter(self.hass, entity)

    def _lamp_watts(self) -> float | None:
        """The lamp's draw, when a calibration knows it."""
        return None

    def _motor_busy(self) -> bool:
        """A motor on the same meter is changing speed: the meter cannot tell."""
        return False

    def _lamp_is_on(self, watts: float) -> bool:
        """Whether the meter shows the lamp lit (the motor is not changing: see _motor_busy)."""
        if (lamp := self._lamp_watts()) is not None:
            # Not half of its draw: the lamp of the bedroom takes ~3 s to reach full power
            # (7, 10, 27 W) and, judged at 4 s, a lamp that had reacted looked ignored.
            return watts >= max(RETRY_MIN_JUMP_W, lamp * RETRY_LAMP_FRACTION)
        return watts > self._threshold

    @property
    def command_unconfirmed(self) -> bool:
        """The last command has not shown on the meter yet."""
        return self._pending is not None

    @callback
    def _cancel_retry(self) -> None:
        pending, self._pending = self._pending, None
        if pending is not None and pending.task is not None and not pending.sending:
            pending.task.cancel()

    async def _async_watch(self, pending: _Pending) -> None:
        """Watch the meter after a command; resend it while the lamp has not moved.

        An RF code is sometimes not received (distance, interference). Once
        on its own after ``light_retry_after`` s, and once more each time
        someone asks again (but never before the lamp had ``RETRY_MIN_SHOW`` s
        to show the previous code, so two codes never cancel each other out).
        """
        loop = self.hass.loop
        previous: float | None = None
        try:
            while self._pending is pending:
                await asyncio.sleep(RETRY_EVERY)
                if not self.powered or self.hub.calibrating or self._motor_busy():
                    return
                watts = await pending.meter.async_read()
                moving = watts is not None and previous is not None and abs(watts - previous) > RETRY_MOVING_W
                previous = watts if watts is not None else previous
                # Confirmed when the lamp is as it was asked to be. Not "it changed since
                # before the command": with a toggle code, two quick commands (on, then
                # off) change nothing on the meter, and resending would flip the lamp.
                if watts is not None and self._lamp_is_on(watts) == pending.target:
                    return
                if moving:
                    continue  # still starting up or fading: wait for it to settle before judging
                wait = RETRY_MIN_SHOW if pending.urgent else self._retry_after
                if loop.time() < pending.last_send + wait:
                    continue
                if pending.resends <= 0:
                    return  # give up; the meter will correct the state
                async with self._op_lock:
                    if self._pending is not pending:
                        return
                    pending.resends -= 1
                    pending.urgent = False
                    pending.sending = True
                    try:
                        _LOGGER.info(
                            "%s: the lamp did not react (%s W); sending %s again",
                            self.entity_id, pending.baseline, pending.role,
                        )
                        self.sent_at = loop.time()
                        await self.async_send_role(pending.role)
                    finally:
                        pending.sending = False
                        pending.last_send = loop.time()
        finally:
            if self._pending is pending:
                self._pending = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.user_on_at = self.hass.loop.time()
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.user_off_at = self.hass.loop.time()
        await self._async_set(False)

    @callback
    def mirror_state(self, state) -> None:
        if state.state in (STATE_ON, STATE_OFF):
            self._attr_is_on = state.state == STATE_ON

    async def async_follow_remote(self, role: str) -> bool:
        if role not in self._roles.values():
            return False
        self._cancel_retry()  # the original remote was used: do not resend ours
        if self._state_entity or self.mirror_source:
            return True  # the real state comes from there
        async with self._op_lock:
            if role == self._roles["toggle"]:
                self._attr_is_on = not self._attr_is_on
            else:
                self._attr_is_on = role == self._roles["on"]
            self.async_write_ha_state()
        return True

    async def async_set_assumed_state(self, is_on: bool) -> None:
        """Service handler: change the state without transmitting."""
        self._cancel_retry()
        self._attr_is_on = is_on
        self.async_write_ha_state()

    @property
    def _lights_at_power_up(self) -> bool:
        return self._on_at_power_up

    async def async_toggle_from_wall(self) -> None:
        """Mode B: the wall switch was flipped."""
        await self._async_set(None)

    async def async_restore_from_wall(self, on: bool) -> None:
        """The flip that toggled the light at once was the start of a gesture: undo it."""
        await self._async_set(on)

    async def async_sync(self) -> None:
        """Sync button: flip the state in HA without transmitting."""
        self._cancel_retry()
        async with self._op_lock:
            self._attr_is_on = not self._attr_is_on
            self.async_write_ha_state()

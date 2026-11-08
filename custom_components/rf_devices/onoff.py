"""Shared on/off behaviour for lights and switches (toggle-only or on/off remotes)."""

from __future__ import annotations

import asyncio
import logging
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
        self._retry_task: asyncio.Task | None = None  # checking the last command on the meter
        self._retrying = False  # the check is resending: let it finish

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
        self._cancel_retry()  # a new command replaces the check of the previous one
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
        await self.async_send_role(role)
        self._attr_is_on = on
        self.async_write_ha_state()
        if meter is not None and before is not None:
            baseline = await before
            if baseline is not None:
                self._retry_task = self.hass.async_create_background_task(
                    self._async_check_sent(meter, role, baseline),
                    f"rf_devices check {self.entity_id}",
                )

    # --- check a command on the meter, resend once if the lamp ignored it --
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

    def _lamp_changed(self, before: float, after: float) -> bool:
        if (lamp := self._lamp_watts()) is not None:
            return abs(after - before) >= max(RETRY_MIN_JUMP_W, lamp / 2)
        return (before > self._threshold) != (after > self._threshold)

    @callback
    def _cancel_retry(self) -> None:
        if self._retry_task is not None and not self._retrying:
            self._retry_task.cancel()
        self._retry_task = None

    async def _async_check_sent(self, meter: Meter, role: str, before: float) -> None:
        """Watch the meter after a command; if the lamp never moved, send it once more.

        An RF code is sometimes not received (distance, interference, a busy
        transmitter). Without this the light only looks switched in Home
        Assistant, until the meter corrects it, and the wall switch seems dead.
        """
        loop = self.hass.loop
        end = loop.time() + self._retry_after
        while loop.time() < end:
            await asyncio.sleep(RETRY_EVERY)
            if not self.powered or self.hub.calibrating or self._motor_busy():
                return
            watts = await meter.async_read()
            if watts is not None and self._lamp_changed(before, watts):
                return
        async with self._op_lock:
            if self._retry_task is not asyncio.current_task():
                return  # replaced by a newer command meanwhile
            self._retrying = True
            try:
                _LOGGER.info(
                    "%s: the lamp did not react within %.1f s (%s W); sending %s again",
                    self.entity_id, self._retry_after, before, role,
                )
                self.sent_at = loop.time()
                await self.async_send_role(role)
            finally:
                self._retrying = False
                self._retry_task = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.user_on_at = self.hass.loop.time()
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.user_off_at = self.hass.loop.time()
        await self._async_set(False)

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

    async def async_sync(self) -> None:
        """Sync button: flip the state in HA without transmitting."""
        self._cancel_retry()
        async with self._op_lock:
            self._attr_is_on = not self._attr_is_on
            self.async_write_ha_state()

"""Shared on/off behaviour for lights and switches (toggle-only or on/off remotes)."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .const import MODE_TOGGLE, ROLE_OFF, ROLE_ON, ROLE_TOGGLE
from .entity import RFEntity, feedback_on, last_on


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
        if self._toggle_mode:
            await self.async_send_role(self._roles["toggle"])
        else:
            await self.async_send_role(self._roles["on" if on else "off"])
        self._attr_is_on = on
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.user_on_at = self.hass.loop.time()
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.user_off_at = self.hass.loop.time()
        await self._async_set(False)

    async def async_set_assumed_state(self, is_on: bool) -> None:
        """Service handler: change the state without transmitting."""
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
        async with self._op_lock:
            self._attr_is_on = not self._attr_is_on
            self.async_write_ha_state()

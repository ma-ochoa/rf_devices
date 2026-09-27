"""Wall switch gestures: count the flips of a detached switch.

A rocker switch that no longer drives the load only reports changes, so a
"gesture" is the number of flips in quick succession (each within
``wall_window`` seconds of the previous one). Every count has an action,
chosen in the panel:

    1 flip  → toggle the light
    2 flips → fan on, or next speed (bouncing back down from the top one)
    3 flips → fan off
    4 flips → nothing (or whatever is configured)

When only one flip has an action there is nothing to wait for, so it acts at
once. Otherwise it waits for the window to pass after the last flip. Five
or more flips count as four: fast back-and-forths are hard to count. Every gesture is also
fired as the ``rf_devices_wall_gesture`` event, for automations.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import ROLE_LIGHT_COLOR, WALL_ACTIONS
from .entity import find_by_unique_id

_LOGGER = logging.getLogger(__name__)

EVENT_WALL_GESTURE = "rf_devices_wall_gesture"
MAX_FLIPS = 4
DEFAULT_WINDOW = 0.6  # seconds between flips of one gesture

ACTIONS = WALL_ACTIONS


def default_actions(device: dict) -> dict[str, str]:
    """Without a configured table: one flip toggles the light (or the fan)."""
    opts = device.get("options", {})
    has_light = device["type"] != "fan" or opts.get("light", "none") != "none"
    return {"1": "light_toggle" if has_light else "fan_toggle"}


def gesture_actions(device: dict) -> dict[int, str]:
    opts = device.get("options", {})
    table = opts["wall_actions"] if opts.get("wall_actions") is not None else default_actions(device)
    return {
        int(count): action
        for count, action in table.items()
        if str(count).isdigit() and 1 <= int(count) <= MAX_FLIPS and action in ACTIONS
    }


def gesture_window(device: dict) -> float:
    return float(device.get("options", {}).get("wall_window", DEFAULT_WINDOW))


class WallGestures:
    """Turns the flips of one wall switch into actions on one RF Devices device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: dict,
        entity: str,
        on_flip: Callable[[], None] | None = None,
        power_off: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.hass = hass
        self.device = device
        self.entity = entity
        self._on_flip = on_flip  # e.g. confirm the press to the relay's fallback script
        self._power_off = power_off
        self.actions = gesture_actions(device)
        self.window = gesture_window(device)
        self.count = 0
        self._timer: Callable[[], None] | None = None
        self._going_down = False  # fan_step: direction of the next step

    # --- lifecycle --------------------------------------------------------
    @callback
    def async_start(self) -> Callable[[], None]:
        unsub = async_track_state_change_event(self.hass, [self.entity], self._changed)

        def stop() -> None:
            unsub()
            self._cancel()

        return stop

    def _cancel(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None

    # --- flips ------------------------------------------------------------
    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        valid = (STATE_ON, STATE_OFF)
        if old is None or new is None or old.state not in valid or new.state not in valid:
            return
        if old.state != new.state:
            self.flip()

    @callback
    def flip(self) -> None:
        if self._on_flip is not None:
            self._on_flip()
        self._cancel()
        self.count += 1
        # Only one flip does something: nothing to wait for. Otherwise wait,
        # even past the highest configured count, so a fourth flip is not
        # taken as the first of a new gesture.
        if not any(a != "none" for n, a in self.actions.items() if n > 1):
            self._finish()
        else:
            self._timer = async_call_later(self.hass, self.window, self._timeout)

    @callback
    def _timeout(self, _now) -> None:
        self._timer = None
        self._finish()

    @callback
    def _finish(self) -> None:
        count, self.count = self.count, 0
        # More flips than the table has count as the last row ("4 or more").
        action = self.actions.get(min(count, MAX_FLIPS), "none")
        self.hass.bus.async_fire(
            EVENT_WALL_GESTURE,
            {"device_id": self.device["id"], "name": self.device["name"], "flips": count, "action": action},
        )
        if action != "none":
            self.hass.async_create_task(self._async_run(action), f"rf_devices wall {action}")

    # --- actions ----------------------------------------------------------
    def _entity(self, key: str) -> Any:
        return find_by_unique_id(self.hass, f"{self.device['id']}_{key}")

    def _light(self) -> Any:
        return self._entity("fan_light" if self.device["type"] == "fan" else self.device["type"])

    def _fan(self) -> Any:
        return self._entity("fan") if self.device["type"] == "fan" else None

    async def _async_run(self, action: str) -> None:
        _LOGGER.debug("%s: wall gesture → %s", self.device["name"], action)
        try:
            await self._async_action(action)
        except HomeAssistantError as err:
            _LOGGER.warning("Wall switch of %s (%s): %s", self.device["name"], action, err)

    async def _async_action(self, action: str) -> None:
        light, fan = self._light(), self._fan()
        if action.startswith("light_") and light is None:
            return
        if action.startswith("fan_") and fan is None:
            return
        if action == "light_toggle":
            await light.async_toggle_from_wall()
        elif action == "light_on":
            await light.async_turn_on()
        elif action == "light_off":
            await light.async_turn_off()
        elif action == "light_color":
            button = self._entity(ROLE_LIGHT_COLOR)
            if button is not None:
                await button.async_press()
        elif action in ("fan_step", "fan_up", "fan_down"):
            await self._async_fan_step(fan, action)
        elif action == "fan_toggle":
            await (fan.async_turn_off() if fan.is_on else fan.async_turn_on())
        elif action == "fan_on":
            await fan.async_turn_on()
        elif action == "fan_off":
            await fan.async_turn_off()
        elif action == "fan_direction":
            if fan.current_direction is not None:
                await fan.async_set_direction("reverse" if fan.current_direction == "forward" else "forward")
        elif action == "all_off":
            if fan is not None and fan.is_on:
                await fan.async_turn_off()
            if light is not None and light.is_on:
                await light.async_turn_off()
        elif action == "power_off" and self._power_off is not None:
            await self._power_off()

    async def _async_fan_step(self, fan: Any, action: str) -> None:
        if not fan.is_on:
            self._going_down = False
            await fan.async_turn_on()
            return
        top = fan.speed_count
        speed = fan.speed_of(fan.percentage or 0)
        if action == "fan_down":
            target = max(1, speed - 1)
        elif action == "fan_up":
            target = min(top, speed + 1)
        else:  # fan_step: up to the top, then back down to 1, and up again
            if speed >= top:
                self._going_down = True
            elif speed <= 1:
                self._going_down = False
            target = speed - 1 if self._going_down else speed + 1
            target = max(1, min(top, target))
        if target != speed:
            await fan.async_set_percentage(fan.pct_of(target))

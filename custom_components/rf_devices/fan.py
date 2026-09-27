"""Ceiling/standing fans driven by RF codes.

Remotes differ a lot, so the model is configurable:

* power: a dedicated "off" button, or one power button that alternates;
* speeds: one button per speed (pressing one also starts the fan);
* direction: none, one button that reverses, or summer/winter buttons;
* presets: special modes such as "breeze", each with its own button.

A relay feeding the fan (``power_entity``) is only switched on to start the
fan when ``fan_power_on`` allows it (relay.py): powering a ceiling fan
usually lights its lamp, which must not happen at night because someone
asked to change the fan.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.fan import (
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ranged_value_to_percentage,
)

from .calibration import Estimate, PowerAligner
from .const import (
    MODE_BUTTONS,
    MODE_NONE,
    MODE_TOGGLE,
    PRESET_PREFIX,
    ROLE_DIRECTION,
    ROLE_FORWARD,
    ROLE_OFF,
    ROLE_POWER,
    ROLE_REVERSE,
    SPEED_PREFIX,
)
from .entity import RFEntity, find_by_unique_id, setup_platform_entities
from .meter import Meter

_LOGGER = logging.getLogger(__name__)

PCT_SLACK = 1  # percentage points a request may exceed a speed's value

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_platform_entities(hass, entry, async_add_entities, "fan", RFFan)


class RFFan(RFEntity, FanEntity):
    _attr_name = None

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        opts = device["options"]
        self._speeds = int(opts.get("speeds", 3))
        self._power_toggle = opts.get("power") == MODE_TOGGLE
        self._direction_mode = opts.get("direction", MODE_NONE)
        self._presets: list[str] = list(opts.get("presets", []))
        self._attr_speed_count = self._speeds
        self._attr_percentage = 0
        self._attr_preset_mode = None
        self._attr_preset_modes = self._presets or None
        self._attr_current_direction = (
            DIRECTION_FORWARD if self._direction_mode != MODE_NONE else None
        )
        features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self._direction_mode != MODE_NONE:
            features |= FanEntityFeature.DIRECTION
        if self._presets:
            features |= FanEntityFeature.PRESET_MODE
        self._attr_supported_features = features
        self._last_speed = 1
        self._op_lock = asyncio.Lock()
        # True while the current speed is the one RF Devices sent (not corrected
        # from a reading): the aligner never overrules it if the reading fits.
        self._own_speed = False
        self._gap: float | None = None  # pause before the first command after a power-up

    @property
    def extra_state_attributes(self) -> dict:
        """The percentage of each speed, so dashboards can send exact values."""
        return {"speed_percentages": self._table}

    @property
    def is_on(self) -> bool:
        return bool(self._attr_percentage) or self._attr_preset_mode is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in ("on", "off"):
            attrs = state.attributes
            pct = attrs.get("percentage") or 0
            if pct:
                self._last_speed = self._speed_of(pct)
            if state.state == "on":
                self._attr_percentage = pct
                if attrs.get("preset_mode") in self._presets:
                    self._attr_preset_mode = attrs["preset_mode"]
            if self._direction_mode != MODE_NONE and attrs.get("direction") in (
                DIRECTION_FORWARD,
                DIRECTION_REVERSE,
            ):
                self._attr_current_direction = attrs["direction"]
        if not self.powered:
            self._set_off()
        opts = self.device["options"]
        if opts.get("calibration") and opts.get("light_state_entity"):
            aligner = PowerAligner(
                self.hass,
                Meter(self.hass, opts["light_state_entity"]),
                opts["calibration"],
                self._apply_estimate,
                self._color_index,
                self._colour_from_jump,
                self._speed_state,
            )
            self.async_on_remove(aligner.async_start())

    @callback
    def _color_index(self) -> int | None:
        select = find_by_unique_id(self.hass, f"{self.device['id']}_color")
        return select.index if select is not None else None

    @callback
    def _apply_estimate(self, estimate: Estimate) -> None:
        """Correct fan and light from a settled meter reading (nothing is sent)."""
        if self.hub.calibrating or self._op_lock.locked() or not self.powered:
            return
        changed = False
        if not estimate.fan_on and self.is_on:
            self._set_off()
            changed = True
        elif estimate.fan_on:
            speed = estimate.speed or (self._last_speed if self.is_on else None)
            if speed is None:
                speed = self._last_speed
            pct = self._pct(speed)
            if not self.is_on or (estimate.speed and pct != self._attr_percentage):
                self._last_speed = speed
                self._attr_percentage = pct
                self._attr_preset_mode = None
                self._own_speed = False  # from now on the reading, not a command
                changed = True
        if changed:
            _LOGGER.info("%s re-aligned from power reading: %s", self.entity_id, estimate)
            self.async_write_ha_state()
        light = find_by_unique_id(self.hass, f"{self.device['id']}_fan_light")
        if light is not None and hasattr(light, "async_apply_measured"):
            light.async_apply_measured(estimate.light)

    @callback
    def _speed_state(self) -> tuple[int | None, bool]:
        """Current speed (0 = off) and whether RF Devices set it itself."""
        if not self.is_on:
            return 0, False
        return self._last_speed, self._own_speed

    @callback
    def _colour_from_jump(self, mode: int) -> None:
        """The aligner recognised a colour press by its jump in draw."""
        if self.hub.calibrating:
            return
        select = find_by_unique_id(self.hass, f"{self.device['id']}_color")
        if select is not None:
            select.async_set_measured(mode)

    # --- calibration helpers (used by the wizard) --------------------------
    async def async_calibration_speed(self, speed: int) -> None:
        async with self._op_lock:
            await self._async_speed(speed)
            self.async_write_ha_state()

    async def async_calibration_off(self) -> None:
        async with self._op_lock:
            await self._async_off()
            self.async_write_ha_state()

    @callback
    def power_changed(self, on: bool) -> None:
        # Without power it is stopped; when power returns these fans stay stopped.
        self._set_off()

    def _set_off(self) -> None:
        self._attr_percentage = 0
        self._attr_preset_mode = None

    @property
    def _table(self) -> list[int]:
        """Percentage of each speed (ascending); even split unless configured."""
        custom = list(self.device["options"].get("speed_percentages") or [])
        if len(custom) == self._speeds and custom == sorted(custom):
            return custom
        return [ranged_value_to_percentage((1, self._speeds), n) for n in range(1, self._speeds + 1)]

    def _speed_of(self, percentage: int) -> int:
        """Speed for a percentage: its range in the table, or the number itself if small."""
        if self.device["options"].get("small_pct_is_speed", True) and 1 <= percentage <= self._speeds:
            if percentage not in self._table:  # an actual table value wins
                return int(percentage)
        for speed, upper in enumerate(self._table, start=1):
            # One point of slack: 4 × 16.67 % arrives as 67 %, which is speed 4.
            if percentage <= upper + PCT_SLACK:
                return speed
        return self._speeds

    def _pct(self, speed: int) -> int:
        return self._table[max(1, min(self._speeds, speed)) - 1]

    # Public for the wall switch gestures.
    speed_of = _speed_of
    pct_of = _pct

    # --- actions ---------------------------------------------------------
    async def _async_need_power(self) -> None:
        """Fan commands with the relay off: the relay controller decides (never by default)."""
        if self.powered:
            return
        if self.relay is not None:
            self._gap = await self.relay.async_fan_needs_power()
        else:
            self.require_power()

    async def async_send_role(
        self, role: str, hold: float | None = None, interval: float | None = None
    ) -> None:
        """The first command after a power-up uses its own pause, then gets checked."""
        gap, self._gap = self._gap, None
        if gap is not None and interval is None:
            interval = gap
        await super().async_send_role(role, hold, interval)
        if gap is not None and self.relay is not None:
            self.relay.schedule_light_check()

    async def _async_speed(self, speed: int) -> None:
        """Speed buttons also start the fan."""
        await self._async_need_power()
        await self.async_send_role(f"{SPEED_PREFIX}{speed}")
        self._own_speed = True
        self._last_speed = speed
        self._attr_percentage = self._pct(speed)
        self._attr_preset_mode = None

    async def _async_off(self) -> None:
        if not self.powered or not self.is_on and self._power_toggle:
            # Nothing to do: already stopped (and a toggle would start it).
            self._set_off()
            return
        await self.async_send_role(ROLE_POWER if self._power_toggle else ROLE_OFF)
        self._set_off()

    async def async_set_percentage(self, percentage: int) -> None:
        async with self._op_lock:
            if percentage:
                await self._async_speed(self._speed_of(percentage))
            else:
                await self._async_off()
            self.async_write_ha_state()

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        async with self._op_lock:
            await self._async_need_power()
            if preset_mode:
                await self._async_preset(preset_mode)
            elif percentage:
                await self._async_speed(self._speed_of(percentage))
            elif self.is_on:
                pass
            else:
                # A speed code, not the power button: remotes differ in what
                # speed "power" resumes, a speed code is always predictable.
                wanted = int(self.device["options"].get("turn_on_speed", 1))
                await self._async_speed(wanted or self._last_speed)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        async with self._op_lock:
            await self._async_off()
            self.async_write_ha_state()

    async def _async_preset(self, preset_mode: str) -> None:
        await self._async_need_power()
        index = self._presets.index(preset_mode) + 1
        await self.async_send_role(f"{PRESET_PREFIX}{index}")
        self._attr_preset_mode = preset_mode
        if not self._attr_percentage:
            self._attr_percentage = self._pct(self._last_speed)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        async with self._op_lock:
            await self._async_preset(preset_mode)
            self.async_write_ha_state()

    async def async_set_direction(self, direction: str) -> None:
        async with self._op_lock:
            await self._async_need_power()
            if self._direction_mode == MODE_BUTTONS:
                await self.async_send_role(
                    ROLE_FORWARD if direction == DIRECTION_FORWARD else ROLE_REVERSE
                )
            elif direction != self._attr_current_direction:
                await self.async_send_role(ROLE_DIRECTION)
            self._attr_current_direction = direction
            self.async_write_ha_state()

    # --- corrections without sending --------------------------------------
    async def async_set_assumed_state(self, is_on: bool, percentage: int | None = None) -> None:
        if not is_on:
            self._set_off()
        else:
            speed = self._speed_of(percentage) if percentage else self._last_speed
            self._last_speed = speed
            self._attr_percentage = self._pct(speed)
        self.async_write_ha_state()

    async def async_sync(self) -> None:
        """Sync button: flip on/off in HA without transmitting."""
        async with self._op_lock:
            if self.is_on:
                self._set_off()
            else:
                self._attr_percentage = self._pct(self._last_speed)
            self.async_write_ha_state()

"""Covers (blinds, shutters, awnings…) driven by RF codes.

With travel times configured the position is estimated from how long the
cover has been moving, and set_position sends "stop" at the right moment.
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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ROLE_CLOSE, ROLE_OPEN, ROLE_STOP
from .entity import RFEntity, setup_platform_entities

TICK = 0.5  # seconds between position updates while moving

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
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if self.code(ROLE_STOP):
            features |= CoverEntityFeature.STOP
            if self._timed:
                features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features
        self._position: float | None = 100.0 if self._timed else None
        self._closed: bool | None = None
        self._direction = 0  # +1 opening, -1 closing
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is None:
            return
        if self._timed and (pos := state.attributes.get("current_position")) is not None:
            self._position = float(pos)
        elif state.state in ("open", "closed"):
            self._closed = state.state == "closed"

    async def async_will_remove_from_hass(self) -> None:
        await self._async_cancel_move()
        await super().async_will_remove_from_hass()

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
        """Track the estimated position until ``target``; sends stop if mid-way."""
        travel = self._open_time if direction > 0 else self._close_time
        rate = 100 / travel  # % per second
        start_pos = self._position if self._position is not None else (0 if direction > 0 else 100)
        start = time.monotonic()
        duration = abs(target - start_pos) / rate
        try:
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= duration:
                    break
                self._position = start_pos + direction * rate * elapsed
                self.async_write_ha_state()
                await asyncio.sleep(min(TICK, duration - elapsed))
            self._position = target
            self._direction = 0
            if 0 < target < 100:
                await self.async_send_role(ROLE_STOP)
        except asyncio.CancelledError:
            elapsed = time.monotonic() - start
            self._position = max(0.0, min(100.0, start_pos + direction * rate * elapsed))
            raise
        finally:
            self._direction = 0
            self.async_write_ha_state()

    async def _async_go(self, direction: int, target: float) -> None:
        async with self._lock:
            await self._async_cancel_move()
            await self.async_send_role(ROLE_OPEN if direction > 0 else ROLE_CLOSE)
            if not self._timed:
                self._closed = direction < 0
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
            await self.async_send_role(ROLE_STOP)
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        target = float(kwargs[ATTR_POSITION])
        current = self._position if self._position is not None else 0
        if abs(target - current) < 1:
            return
        await self._async_go(1 if target > current else -1, target)

    async def async_set_assumed_position(self, position: int) -> None:
        """Service handler: correct the estimate without transmitting."""
        await self._async_cancel_move()
        if self._timed:
            self._position = float(position)
        else:
            self._closed = position == 0
        self.async_write_ha_state()

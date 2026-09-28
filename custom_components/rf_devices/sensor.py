"""Sensors on the device page: live power draw and the aligner's reading."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .calibration import (
    TREND_SLOPE,
    TREND_WINDOW,
    _lamp_offset,
    _slope,
    classify,
    read_watts,
    speed_position,
)
from .const import DOMAIN
from .entity import RFEntity, feedback_on, find_by_unique_id, setup_platform_entities
from .meter import Meter

LIVE_EVERY = timedelta(seconds=2)

# Nothing is polled; commands are queued by the hub, not by the platform.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def factory(hub, device, key):
        if key == "power":
            return RFPowerSensor(hub, device, key)
        if key == "speed_estimate":
            return RFSpeedEstimateSensor(hub, device, key)
        return RFEstimateSensor(hub, device, key)

    setup_platform_entities(hass, entry, async_add_entities, "sensor", factory)


class _MeterMirror(RFEntity, SensorEntity):
    """Follows the meter chosen for the device and refreshes with it."""

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        opts = device["options"]
        self._meter: str = opts.get("state_entity") or opts.get("light_state_entity")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [self._meter], self._meter_changed)
        )

    @callback
    def _meter_changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        state = self.hass.states.get(self._meter)
        return state is not None and state.state not in ("unavailable", "unknown")


class RFPowerSensor(_MeterMirror):
    """Live draw (or on/off) of the meter linked to the device."""

    _attr_translation_key = "power"

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        self._numeric = self._meter.startswith("sensor.")
        self._live: float | None = None
        self._reader: Meter | None = None
        if self._numeric:
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 1

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._numeric:
            reader = Meter(self.hass, self._meter)
            if reader.direct:
                # The meter pushes ~1 W steps now and then; read it live instead.
                self._reader = reader
                self.async_on_remove(
                    async_track_time_interval(self.hass, self._async_poll, LIVE_EVERY)
                )

    async def _async_poll(self, _now) -> None:
        if self._reader is None or not self._reader.direct:
            return
        value = await self._reader.async_read()
        if value is not None and value != self._live:
            self._live = value
            self.async_write_ha_state()

    @callback
    def _meter_changed(self, event: Event[EventStateChangedData]) -> None:
        self._live = None  # a fresh push wins until the next live reading
        self.async_write_ha_state()

    @property
    def native_value(self):
        if self._numeric:
            return self._live if self._live is not None else read_watts(self.hass, self._meter)
        on = feedback_on(self.hass.states.get(self._meter), 0)
        return None if on is None else ("on" if on else "off")

    @property
    def extra_state_attributes(self) -> dict:
        return {"source": self._meter, "live": bool(self._reader and self._reader.direct)}


class RFEstimateSensor(_MeterMirror):
    """What the calibration table makes of the current reading."""

    _attr_translation_key = "estimate"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "light", "fan", "fan_light", "unknown"]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Follow the integration's own power sensor too: it reads the meter live.
        power = er.async_get(self.hass).async_get_entity_id(
            "sensor", DOMAIN, f"{self.device['id']}_power"
        )
        if power:
            self._power_entity = power
            self.async_on_remove(
                async_track_state_change_event(self.hass, [power], self._meter_changed)
            )

    def _estimate(self):
        watts = None
        if getattr(self, "_power_entity", None):
            watts = read_watts(self.hass, self._power_entity)
        if watts is None:
            watts = read_watts(self.hass, self._meter)
        if watts is None:
            return None, None
        select = find_by_unique_id(self.hass, f"{self.device['id']}_color")
        mode = select.index if select is not None else None
        return watts, classify(self.device["options"]["calibration"], watts, mode)

    @property
    def native_value(self) -> str:
        _, estimate = self._estimate()
        if estimate is None:
            return "unknown"
        if estimate.fan_on:
            return "fan_light" if estimate.light else "fan"
        return "light" if estimate.light else "off"

    @property
    def extra_state_attributes(self) -> dict:
        watts, estimate = self._estimate()
        return {"watts": watts, "speed": estimate.speed if estimate else None}


class RFSpeedEstimateSensor(RFEstimateSensor):
    """Approximate fan speed in %, followed continuously while the motor ramps.

    The motor's draw (the lamp's subtracted when it is on) is placed between
    the calibrated speeds, so a PWM motor speeding up or slowing down shows
    where it is on its way; ``trend`` tells which way it is going.
    """

    _attr_translation_key = "speed_estimate"
    _attr_device_class = None
    _attr_options = None
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, hub, device, key) -> None:
        super().__init__(hub, device, key)
        self._history: list[tuple[float, float]] = []
        self._position: float | None = None
        self._trend = "stable"

    @callback
    def _meter_changed(self, event: Event[EventStateChangedData]) -> None:
        self._update()
        super()._meter_changed(event)

    def _update(self) -> None:
        watts, estimate = self._estimate()
        if watts is None:
            return
        now = self.hass.loop.time()
        self._history = [(t, v) for t, v in self._history if t >= now - TREND_WINDOW]
        self._history.append((now, watts))
        slope = _slope(self._history) if len(self._history) > 2 else 0.0
        self._trend = (
            "accelerating" if slope > TREND_SLOPE else "decelerating" if slope < -TREND_SLOPE else "stable"
        )
        if estimate is None:
            self._position = None
            return
        if not estimate.fan_on:
            self._position = 0.0
            return
        calibration = self.device["options"]["calibration"]
        motor = watts - (_lamp_offset(calibration, estimate.light_mode) if estimate.light else 0.0)
        direction = {"accelerating": "up", "decelerating": "down"}.get(self._trend)
        self._position = speed_position(calibration, motor, direction)

    @property
    def native_value(self) -> float | None:
        if self._position is None:
            return None
        speeds = len(self.device["options"]["calibration"]["speeds"])
        return round(self._position / speeds * 100, 1)

    @property
    def extra_state_attributes(self) -> dict:
        watts, _ = self._estimate()
        return {
            "watts": watts,
            "speed": None if self._position is None else round(self._position, 2),
            "trend": self._trend,
        }

# Changelog

## 0.10.1

- Panel: fan and light button chips grouped on their own lines in the device list.
- README: one-click "Open in HACS" button.

## 0.10.0 — first public release

- Visual panel to learn, clean, test, export and import Broadlink RF codes.
- Device types: light, switch, cover, fan (with optional light), buttons.
- Fans: speeds with a percentage table, direction, presets, timers; turn on by a speed code.
- Lights: colour-temperature modes with names and power-up behaviour, brightness by held buttons.
- A fan's named light is an independent device; the panel groups both as one remote.
- Real state from a feedback entity or from a power calibration (up/down speeds, colour steps).
- Relay and wall switch: modes A (coupled), B (detached) and wall switch only; Shelly adapter
  with live power, detach/attach and a per-press confirmed fallback script.
- Wall-switch gestures (1–4 flips) with configurable actions and the `rf_devices_wall_gesture` event.
- Broadlink safeguards, transmit queue, diagnostics, services to correct assumed state.

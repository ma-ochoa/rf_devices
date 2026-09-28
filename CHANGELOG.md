# Changelog

## 0.11.4

- Shelly Gen1 meters (e.g. Shelly 1PM) are read live from `/status`, like Gen2+ ones: exact lamp
  values in calibrations and a correct lamp check after powering the relay.
- Calibration detects each fan's pace by itself: a reading is settled once flat for at least 15 s
  and half the time waited (at most 60 s), with no fixed one-minute minimum. A fast motor is done
  in ~30 s per speed; a slow PWM one is still followed for minutes.
- Quick light calibration: the lamp is checked again once the fan has settled, even if the meter
  reports nothing new (it could be left showing off while lit).

## 0.11.3

- Quick light calibration (1–2 min, fan stopped): measures idle and the lamp in each colour mode.
  Without the full table, the fan's light then follows the meter: by level with the fan stopped,
  by sudden jumps of about the lamp's watts while it runs. With a full table, it refreshes its
  lamp values.
- Panel: restored the missing "Power" label in the live chips.

## 0.11.2

- A device's relay, wall switch or meter can no longer be one of RF Devices' own entities (panel and
  server). Choosing the device's own light as its relay and taking the relay's name renamed that
  light after itself.

## 0.11.1

- Live calibration no longer blocked by wizard values taken too early: order and "reads as another
  speed" are checked only against values already learned live, and larger corrections (up to
  60 %) are accepted. On the tested fan the whole table was ~30 % low.

## 0.11.0

- Live calibration: after an own speed command, with the light off, the settled draw (up to
  15 min later) corrects that speed's up/down value. Implausible readings are refused.
- New "Estimated speed" sensor (%): the motor's position between the calibrated speeds, with a
  `trend` attribute, so a PWM motor can be followed while it speeds up or slows down.
- A settled reading above the top speed's value is the top speed (it was left unrecognised).

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

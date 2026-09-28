# Changelog

## 0.12.0-iotorero.1 (test build)

- New: **`radio_frequency` transmitters** (Home Assistant 2026.5+). Codes are sent as raw timings
  through the core RF helper, so any RF adapter Home Assistant supports can be used, such as an
  ESPHome `ir_rf_proxy` (Athom / IoTorero RF433-IR remote, firmware 3.0.8+).
- New: **learning with an ESPHome RF receiver**. No frequency sweep: one press is enough.
  Received bursts are joined, noise is dropped and the capture is cleaned like a Broadlink one.
- Transmitters are now adapters (`transmitters/`), like relays. The Broadlink behaviour
  (learning, safeguards, power-cycling) is unchanged.
- Codes are still stored in the Broadlink format and are converted when sent through a
  `radio_frequency` entity.
- Requires Home Assistant 2026.5 or newer.

## 0.11.8

- Live calibration of the lamp: each time the lamp switches with the fan stopped, its real draw
  (settled level after minus before) updates that colour mode's value, the jump size and the
  table's "with light" column. Lamps drift with temperature (a tested one: 35.8 to 37.8 W), which
  made the lamp read as "lamp + slowest speed". Implausible values are refused; it follows the
  "Live calibration" option. Works with the full and the quick lamp calibration.

## 0.11.7

- Instant light detection when the original remote is used: a change of about the lamp's draw from
  the last steady value switches the light at once, from the meter's own report or the live
  reading, whichever comes first (tested: 0-1 s after the lamp changes, Shelly Gen1 and Gen2).
  Values in passing (a lamp fading, a motor ramping) are ignored. The fan is only decided on
  steady readings, and not at all when the whole change is the lamp's jump.
- The light ignores the meter for 6 s after our own command (HA, voice, wall switch): a lamp that
  fades in could be turned back off by an early reading.
- Live readings of one device are shared for 0.8 s between callers (aligner, sensor, panel): a
  Shelly Gen1 timed out when asked by several at once.
- A running preset (e.g. Breeze, whose draw swings between speeds on purpose) is no longer replaced
  by a speed from a reading.
- Fixed a deprecated device-registry lookup (HA 2027.8) and an error logged when Home Assistant
  stops during a live reading.

## 0.11.5

- Quick light calibration: a change is read until it settles (live, reading by reading) and the
  settled values before and after are compared, so a lamp that lights in two steps or a meter
  that reports a change in pieces is still recognised. With a live meter the wait after a fan
  change drops from 90 s to 15 s. Tested with the original remote while the fan was running and
  stopped: the light followed in 1-3 s.

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

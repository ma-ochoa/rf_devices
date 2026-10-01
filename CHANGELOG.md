# Changelog

## 0.12.0-labs.1 (test build, `labs` branch)

Everything in this build is untested on real hardware: it is meant for users who try it and send
the panel's *Diagnostics* report.

- New: **three kinds of button**. Besides a captured RF code, a button can be a **Somfy RTS**
  button or a **Home Assistant action** (a service call on any entity, with optional data).
- New: **Somfy RTS** (generated). Each device gets its own 24-bit address and rolling code, kept
  in the store apart from the devices and saved before every press. *Pair (PROG)*, "motor turns
  the other way" and repeats per press in the panel. Sent at 433.42 MHz through a
  `radio_frequency` transmitter; the panel warns when a transmitter can only do 433.92 MHz. The
  counters travel with exports and never go back on import.
- New: **devices driven by other integrations** (ESPSomfy RTS, ble_adv, ESPHome…). Link the
  device to that integration's entity, fill the buttons with its actions in one click and copy
  its state (cover position and movement, fan speed, preset and direction, on/off, a fan's
  separate lamp). A linked cover passes "go to a position" straight to it.
- New: **follow the original remote**. With an ESPHome RF receiver, RF Devices listens all the
  time and applies the presses of the original remote without sending: stored fixed codes by
  fingerprint, and real Somfy remotes by address (*Detect a Somfy remote*). Own transmissions
  and captures are ignored. Every recognised press fires `rf_devices_remote`. The subscription
  survives reconnections of the ESPHome device.
- New: **ESP32 + CC1101** reference configs for ESPHome 2026.9+ (`docs/esphome`): two radios
  (433.42 + 433.92 MHz, each sending and listening) or one radio that retunes to send Somfy.
- With several radios on one ESPHome device, learning uses the receiver whose frequency matches
  the transmitter.
- Fix: **learning with an ESPHome receiver never started** in 0.12.0-iotorero.1 ("This ESPHome
  device has no RF receiver"). Home Assistant keeps no record of RF receivers, only of
  transmitters; RF Devices now asks the device itself for its receivers.
- Fix: a **Broadlink's `radio_frequency` entity** could not learn ("Only ESPHome devices can
  learn…"). It now learns the same way as the Broadlink's `remote` entity.
- The *Diagnostics* report shows the RF receivers each ESPHome device lists.
- Fix: saving a cover failed ("not a valid option at take_relay_entity_id").
- Transmitters can send raw timings at a given frequency (`async_send_timings`); a Broadlink
  gets them as a packet.

- Includes everything in 0.11.9 of the main branch: the fix for saving blinds and "buttons only"
  devices, timing a blind's travel from the panel, and its relay, wall buttons and power meter.

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
- New: **Diagnostics** button in the panel. It downloads a report for remote debugging:
  versions, transmitters and why each can or cannot learn, ESPHome devices with RF/IR, the
  entities in use, the latest transmissions and captures (with every burst received) and recent
  log lines. Home Assistant's own *Download diagnostics* now gives the same report.
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

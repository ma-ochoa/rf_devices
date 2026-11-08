<p align="center">
  <img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/custom_components/rf_devices/brand/icon@2x.png" alt="RF Devices" width="160">
</p>

<h1 align="center">RF Devices</h1>

<p align="center">
  Turn the buttons of any RF remote into real Home Assistant devices: lights, fans, blinds,
  switches and buttons, learned and managed from a visual panel.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.5%2B-blue.svg" alt="Home Assistant 2026.5+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT">
</p>

<p align="center"><a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ma-ochoa&repository=rf_devices&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open in HACS"></a></p>

<p align="center"><b>English</b> · <a href="docs/README.es.md">Español</a></p>

---

## What it gives you

You have a ceiling fan, a lamp or a blind with a **433/315 MHz RF remote**, and a **Broadlink**
that can send RF, or an **ESPHome RF proxy** such as the Athom/IoTorero RF-IR remote or an
**ESP32 with a CC1101** radio. RF Devices lets you:

- **Capture every button from a panel** in the sidebar: no YAML, no `remote.learn_command`, no
  searching for codes in `.storage`.
- **Get clean, reliable codes.** Each capture is analysed and trimmed to a few identical frames
  sent once. Toggle-only lamps no longer switch on and straight back off, which is the usual
  "it flickers" problem with learned RF codes.
- **Create real entities** with the right behaviour: a `fan` with speeds, direction, presets and
  timers; a `light` with colour-temperature modes and dimming; a `cover` with an estimated
  position; `switch` and `button` entities. They work with dashboards, automations and voice
  assistants (Alexa, Google, Assist).
- **Know the real state** even when someone uses the original remote: from a power meter, an
  on/off entity, or a **power calibration** that tells the fan speed and whether the lamp is on
  from a single meter.
- **Use the wall switch and the smart relay** that feed the device (Shelly, and any relay Home
  Assistant can switch), including **wall-switch gestures**: one flip toggles the light, two
  change the fan speed, three switch the fan off, and so on.
- **Keep working when Home Assistant is down**: on Shelly, an optional fallback script takes
  over the wall switch if Home Assistant does not confirm a press.
- **Drive Somfy RTS blinds** (test build): RF Devices acts as one more Somfy remote, with its own
  rolling code, paired with the motor like any new remote.
- **Group devices other integrations drive** (test build): a blind from ESPSomfy RTS, a fan
  from ble_adv, an ESPHome button… Each button can call a Home Assistant action, and the state
  is copied from that integration's entity.
- **Follow the original remote** (test build): with an RF receiver (ESP32 + CC1101), RF Devices
  hears the usual remote and updates the state without sending anything.

<p align="center"><img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/docs/images/en/list.png" alt="Device list" width="820"></p>

## Tested hardware

| Role | Tested with | Should also work with |
|---|---|---|
| RF transmitter / learner | **Broadlink RM Pro+** (433 MHz) | Other RF-capable Broadlink models supported by the core integration (RM Pro, RM4 Pro…) |
| RF transmitter / learner (test build) | Not yet tested on real hardware | **Athom / IoTorero RF433-IR remote** (ESP32, ESPHome, firmware 3.0.8+); **ESP32 + one or two CC1101** with ESPHome 2026.9+ (reference configs in [`docs/esphome`](docs/esphome)); any ESPHome `ir_rf_proxy` with an RF transmitter and receiver; any `radio_frequency` entity (send only) |
| Somfy RTS (test build) | Not yet tested on real hardware | A 433.42 MHz transmitter (CC1101). The frames follow Somfy_Remote_Lib, which works with real motors |
| Other integrations (test build) | Not yet tested on real hardware | Any entity: ESPSomfy RTS covers, ble_adv fans and lights, ESPHome buttons, scripts, scenes… |
| Relay, meter and wall switch | **Shelly Plus 2PM** (Gen2, local RPC) | Other Shelly Gen2+ relays; any relay/switch entity through the generic adapter |

It has only been tested with the devices in the first column. The code is built to grow:
- **Transmitters** go through adapters (`transmitters/`): a `remote` entity (Broadlink) or a
  `radio_frequency` entity (any RF adapter Home Assistant supports, such as ESPHome).
- **Relays** go through adapters (`relays/`). Sonoff, Tuya or other relays and wall-switch modules
  similar to Shelly can get vendor-specific features (live power, detaching the switch, scripts)
  by adding one module.

## Requirements

- Home Assistant **2026.5** or newer (tested on 2026.9).
- A transmitter, one of:
  - the core **Broadlink** integration with an RF-capable model. RF Devices sends through its
    `remote` entity and uses its connection to learn;
  - an **ESPHome** device with the `ir_rf_proxy` RF platform, which gives Home Assistant a
    `radio_frequency` entity. RF Devices sends raw timings through it and, when the device also
    has an `ir_rf_proxy` RF receiver, learns from it (see [ESPHome RF proxies](#esphome-rf-proxies-iotorero-esp32--cc1101)).
  - none, if every button of the device calls another integration (see
    [Devices driven by other integrations](#devices-driven-by-other-integrations)).
- Optional: a smart relay (e.g. Shelly) feeding the device, with a power meter and a wall switch.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ma-ochoa&repository=rf_devices&category=integration)

Or by hand:

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/ma-ochoa/rf_devices`, type
   **Integration**.
2. Search for **RF Devices**, install it and **restart** Home Assistant.
3. **Settings → Devices & services → Add integration → RF Devices**, then choose your Broadlink
   remote. Later, **Configure** lets you change it, set the gap between transmissions and pick
   the smart plug that powers the Broadlink (used to power-cycle it if it hangs).

### Manual

Copy `custom_components/rf_devices` into `config/custom_components/` and restart Home Assistant.
Then add the integration as in step 3.

After installing, **RF Devices** appears in the sidebar (administrators only).

## Quick start

1. Open **RF Devices** → **New device**, give it a name and choose the type.
2. On the **Remote buttons** tab, press **Capture** on each button:
   - the first time, *hold* the remote's button until the frequency is found, then press it once;
   - once the frequency is known, one press is enough.
3. Press **Test** to send it. If it works, it is saved automatically.
4. The entities appear in Home Assistant under a device with that name. The **Live test**
   column lets you try them right away, and links to their device pages. Use **Add to
   dashboard** there.

<p align="center"><img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/docs/images/en/live.png" alt="Live test" width="820"></p>

<p align="center"><img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/docs/images/en/buttons.png" alt="Capturing buttons" width="820"></p>

## Device types

| Type | Entities | Remote buttons |
|---|---|---|
| **Light** | `light` (on/off, colour-temperature modes, brightness) | A single toggle button, or separate on/off; optional colour and brighter/dimmer buttons |
| **Switch** | `switch` | Toggle or on/off |
| **Cover** | `cover` with estimated position | Open, close, stop; travel times (timed from the panel) for positioning; optional relay, wall buttons and power meter |
| **Fan** | `fan` + optional `light` | Power (toggle) or off button, 1–10 speeds, direction (one reversing button, or summer/winter), presets such as *Breeze*, timers, optional lamp with its own buttons |
| **Buttons** | `button` per remote button | Any |

Any device can also have **extra buttons** (`x_…`), which become `button` entities.

### Fans with a light

A fan whose lamp has **a name of its own** becomes **two independent devices** in Home
Assistant, the fan and the light, each with its own name and entities. Voice assistants and
dashboards treat them separately. The RF Devices panel keeps them together as one remote and
groups the buttons and entities into *Fan* and *Light*.

- **Speeds and percentages**: each speed has a percentage (editable table). "Set the fan to 2"
  arriving as 2 % is taken as speed 2.
- **Turn on** sends the code of a chosen speed (1 by default) rather than the power button. That
  is predictable whatever the remote remembers.
- **Colour temperature**: name the modes in the order the button cycles through them. RF Devices
  remembers the current one, with options for what the lamp does when power returns (keeps its
  mode, always starts in one, or advances).
- **Brightness**: brighter/dimmer buttons held for the time needed.

<p align="center"><img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/docs/images/en/general.png" alt="Fan configuration" width="820"></p>

## Knowing the real state

RF is one-way, so Home Assistant only assumes the state. RF Devices offers several ways to keep
it right:

- **Feedback entity**: a power sensor (W, with a threshold) or any on/off entity. The state
  follows it.
- **Power calibration (fans with a light on one meter)**: a wizard measures idle, the lamp in
  each colour mode, and every speed going **up** and **down** (PWM motors draw differently).
  Afterwards the aligner reads the meter and corrects fan speed, lamp and colour without
  transmitting, even after the original remote was used. Values can be edited by hand.
  - **Live calibration** (live meters, on by default): after each speed command sent by
    RF Devices, with the light off, the draw is watched for up to 15 min; once it is really flat
    (a PWM motor can keep creeping for minutes), that speed's value is corrected. Readings that
    look like another speed (the remote was used meanwhile) are ignored.
  - **Estimated speed** sensor: the motor's position between the calibrated speeds, in %, with a
    `trend` attribute (accelerating / decelerating / stable) while it ramps.
- **Live calibration**: after its own speed commands the settled draw corrects that speed, and
  every lamp switch seen with the fan stopped corrects the lamp's value (lamps drift with
  temperature), so the table stays right without calibrating again.
- **Quick light calibration** (1–2 minutes, fan stopped): measures only the lamp. Enough to tell
  the light from the fan by its sudden jumps in draw, without waiting for every speed.
- **Sync buttons** and the services `rf_devices.set_state`, `rf_devices.set_position_state` and
  `rf_devices.set_color_mode` correct the state without sending anything.

With a Shelly meter (Gen1 or Gen2+) the power is read **live** through its local API. Home Assistant only
gets ~1 W steps from it, which is too coarse for fan speeds.

<p align="center"><img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/docs/images/en/power.png" alt="Power calibration" width="820"></p>

## Relay and wall switch

A fan or lamp is often fed by a smart relay that a wall switch drives. Link them on the **Relay
and wall switch** tab; a diagram shows the wiring for the chosen mode.

| Mode | Wall switch | What RF Devices does |
|---|---|---|
| **None** | — | RF only |
| **A · Coupled** | Drives the relay directly | Follows the relay (relay on = lamp on). Asking for the lamp with the relay off switches the relay on. |
| **B · Detached** | Only reports to Home Assistant | Toggles the lamp **by RF**. The relay stays on, so the fan always has power. Supports gestures and the fallback script. |
| **Wall switch only** | A detached input with nothing wired to its output | Reads the switch; the device is always powered. Supports gestures. |

Options:

- **Apply to relay** (Shelly): detaches or re-attaches the wall switch on the device, enables its
  input entity and installs or removes the fallback script. Going back to mode A undoes it all.
- **Turn the lamp on at power-up**: if the lamp remembers "off", RF Devices sees it in the
  meter and sends "on".
- **Power the relay to start the fan**: opt-in, because the lamp lights for a moment. Keep it off
  in bedrooms. Timings for the power-up sequence are configurable.
- **Relay off after N minutes with everything off** (always, at night, or within hours):
  relays kept energised for years can weld their contacts.
- **Use the relay's name / entity_id**: the RF light takes over the name and `entity_id`
  your voice assistant already knows, and the relay is renamed "Switch …". Reversible.
- **Hide the relay's own entities** so only the RF light and fan are shown.

<p align="center"><img src="https://raw.githubusercontent.com/ma-ochoa/rf_devices/main/docs/images/en/relay.png" alt="Relay and wall switch" width="820"></p>

### Wall-switch gestures (modes B and wall switch only)

A rocker switch only reports that it changed, so RF Devices counts quick changes. Each count has
an action you choose:

| Flips | Example action |
|---|---|
| 1 | Toggle the light |
| 2 (a quick back-and-forth) | Fan on, or next speed; from the top speed it goes back down |
| 3 | Fan off |
| 4 or more | Fan off, or anything else |

Available actions: toggle/on/off light, next colour, fan step (bouncing), fan faster/slower,
fan on/off/toggle, reverse direction, everything off, cut the relay, or nothing.

- The **window** between flips is configurable (0.6 s by default). With only a 1-flip action
  configured, the light responds instantly. Otherwise it waits for the window to close.
- Every gesture is also fired as the event `rf_devices_wall_gesture` with `device_id`, `name`,
  `flips` and `action`, for your own automations.

### Fallback script (Shelly, mode B)

When the wall switch is detached, it depends on Home Assistant. The optional script keeps it
working when Home Assistant is down:

- Home Assistant confirms **every** change to the Shelly as soon as it receives it (~0.1–0.3 s).
- If no confirmation arrives within the wait (1–2 s, configurable), the script toggles the relay
  itself, as a normal switch would.
- It sends nothing while idle and never writes to flash. It uses about 0.5 KB of the Shelly's
  memory.

## Broadlink safeguards

Learning puts the Broadlink in a special mode, and some units hang if they are polled too fast.
RF Devices:
- checks the Broadlink answers before learning;
- polls it once per second;
- always leaves learning mode;
- sends nothing during a capture;
- checks the Broadlink afterwards.

If it stops answering, a notification tells you. With a smart plug configured, RF Devices can
power-cycle it for you. All transmissions go through a queue with a configurable gap, per
device if needed.

## ESPHome RF proxies (IoTorero, ESP32 + CC1101)

Test build: it has not been tried on real hardware yet. Feedback in the issues is welcome.

The ESP only moves raw pulses. Codes, Somfy rolling codes, learning and state live in Home
Assistant, so adding a device never needs a new firmware.

1. Add the device with the ESPHome integration.
   - **Athom / IoTorero RF433-IR remote**: update it to firmware **3.0.8 or newer** from its
     *Firmware Update* entity; it already declares the `ir_rf_proxy` RF transmitter and receiver.
   - **ESP32 + CC1101**: start from a reference config (validated with `esphome config`
     2026.9.1, not yet flashed):
     - [`docs/esphome/esp32-2x-cc1101.yaml`](docs/esphome/esp32-2x-cc1101.yaml): **two radios**,
       one at 433.42 MHz (Somfy RTS) and one at 433.92 MHz, each sending and listening.
       Recommended: it can follow Somfy remotes and fixed-code remotes at the same time.
     - [`docs/esphome/esp32-cc1101.yaml`](docs/esphome/esp32-cc1101.yaml): **one radio** that
       listens at 433.92 MHz and retunes to 433.42 MHz only to send Somfy frames.
     Both use the native `cc1101` component with separate pins to send (GDO0) and receive (GDO2).
     Use 2.54 mm pin modules, power them from 3.3 V, and change the pins to your board's.
   - Your own config: each `ir_rf_proxy` entity has **either** a transmitter **or** a receiver,
     and must declare its `frequency` (Home Assistant refuses frequencies a transmitter does not
     declare):
     ```yaml
     radio_frequency:
       - platform: ir_rf_proxy
         name: 433MHz RF Transmitter
         frequency: 433.92MHz
         remote_transmitter_id: rf_transmitter
       - platform: ir_rf_proxy
         name: 433MHz RF Receiver
         frequency: 433.92MHz
         remote_receiver_id: rf_receiver
     ```
2. Choose a `radio_frequency.…` transmitter (in the RF Devices options, or per device). With
   two radios, pick the 433.42 MHz one for Somfy devices and the 433.92 MHz one for the rest.
   Learning uses the receiver of the same device whose frequency matches the transmitter.
3. Capture: there is no frequency sweep. Press the button once, holding it for about a second.
   The receiver's bursts are joined, noise is dropped and the result is cleaned like a
   Broadlink capture.

**Simple receivers (Athom / IoTorero).** A plain 433 MHz receiver delivers noise all the time,
and the Athom firmware (checked with v3.0.8) reports its receiver with the polarity swapped:
carrier as silence and silence as carrier, most likely because its ESPHome config declares the
RF receiver pin as `inverted`. RF Devices copes with both: a capture ends only when the same
frame has been received at least twice, and each capture is read both ways round, keeping the
reading where the frame repeats. Nothing has to be configured, and a receiver with the right
polarity (or a corrected firmware) works the same. A remote that sends its frame only once per
press cannot be captured this way.

Codes are still stored in the Broadlink format, so they can be moved between a Broadlink and an
ESPHome transmitter. Fixed-code OOK remotes are captured; rolling-code remotes cannot be
replayed (Somfy RTS is generated instead, see below). With debug logs on, every received burst
is logged: attach them to an issue if a capture fails.

## Somfy RTS

Test build. Somfy RTS remotes change their code on every press, so a capture cannot be replayed:
the motor ignores a code it has already seen. RF Devices acts as **one more remote** instead:

1. Create the device (usually a *Cover*) and, in *General → How it is controlled*, choose
   **Generated Somfy RTS**. It gets its own random 24-bit address; the buttons are assigned
   (open = Up, close = Down, stop = My) and can be changed on the *Buttons* tab.
2. Choose a transmitter that works at **433.42 MHz** (a CC1101). A 433.92 MHz transmitter
   (Broadlink, Athom) is used at its own frequency and may only reach the motor from close by:
   the panel warns about it.
3. **Pair**: on a remote the motor already knows, hold PROG until the blind jogs; within two
   minutes press **Pair (PROG)** in the panel; the blind jogs again. Doing it again unpairs it.
   Motors accept about 12 remotes: keep the original one.
4. If the motor turns the other way, tick **The motor turns the other way**.

The rolling code is kept in `.storage/rf_devices`, apart from the devices, and is saved before
each press (a failed press skips a code, which motors accept). It travels with exports, and an
import never moves it back. **Do not use the same address from two places** (two Home Assistant
installations, or an old firmware): their counters would clash.

## Devices driven by other integrations

Test build. When another integration already drives the device (ESPSomfy RTS, ble_adv, an
ESPHome button, a script…), RF Devices can still group it with its light, relay, wall switch
and gestures:

- In *General → How it is controlled*, choose **Another integration** and pick its entity.
  **Fill the buttons with its actions** creates a *Home Assistant action* for each button
  (for example `cover.open_cover`, or `fan.set_percentage` with the percentage of each speed).
  A fan's lamp may be a separate entity (ble_adv): pick it as the *light entity*.
- **Copy its state** (recommended): the RF Devices entity follows the other integration's
  entity (ESPSomfy RTS listens to the remotes; ble_adv remembers what it sends). A linked cover
  also passes "go to 40 %" straight to it.
- Any single button can also be an action, whatever the device: *More… → Home Assistant
  action…* on the *Buttons* tab (service, target entity and optional JSON data).

## Following the original remote

Test build. With an RF receiver on the transmitter's ESPHome device, tick **Follow the original
remote** on a device. RF Devices then listens all the time and, without sending anything:

- recognises the device's stored codes (fixed-code remotes) and applies that button;
- for Somfy devices, recognises the **real** Somfy remotes added with *Detect a Somfy remote*
  (press any button of the real remote; its address is read from the frame).

What RF Devices sends itself is ignored, and so is everything heard while sending or learning.
Every recognised press fires the `rf_devices_remote` event, so remotes with no entity of their
own (an alarm fob, an extra button) can drive automations.

## Import, export and existing codes

- **Export / import** all devices (or some) as a JSON file, to move them to another
  installation. Data lives in `.storage/rf_devices` and is included in Home Assistant backups.
- **Reuse codes** already learned with the core Broadlink integration: *More… → From Broadlink*
  on any button. You can also paste a code, or copy one from another RF Devices device.

## Services and events

| Service | What it does |
|---|---|
| `rf_devices.set_state` | Set on/off (and fan percentage) without transmitting |
| `rf_devices.set_position_state` | Set a cover's position without transmitting |
| `rf_devices.set_color_mode` | Set the remembered colour mode without transmitting |

| Event | Data |
|---|---|
| `rf_devices_wall_gesture` | `device_id`, `name`, `flips`, `action` |
| `rf_devices_remote` | `device_id`, `name`, `role`, `source` (`code` or `somfy:<address>`), `applied` |

## Troubleshooting

- **Diagnostics**: the panel's *Diagnostics* button (or *Settings → Devices & services → RF
  Devices → ⋮ → Download diagnostics*) downloads a report with versions, transmitters, ESPHome
  RF/IR devices, the entities in use, the latest transmissions and captures (with the bursts
  received) and recent log lines. Stored codes are summarised, not included. Attach it to an
  issue.
- **Debug logs**:
  ```yaml
  logger:
    logs:
      custom_components.rf_devices: debug
  ```
- **A code works once and then not / the lamp flickers**: open the button, check the frame map
  and use *Clean*. Choose fewer or more frames if the receiver needs them.
- **The fan state drifts**: run the power calibration again. Lamps change their draw as they
  warm up.
- **The fallback script toggled the relay while Home Assistant was up**: raise its wait. The
  Shelly's `Switch.GetStatus` shows `"source": "loopback"` when the script acted.

## Limitations

- RF 315/433 MHz only for now (no IR). Rolling codes: only Somfy RTS (generated).
- State is assumed unless a meter or feedback entity is linked.
- Password-protected Shelly devices are handled through their Home Assistant entities only (no
  live power, detach or script).
- Tested only with the hardware listed above.

## Extending: other transmitters

Transmitters live in `custom_components/rf_devices/transmitters/`. Subclass `Transmitter`
(`base.py`), implement `async_send` and, if it can learn, `learn_problem` and `async_learn`, and
map its entity domain in `TRANSMITTERS` (`__init__.py`). Optional: `async_send_timings` (raw
microseconds at a given frequency, used by generated protocols such as Somfy RTS),
`carrier_note` and `receiver_problem`.

Generated protocols live in `protocols/` (`somfy.py`: build and decode frames, no Home Assistant
dependency). A command is one of three kinds (`rf`, `somfy`, `action`), see `models.py`.

## Extending: other relays

Relay support lives in `custom_components/rf_devices/relays/`. Any relay Home Assistant can
switch works through `generic.py`. To add vendor features:

1. Create a module with a subclass of `RelayAdapter` (`relays/base.py`).
2. Declare what it can do in `capabilities` and implement those methods (live power, detach,
   fallback script, acknowledgement).
3. Add it to `ADAPTERS` in `relays/__init__.py`.

`relays/shelly.py` is a complete example. Pull requests are welcome.

## Development

```bash
uv venv -p 3.14 .venv
uv pip install -p .venv/bin/python pytest-homeassistant-custom-component broadlink==0.19.0 rf-protocols aioesphomeapi ruff
.venv/bin/ruff check custom_components tests --select E,F,W,I,B,UP --ignore E501
.venv/bin/pytest
```

The panel is a plain web component (`frontend/rf-devices-panel.js`) with no build step. Tests use
synthetic RF frames.

## License

[MIT](LICENSE)

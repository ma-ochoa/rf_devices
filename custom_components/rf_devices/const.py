"""Constants for RF Devices."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "rf_devices"
VERSION = "0.11.4"
MANUFACTURER = "RF Devices"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
EXPORT_FORMAT = "rf_devices_export"

CONF_TRANSMITTER = "transmitter"
CONF_MIN_INTERVAL = "min_interval"
DEFAULT_MIN_INTERVAL = 0.4  # seconds between two transmissions

PANEL_URL = "rf-devices"
STATIC_URL = "/rf_devices_static"

LEARN_TIMEOUT = 30  # seconds per learning stage
LEARN_COOLDOWN = 3  # seconds between two captures
POLL_INTERVAL = 1.0  # seconds between "got a code?" questions while learning
MAX_POLL_MISSES = 2  # unanswered polls tolerated while it is busy receiving
HEALTH_TIMEOUT = 6  # seconds to wait for the Broadlink to answer
HEALTH_DELAY = 2  # seconds after a capture before checking the Broadlink
POWER_OFF_TIME = 10  # seconds the Broadlink plug stays off when power-cycling
POWER_BOOT_TIME = 60  # seconds allowed for it to come back

CONF_POWER_SWITCH = "power_switch"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.FAN,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Device types and the command roles each one uses.
TYPE_LIGHT = "light"
TYPE_SWITCH = "switch"
TYPE_COVER = "cover"
TYPE_FAN = "fan"
TYPE_BUTTONS = "buttons"
DEVICE_TYPES = [TYPE_LIGHT, TYPE_SWITCH, TYPE_COVER, TYPE_FAN, TYPE_BUTTONS]

MODE_TOGGLE = "toggle"
MODE_ONOFF = "onoff"
MODE_NONE = "none"
MODE_OFF_BUTTON = "off"
MODE_BUTTONS = "buttons"

ROLE_TOGGLE = "toggle"
ROLE_ON = "on"
ROLE_OFF = "off"
ROLE_OPEN = "open"
ROLE_CLOSE = "close"
ROLE_STOP = "stop"
ROLE_POWER = "power"
ROLE_DIRECTION = "direction"
ROLE_FORWARD = "forward"
ROLE_REVERSE = "reverse"
ROLE_LIGHT_TOGGLE = "light_toggle"
ROLE_LIGHT_ON = "light_on"
ROLE_LIGHT_OFF = "light_off"
SPEED_PREFIX = "speed_"
EXTRA_PREFIX = "x_"
PRESET_PREFIX = "preset_"
SYNC_PREFIX = "sync_"
TIMER_PREFIX = "timer_"
ROLE_LIGHT_COLOR = "light_color"
ROLE_LIGHT_UP = "light_up"
ROLE_LIGHT_DOWN = "light_down"
# Optional light buttons, offered as tick boxes rather than free extras.
LIGHT_EXTRA_ROLES = (ROLE_LIGHT_COLOR, ROLE_LIGHT_UP, ROLE_LIGHT_DOWN)
# Brightness buttons act while held; this is used until the user sets a time.
DEFAULT_DIM_HOLD = 0.5
MAX_TIMERS = 6

MAX_SPEEDS = 10
MAX_PRESETS = 6

# Store keys
ATTR_CODE = "code"
ATTR_FREQUENCY = "frequency"
ATTR_LABEL = "label"
ATTR_LEARNED = "learned"
ATTR_HOLD = "hold"

# Actions a wall switch gesture (1–4 quick flips) can run; see wall.py.
WALL_ACTIONS = (
    "none",
    "light_toggle",
    "light_on",
    "light_off",
    "fan_step",  # on, or next speed; from the top speed it goes back down
    "fan_up",  # on, or next speed; stays at the top
    "fan_down",
    "fan_toggle",
    "fan_on",
    "fan_off",
    "fan_direction",
    "light_color",
    "all_off",
    "power_off",  # cut the relay (mode B only)
)

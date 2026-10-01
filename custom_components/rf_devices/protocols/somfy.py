"""Somfy RTS: build the frames of a virtual remote, and read a real remote's.

Somfy RTS remotes use a rolling code, so a captured press cannot be replayed:
the motor ignores a code it has already seen. RF Devices behaves as one more
remote instead. Each device gets its own 24-bit address and counter, and is
paired with the motor like any new remote (PROG on a remote the motor
already knows, then "Pair" in RF Devices).

Frame (7 bytes, before obfuscation)::

    0      key: 0xA7 (the high nibble must be 0xA; the rest does not matter)
    1      button << 4 | checksum (XOR of all the nibbles)
    2-3    rolling code, big endian
    4-6    address (bytes as Somfy_Remote_Lib sends them)

Each byte is then XORed with the previous obfuscated one. On air: 433.42 MHz
OOK, Manchester with 640 µs half-symbols (a "1" rises in the middle).
Timings follow Legion2/Somfy_Remote_Lib, which is known to work with real
motors: a wake-up pulse before the first frame, two hardware syncs in the
first frame and seven in the repeats, a software sync, 56 bits, ~30 ms gap.

This module has no Home Assistant dependency so it can be unit tested alone.
"""

from __future__ import annotations

from dataclasses import dataclass

FREQUENCY_HZ = 433_420_000
SYMBOL = 640  # µs, half of a bit
KEY = 0xA7

WAKEUP_HIGH = 9415
WAKEUP_LOW = 9565 + 80_000  # silence, then a pause before the first frame
HW_SYNC = 4 * SYMBOL
SW_SYNC_HIGH = 4550
FRAME_GAP = 415 + 30_000

# Frames sent for one press (the first plus repeats), as Somfy_Remote_Lib does.
DEFAULT_REPEATS = 4
MAX_REPEATS = 100

BUTTONS: dict[str, int] = {
    "my": 0x1,
    "up": 0x2,
    "my_up": 0x3,
    "down": 0x4,
    "my_down": 0x5,
    "up_down": 0x6,
    "prog": 0x8,
    "sun_flag": 0x9,
    "flag": 0xA,
}
BUTTON_NAMES = {code: name for name, code in BUTTONS.items()}

MAX_ADDRESS = 0xFFFFFF
MAX_CODE = 0xFFFF


class SomfyError(ValueError):
    """Bad address, button or frame."""


def build_frame(address: int, button: str, rolling_code: int) -> bytes:
    """The 7 obfuscated bytes of one press."""
    if button not in BUTTONS:
        raise SomfyError(f"Unknown Somfy button: {button}")
    if not 0 < address <= MAX_ADDRESS:
        raise SomfyError(f"Somfy address out of range: {address}")
    code = rolling_code & MAX_CODE
    frame = bytearray(
        (
            KEY,
            BUTTONS[button] << 4,
            code >> 8,
            code & 0xFF,
            (address >> 16) & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF,
        )
    )
    checksum = 0
    for byte in frame:
        checksum ^= byte ^ (byte >> 4)
    frame[1] |= checksum & 0x0F
    for i in range(1, 7):
        frame[i] ^= frame[i - 1]
    return bytes(frame)


def _data_timings(frame: bytes) -> list[int]:
    """Manchester, most significant bit first: 1 = low then high, 0 = high then low."""
    halves: list[int] = []
    for i in range(56):
        bit = (frame[i // 8] >> (7 - i % 8)) & 1
        halves += [-SYMBOL, SYMBOL] if bit else [SYMBOL, -SYMBOL]
    return halves


def _merge(values: list[int]) -> list[int]:
    """Join consecutive values of the same sign (+on / −off)."""
    out: list[int] = []
    for value in values:
        if out and (out[-1] > 0) == (value > 0):
            out[-1] += value
        else:
            out.append(value)
    return out


def encode(address: int, button: str, rolling_code: int, repeats: int = DEFAULT_REPEATS) -> list[int]:
    """Signed microseconds (+on / −off) of one press: first frame plus ``repeats``."""
    repeats = max(0, min(MAX_REPEATS, int(repeats)))
    frame = build_frame(address, button, rolling_code)
    data = _data_timings(frame)
    out = [WAKEUP_HIGH, -WAKEUP_LOW]
    for n in range(repeats + 1):
        syncs = 2 if n == 0 else 7
        out += [HW_SYNC, -HW_SYNC] * syncs
        out += [SW_SYNC_HIGH, -SYMBOL]
        out += data
        out.append(-FRAME_GAP)
    return _merge(out)


def frame_ms(repeats: int = DEFAULT_REPEATS) -> float:
    """How long a press lasts on air, in milliseconds."""
    return sum(abs(v) for v in encode(1, "my", 0, repeats)) / 1000


def repeats_for(seconds: float) -> int:
    """Repeats that keep a button "held" for ``seconds`` (0 = a normal press)."""
    if seconds <= 0:
        return DEFAULT_REPEATS
    one = frame_ms(1) - frame_ms(0)  # a repeated frame, in ms
    return max(DEFAULT_REPEATS, min(MAX_REPEATS, round(seconds * 1000 / one)))


# ---------------------------------------------------------------- receiving


@dataclass(frozen=True)
class Press:
    """A decoded Somfy frame."""

    address: int
    button: str
    rolling_code: int


def deobfuscate(frame: bytes) -> bytes:
    out = bytearray(frame)
    for i in range(6, 0, -1):
        out[i] ^= frame[i - 1]
    return bytes(out)


def parse_frame(frame: bytes) -> Press | None:
    """Read 7 obfuscated bytes; None if the checksum or key is wrong."""
    if len(frame) != 7:
        return None
    clear = deobfuscate(frame)
    if clear[0] >> 4 != 0xA:
        return None
    checksum = 0
    for i, byte in enumerate(clear):
        if i == 1:
            byte &= 0xF0
        checksum ^= byte ^ (byte >> 4)
    if checksum & 0x0F != clear[1] & 0x0F:
        return None
    button = BUTTON_NAMES.get(clear[1] >> 4)
    if button is None:
        return None
    return Press(
        address=clear[4] << 16 | clear[5] << 8 | clear[6],
        button=button,
        rolling_code=clear[2] << 8 | clear[3],
    )


# A received duration counts as this many half-symbols if within these bounds.
_HALF = (SYMBOL * 0.5, SYMBOL * 1.55)
_FULL = (SYMBOL * 1.55, SYMBOL * 2.6)
_SW_SYNC = (3800, 5400)


def _halves(value: int) -> int:
    length = abs(value)
    if _HALF[0] <= length < _HALF[1]:
        return 1
    if _FULL[0] <= length < _FULL[1]:
        return 2
    return 0


def _decode_after_sync(timings: list[int], start: int) -> bytes | None:
    """Read 56 Manchester bits that follow a software sync at ``start``."""
    levels: list[int] = []
    for value in timings[start + 1 :]:
        n = _halves(value)
        if n == 0:
            # The frame gap (or noise): the last low half-symbol may sit in it.
            if value < 0 and len(levels) == 112:
                levels.append(0)
            break
        levels += [1 if value > 0 else 0] * n
        if len(levels) >= 113:
            break
    if len(levels) == 112:
        # The burst ended on the last high half (receivers drop the final
        # silence): a "0" bit's low half is that silence.
        levels.append(0)
    # The software sync is followed by one low half-symbol before the data.
    if len(levels) < 113 or levels[0] != 0:
        return None
    halves = levels[1:113]
    bits = 0
    for i in range(0, 112, 2):
        first, second = halves[i], halves[i + 1]
        if first == second:
            return None  # not Manchester
        bits = bits << 1 | (1 if (first, second) == (0, 1) else 0)
    return bits.to_bytes(7, "big")


def decode(timings: list[int]) -> list[Press]:
    """Every valid Somfy frame in a received burst (repeats included)."""
    presses: list[Press] = []
    merged = _merge([v for v in timings if v])
    for i, value in enumerate(merged):
        if value > 0 and _SW_SYNC[0] <= value <= _SW_SYNC[1]:
            frame = _decode_after_sync(merged, i)
            if frame is not None and (press := parse_frame(frame)) is not None:
                presses.append(press)
    return presses

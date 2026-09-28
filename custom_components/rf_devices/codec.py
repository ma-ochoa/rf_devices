"""Decode, analyse and clean Broadlink IR/RF packets.

Packet layout (as returned by ``check_data`` and accepted by ``send_data``):

    byte 0      type: 0x26 IR, 0xb2 RF 433 MHz, 0xd7 RF 315 MHz
    byte 1      repeat count (the packet is sent ``repeat + 1`` times)
    bytes 2-3   payload length, little endian
    payload     pulse lengths in ticks, alternating on/off, starting with "on".
                One byte per pulse, or 0x00 followed by a big-endian uint16.

When learning RF the Broadlink records for as long as the button is held, so
a capture usually holds a truncated frame followed by a dozen repetitions.
Remotes that only toggle may read a gap inside that burst as a second press,
so ``clean`` keeps a few complete, identical frames and sends them once.

This module has no Home Assistant dependency so it can be unit tested alone.
"""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass, field

TICK_US = 269 / 8192 * 1000  # ~32.84 µs per tick

TYPE_IR = 0x26
TYPE_RF433 = 0xB2
TYPE_RF315 = 0xD7
KINDS = {TYPE_IR: "ir", TYPE_RF433: "rf433", TYPE_RF315: "rf315"}

# A low pulse this long (or longer) separates two frames.
MIN_GAP_US = 2500
# Final silence appended after the last kept frame.
TAIL_GAP_TICKS = 1500

DEFAULT_FRAMES = 4


class CodecError(ValueError):
    """The code is not a valid Broadlink packet."""


@dataclass
class Packet:
    """A decoded Broadlink packet."""

    type: int
    repeat: int
    pulses: list[int]

    @property
    def kind(self) -> str:
        return KINDS.get(self.type, "unknown")

    @property
    def is_rf(self) -> bool:
        return self.type in (TYPE_RF433, TYPE_RF315)


@dataclass
class Frame:
    """One transmission of the remote's message, plus the gap that follows it."""

    start: int
    pulses: list[int]
    gap: int | None
    signature: str = field(init=False)
    bits: str = field(init=False)

    def __post_init__(self) -> None:
        self.signature, self.bits = _describe(self.pulses)

    @property
    def length(self) -> int:
        return len(self.pulses)

    @property
    def duration_us(self) -> float:
        return (sum(self.pulses) + (self.gap or 0)) * TICK_US


def _to_bytes(code: str | bytes) -> bytes:
    if isinstance(code, bytes):
        return code
    code = code.strip()
    if code.startswith("b64:"):
        code = code[4:]
    try:
        return base64.b64decode(code, validate=True)
    except (ValueError, TypeError) as err:
        raise CodecError("Not valid base64") from err


def decode(code: str | bytes) -> Packet:
    """Decode a base64 string (with or without ``b64:``) or raw bytes."""
    raw = _to_bytes(code)
    if len(raw) < 4:
        raise CodecError("Packet too short")
    length = raw[2] | raw[3] << 8
    end = 4 + length
    if end > len(raw):
        raise CodecError("Declared length exceeds packet size")
    pulses: list[int] = []
    i = 4
    while i < end:
        value = raw[i]
        i += 1
        if value == 0:
            if i + 1 >= len(raw):
                break
            value = raw[i] << 8 | raw[i + 1]
            i += 2
            if value == 0:
                # Zero padding reached.
                break
        pulses.append(value)
    if not pulses:
        raise CodecError("Packet holds no pulses")
    return Packet(raw[0], raw[1], pulses)


def encode(packet: Packet) -> bytes:
    """Encode a packet, padded with zeros to a multiple of 16 bytes."""
    payload = bytearray()
    for value in packet.pulses:
        value = max(1, min(int(value), 0xFFFF))
        if value < 256:
            payload.append(value)
        else:
            payload += bytes((0, value >> 8, value & 0xFF))
    out = bytearray((packet.type, packet.repeat & 0xFF, len(payload) & 0xFF, len(payload) >> 8))
    out += payload
    out += bytes(-len(out) % 16)
    return bytes(out)


def to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# Pause inserted between two received bursts when the receiver reports them
# separately (it drops the silence that split them). ESPHome's default idle
# threshold is 10 ms, so the real pause was at least that long.
RECEIVED_GAP_US = 10000
# Received bursts shorter than this are receiver noise, not a remote frame.
MIN_RECEIVED_PULSES = 16


def to_timings(code: str | bytes) -> tuple[list[int], int]:
    """Signed microseconds (+on / −off) and repeat count, as HA's RF API wants them."""
    packet = decode(code)
    timings = [
        round(p * TICK_US) * (1 if i % 2 == 0 else -1) for i, p in enumerate(packet.pulses)
    ]
    return timings, packet.repeat


def from_timings(bursts: list[list[int]], kind: int = TYPE_RF433) -> str:
    """Build a Broadlink packet (base64) from received signed-microsecond bursts.

    A receiver may deliver a remote's burst of repeated frames as one list
    or one list per frame; either way the result looks like a Broadlink
    capture, so ``analyze``/``clean`` treat both alike. Leading silences
    are skipped, consecutive values of the same sign are merged, and a
    pause is put between bursts that ended on an "on" pulse.
    """
    pulses_us: list[int] = []
    for burst in bursts:
        on = True  # the next value we expect
        for value in burst:
            if value == 0:
                continue
            is_on = value > 0
            if not pulses_us and not is_on:
                continue  # a packet starts with "on"
            if pulses_us and is_on != on:
                # Same sign twice in a row: merge into the previous pulse.
                pulses_us[-1] += abs(value)
                continue
            pulses_us.append(abs(value))
            on = not is_on
        if pulses_us and len(pulses_us) % 2 == 1:
            pulses_us.append(RECEIVED_GAP_US)  # close the burst with its pause
    if not pulses_us:
        raise CodecError("Nothing was received")
    ticks = [max(1, round(us / TICK_US)) for us in pulses_us]
    return to_b64(encode(Packet(kind, 0, ticks)))


def _describe(pulses: list[int]) -> tuple[str, str]:
    """Quantise pulses into short/long and read on-pulses as bits (long = 1)."""
    if not pulses:
        return "", ""
    threshold = (min(pulses) + max(pulses)) / 2
    signature = "".join("L" if p > threshold else "S" for p in pulses)
    bits = signature[0::2].replace("L", "1").replace("S", "0")
    return signature, bits


def split_frames(pulses: list[int]) -> list[Frame]:
    """Split a pulse train at long off-pulses."""
    gap_ticks = MIN_GAP_US / TICK_US
    frames: list[Frame] = []
    start = 0
    for idx in range(1, len(pulses), 2):  # off-pulses sit at odd indexes
        if pulses[idx] >= gap_ticks:
            frames.append(Frame(start, pulses[start:idx], pulses[idx]))
            start = idx + 1
    if start < len(pulses):
        frames.append(Frame(start, pulses[start:], None))
    return frames


def _dominant(frames: list[Frame]) -> tuple[str | None, list[Frame]]:
    """Return the most repeated signature and the frames that carry it."""
    counts = Counter(f.signature for f in frames if f.length > 1)
    if not counts:
        return None, []
    signature, _ = counts.most_common(1)[0]
    return signature, [f for f in frames if f.signature == signature]


def analyze(code: str | bytes) -> dict:
    """Describe a packet for the UI."""
    packet = decode(code)
    frames = split_frames(packet.pulses)
    signature, good = _dominant(frames)
    total_us = sum(packet.pulses) * TICK_US
    sample = good[0] if good else frames[0]
    result = {
        "kind": packet.kind,
        "repeat": packet.repeat,
        "pulses": len(packet.pulses),
        "duration_ms": round(total_us / 1000, 1),
        "sent_ms": round(total_us * (packet.repeat + 1) / 1000, 1),
        "frames": len(frames),
        "good_frames": len(good),
        "bad_frames": len(frames) - len(good),
        "frame_pulses": sample.length,
        "frame_ms": round(sample.duration_us / 1000, 1),
        "bits": sample.bits,
        "hex": _bits_to_hex(sample.bits),
        "sample_us": [round(p * TICK_US) for p in sample.pulses]
        + ([round(sample.gap * TICK_US)] if sample.gap else []),
        "frame_map": [
            {"pulses": f.length, "ok": f.signature == signature} for f in frames
        ],
    }
    result["needs_cleaning"] = packet.is_rf and (
        result["bad_frames"] > 0
        or packet.repeat > 0
        or len(good) > DEFAULT_FRAMES * 2
    )
    return result


def _bits_to_hex(bits: str) -> str:
    if not bits:
        return ""
    width = (len(bits) + 3) // 4
    return format(int(bits, 2), f"0{width}X")


def fingerprint(code: str | bytes) -> str:
    """Identity of the message, independent of how long the button was held."""
    packet = decode(code)
    signature, good = _dominant(split_frames(packet.pulses))
    return f"{packet.kind}:{signature or ''}"


def clean(code: str | bytes, frames: int = DEFAULT_FRAMES, repeat: int = 0) -> str:
    """Keep ``frames`` complete identical frames, sent ``repeat + 1`` times.

    Returns the new code as base64 without the ``b64:`` prefix. IR packets and
    packets without a repeated frame are returned unchanged apart from the
    repeat byte.
    """
    packet = decode(code)
    if frames < 1:
        raise CodecError("At least one frame is needed")
    if not packet.is_rf:
        return to_b64(encode(Packet(packet.type, repeat, packet.pulses)))
    all_frames = split_frames(packet.pulses)
    _, good = _dominant(all_frames)
    good = [f for f in good if f.gap is not None] or good
    if not good:
        return to_b64(encode(Packet(packet.type, repeat, packet.pulses)))
    # The pause *between* frames comes from frames followed by another one;
    # the last frame's gap is the closing silence and must not end up in the
    # middle of the burst (a receiver would read it as a second press).
    inner = [f.gap for f in all_frames[:-1] if f.gap and f.signature == good[0].signature]
    if inner:
        frame_gap = Counter(inner).most_common(1)[0][0]
    else:  # a single frame: typical remotes pause ~20 % of a frame
        frame_gap = max(round(MIN_GAP_US / TICK_US), round(sum(good[0].pulses) * 0.2))
    kept = [good[i % len(good)] for i in range(frames)]
    pulses: list[int] = []
    for frame in kept:
        pulses += frame.pulses
        pulses.append(frame_gap)
    pulses[-1] = max(frame_gap, TAIL_GAP_TICKS)
    return to_b64(encode(Packet(packet.type, repeat, pulses)))


MAX_FRAMES_PER_PACKET = 12  # keeps packets well under the Broadlink's size limit


def hold(code: str | bytes, seconds: float) -> str:
    """Emulate keeping the button pressed for ``seconds`` (dimmers, blinds).

    Repeats the clean frame for the whole duration. Long holds use the
    packet's repeat count so each packet stays small.
    """
    packet = decode(code)
    if seconds <= 0 or not packet.is_rf:
        return to_b64(encode(packet))
    _, good = _dominant(split_frames(packet.pulses))
    if not good:
        return to_b64(encode(packet))
    frame_ms = good[0].duration_us / 1000
    total = max(1, round(seconds * 1000 / frame_ms))
    repeat = -(-total // MAX_FRAMES_PER_PACKET) - 1
    per_packet = -(-total // (repeat + 1))
    return clean(code, frames=per_packet, repeat=repeat)


def capture_result(code: str, frequency: float | None) -> dict:
    """Raw capture, its analysis and the cleaned version the UI proposes."""
    analysis = analyze(code)
    cleaned = clean(code) if analysis["needs_cleaning"] else code
    return {
        "frequency": frequency,
        "raw": code,
        "raw_analysis": analysis,
        "code": cleaned,
        "analysis": analyze(cleaned),
        "fingerprint": fingerprint(code),
    }

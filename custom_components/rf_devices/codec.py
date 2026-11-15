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

Some remotes send each repetition in several parts with a pause in between
(a preamble, a pause, then the data). ``split_frames`` sees every part as a
frame of its own; ``_groups`` finds the group of parts that repeats, and
``analyze``, ``clean``, ``fingerprint`` and ``hold`` then work on whole
groups, so the preamble is never dropped.

This module has no Home Assistant dependency so it can be unit tested alone.
"""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

TICK_US = 269 / 8192 * 1000  # ~32.84 µs per tick

TYPE_IR = 0x26
TYPE_RF433 = 0xB2
TYPE_RF315 = 0xD7
KINDS = {TYPE_IR: "ir", TYPE_RF433: "rf433", TYPE_RF315: "rf315"}
# Some Broadlink apps store 433 MHz codes with this type byte and a huge repeat
# count. The pulses inside are the remote's: ``clean`` turns them into a
# normal 433 MHz code.
TYPE_RF433_APP = 0xB1

# A low pulse this long (or longer) separates two frames.
MIN_GAP_US = 2500
# Final silence appended after the last kept frame.
TAIL_GAP_TICKS = 1500

DEFAULT_FRAMES = 4

# A repetition made of parts separated by pauses (preamble + data) has at
# most this many parts.
MAX_PARTS = 4
# Two parts are the same part of two repetitions when they have the same
# number of pulses and last the same, give or take this share.
PART_TOLERANCE = 0.1

# A press never lasts this long, even held (``hold`` goes up to 10 s): a code
# that does is not a remote's (e.g. something pasted with a wrong first byte).
MAX_PRESS_MS = 15_000
# Why a code cannot be stored or sent (``problem``).
PROBLEM_NOT_RF_IR = "not_rf_ir"
PROBLEM_TOO_LONG = "too_long"
PROBLEM_CONVERTIBLE = "convertible"
# A converted code needs this many identical frames of at least this length.
MIN_CONVERT_FRAMES = 2
MIN_CONVERT_PULSES = 16


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


def kind_for_frequency(frequency_hz: float | None) -> int:
    """Broadlink packet type for a carrier (433 MHz band unless it is near 315)."""
    if frequency_hz and 300e6 <= frequency_hz < 350e6:
        return TYPE_RF315
    return TYPE_RF433


def to_timings(code: str | bytes) -> tuple[list[int], int]:
    """Signed microseconds (+on / −off) and repeat count, as HA's RF API wants them."""
    packet = decode(code)
    timings = [
        round(p * TICK_US) * (1 if i % 2 == 0 else -1) for i, p in enumerate(packet.pulses)
    ]
    return timings, packet.repeat


def from_timings(bursts: list[list[int]], kind: int = TYPE_RF433, repeat: int = 0) -> str:
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
    return to_b64(encode(Packet(kind, repeat, ticks)))


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


def _alike(a: Frame, b: Frame) -> bool:
    """Same number of pulses and about the same duration."""
    if a.length != b.length:
        return False
    ta, tb = sum(a.pulses), sum(b.pulses)
    return abs(ta - tb) <= max(4, PART_TOLERANCE * max(ta, tb))


def _cut_from(piece: Frame, whole: Frame) -> bool:
    """``piece`` is the end of ``whole``: a frame whose beginning was not recorded."""
    if not 1 < piece.length < whole.length:
        return False
    tail = whole.pulses[-piece.length :]
    return all(abs(p - q) <= max(2, 0.2 * q) for p, q in zip(piece.pulses[1:], tail[1:], strict=True))


def _run(frames: list[Frame], period: int) -> tuple[int, int]:
    """Longest stretch (start, length) where every frame is like the one ``period`` later."""
    best = (0, 0)
    start = None
    for i in range(len(frames) - period + 1):
        ok = i + period < len(frames) and _alike(frames[i], frames[i + period])
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            length = i + period - start
            if length > best[1]:
                best = (start, length)
            start = None
    return best


def _groups(frames: list[Frame]) -> tuple[list[list[Frame]], int] | None:
    """Repetitions made of several parts: (complete groups, index of the data part).

    None for the usual remote, whose repetition is a single frame. A group is
    found by the rhythm of the capture (the same sequence of lengths coming
    back every N frames), not by the signature of one part: a preamble of
    near-equal pulses quantises differently each time. One part must still
    carry the same signature in two groups or more: that is the data, and
    groups where it differs are left out. A group ends with its data.

    A packet that holds one group and nothing repeated (what ``clean`` gives
    when asked for a single frame) is that group.
    """
    period, (start, length) = 1, _run(frames, 1)
    for parts in range(2, MAX_PARTS + 1):
        candidate = _run(frames, parts)
        if candidate[1] < 2 * parts or candidate[1] <= length:
            continue
        group = frames[candidate[0] : candidate[0] + parts]
        if any(_alike(a, b) for i, a in enumerate(group) for b in group[i + 1 :]):
            continue  # the same frame several times and a damaged one, not parts
        period, (start, length) = parts, candidate
    if period > 1:
        groups = [frames[i : i + period] for i in range(start, start + length - period + 1, period)]
        # The data is the part that repeats best; when all do, the longest.
        best: tuple[int, int, int, str] | None = None
        for part in range(period):
            signature, count = Counter(g[part].signature for g in groups).most_common(1)[0]
            rank = (count, groups[0][part].length)
            if groups[0][part].length > 1 and (best is None or rank > best[:2]):
                best = (*rank, part, signature)
        if not best or best[0] < 2:
            return None
        *_, part, signature = best
        if part != period - 1:
            # The stretch began in the middle of a repetition (a part was
            # missed just before it): a repetition ends with its data.
            shifted = [
                frames[i : i + period]
                for i in range(start + part + 1, start + length - period + 1, period)
            ]
            if sum(g[-1].signature == signature for g in shifted) >= 2:
                groups, part = shifted, period - 1
        return [g for g in groups if g[part].signature == signature], part
    if length >= 2 or not 2 <= len(frames) <= MAX_PARTS:
        return None
    counts = Counter(f.signature for f in frames if f.length > 1)
    if len(counts) < 2 or max(counts.values()) > 1 or any(f.gap is None for f in frames[:-1]):
        return None
    data = max(range(len(frames)), key=lambda i: frames[i].length)
    if any(_cut_from(f, frames[data]) for f in frames if f is not frames[data]):
        return None  # the end of a frame and the frame: a short press, not two parts
    return [frames], data


def _group_pulses(group: list[Frame]) -> list[int]:
    """The pulses of a group, with the pauses between its parts."""
    pulses: list[int] = []
    for part in group[:-1]:
        pulses += part.pulses
        pulses.append(part.gap or 0)
    return pulses + group[-1].pulses


def _converted(packet: Packet) -> Packet | None:
    """The 433 MHz packet inside a ``TYPE_RF433_APP`` one, or None.

    Only when it really holds a remote's message: the same frame, long enough
    not to be noise, at least twice.
    """
    if packet.type != TYPE_RF433_APP:
        return None
    _, good = _dominant(split_frames(packet.pulses))
    good = [f for f in good if f.gap is not None]
    if len(good) < MIN_CONVERT_FRAMES or good[0].length < MIN_CONVERT_PULSES:
        return None
    return Packet(TYPE_RF433, 0, packet.pulses)


def problem(code: str | bytes) -> str | None:
    """Why a valid packet is still not a usable code, or None.

    ``decode`` only checks the layout. A code pasted from another app can pass
    it and still be junk: an unknown type byte, or a repeat count that would
    keep the transmitter busy for minutes.
    """
    packet = decode(code)
    if packet.type not in KINDS:
        return PROBLEM_CONVERTIBLE if _converted(packet) else PROBLEM_NOT_RF_IR
    if sum(packet.pulses) * TICK_US * (packet.repeat + 1) / 1000 > MAX_PRESS_MS:
        return PROBLEM_TOO_LONG
    return None


def ensure_usable(code: str | bytes) -> None:
    """Raise ``CodecError`` unless the code can be stored and sent."""
    packet = decode(code)
    reason = problem(code)
    if reason == PROBLEM_CONVERTIBLE:
        raise CodecError("Code in a Broadlink app's format: clean it to turn it into a normal 433 MHz code")
    if reason == PROBLEM_NOT_RF_IR:
        raise CodecError(f"Not an IR or RF code (type byte 0x{packet.type:02X}): learn the button again")
    if reason == PROBLEM_TOO_LONG:
        raise CodecError(
            f"The code would take {sum(packet.pulses) * TICK_US * (packet.repeat + 1) / 1_000_000:.0f} s "
            f"to send (repeat {packet.repeat}): learn the button again"
        )


def analyze(code: str | bytes) -> dict:
    """Describe a packet for the UI."""
    packet = decode(code)
    frames = split_frames(packet.pulses)
    total_us = sum(packet.pulses) * TICK_US
    grouped = _groups(frames)
    if grouped:
        # A repetition is a whole group: count groups, not their parts.
        groups, data = grouped
        first = {id(g[0]): g for g in groups}
        inside = {id(f) for g in groups for f in g}
        sample = groups[0][data]
        sample_pulses = _group_pulses(groups[0])
        sample_gap = groups[0][-1].gap
        frame_map = [
            {"pulses": len(_group_pulses(first[id(f)])), "ok": True}
            if id(f) in first
            else {"pulses": f.length, "ok": False}
            for f in frames
            if id(f) in first or id(f) not in inside
        ]
        good_count = len(groups)
        parts = len(groups[0])
    else:
        signature, good = _dominant(frames)
        sample = good[0] if good else frames[0]
        sample_pulses, sample_gap = sample.pulses, sample.gap
        frame_map = [{"pulses": f.length, "ok": f.signature == signature} for f in frames]
        good_count = len(good)
        parts = 1
    result = {
        "kind": packet.kind,
        "repeat": packet.repeat,
        "pulses": len(packet.pulses),
        "duration_ms": round(total_us / 1000, 1),
        "sent_ms": round(total_us * (packet.repeat + 1) / 1000, 1),
        "frames": len(frame_map),
        "good_frames": good_count,
        "bad_frames": len(frame_map) - good_count,
        "parts": parts,
        "frame_pulses": len(sample_pulses),
        "frame_ms": round((sum(sample_pulses) + (sample_gap or 0)) * TICK_US / 1000, 1),
        "bits": sample.bits,
        "hex": _bits_to_hex(sample.bits),
        "sample_us": [round(p * TICK_US) for p in sample_pulses]
        + ([round(sample_gap * TICK_US)] if sample_gap else []),
        "frame_map": frame_map,
    }
    result["problem"] = problem(code)
    result["needs_cleaning"] = result["problem"] == PROBLEM_CONVERTIBLE or packet.is_rf and (
        result["bad_frames"] > 0
        or packet.repeat > 0
        or good_count > DEFAULT_FRAMES * 2
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
    frames = split_frames(packet.pulses)
    grouped = _groups(frames)
    if grouped:  # the data part: the preamble is the same for every button
        groups, data = grouped
        return f"{packet.kind}:{groups[0][data].signature}"
    signature, good = _dominant(frames)
    return f"{packet.kind}:{signature or ''}"


def clean(code: str | bytes, frames: int = DEFAULT_FRAMES, repeat: int = 0) -> str:
    """Keep ``frames`` complete identical frames, sent ``repeat + 1`` times.

    When each repetition has several parts (preamble, pause, data), a frame
    here is the whole group, kept with the pauses between its parts.

    Returns the new code as base64 without the ``b64:`` prefix. IR packets and
    packets without a repeated frame are returned unchanged apart from the
    repeat byte. A code in a Broadlink app's format (``TYPE_RF433_APP``) comes
    out as a normal 433 MHz one.
    """
    packet = decode(code)
    if frames < 1:
        raise CodecError("At least one frame is needed")
    packet = _converted(packet) or packet
    if not packet.is_rf:
        return to_b64(encode(Packet(packet.type, repeat, packet.pulses)))
    all_frames = split_frames(packet.pulses)
    grouped = _groups(all_frames)
    if grouped:
        return to_b64(encode(Packet(packet.type, repeat, _clean_groups(all_frames, grouped[0], frames))))
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


def _clean_groups(all_frames: list[Frame], groups: list[list[Frame]], count: int) -> list[int]:
    """``count`` equal groups, each part followed by the pause that usually follows it."""
    closing = all_frames[-1]
    gaps: list[int] = []
    for part in range(len(groups[0])):
        # As with single frames, the closing silence is not a pause of the burst.
        seen = [g[part].gap for g in groups if g[part].gap and g[part] is not closing]
        if seen:
            gaps.append(Counter(seen).most_common(1)[0][0])
        else:  # a single group: typical remotes pause ~20 % of a frame
            gaps.append(max(round(MIN_GAP_US / TICK_US), round(sum(groups[0][part].pulses) * 0.2)))
    # Every kept group is the same: each pulse is its median over the groups
    # of the capture, which irons out the jitter of the receiver (a preamble
    # of near-equal pulses has little else).
    one: list[int] = []
    for part, gap in zip(range(len(groups[0])), gaps, strict=True):
        one += [round(median(ps)) for ps in zip(*(g[part].pulses for g in groups), strict=True)]
        one.append(gap)
    pulses = one * count
    pulses[-1] = max(gaps[-1], TAIL_GAP_TICKS)
    return pulses


MAX_FRAMES_PER_PACKET = 12  # keeps packets well under the Broadlink's size limit


def hold(code: str | bytes, seconds: float) -> str:
    """Emulate keeping the button pressed for ``seconds`` (dimmers, blinds).

    Repeats the clean frame for the whole duration. Long holds use the
    packet's repeat count so each packet stays small.
    """
    packet = decode(code)
    if seconds <= 0 or not packet.is_rf:
        return to_b64(encode(packet))
    all_frames = split_frames(packet.pulses)
    grouped = _groups(all_frames)
    if grouped:
        frame_ms = sum(f.duration_us for f in grouped[0][0]) / 1000
    else:
        _, good = _dominant(all_frames)
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

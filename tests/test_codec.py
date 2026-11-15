"""Codec tests: no Home Assistant needed."""

import pytest

from custom_components.rf_devices import codec

from .helpers import (
    BITS_A,
    BITS_B,
    DATA_GAP,
    PREAMBLE_GAP,
    capture,
    frame,
    preamble,
    two_part_capture,
)


def test_roundtrip() -> None:
    code = capture(BITS_A)
    packet = codec.decode(code)
    assert packet.kind == "rf433"
    assert packet.repeat == 1
    assert codec.decode(codec.encode(packet)).pulses == packet.pulses


def test_b64_prefix_and_errors() -> None:
    code = capture(BITS_A)
    assert codec.decode("b64:" + code).pulses == codec.decode(code).pulses
    with pytest.raises(codec.CodecError):
        codec.decode("not base64!!")
    with pytest.raises(codec.CodecError):
        codec.decode("AAA=")


def test_analyze_held_button() -> None:
    a = codec.analyze(capture(BITS_A, frames=12))
    assert a["frames"] == 13
    assert a["good_frames"] == 12
    assert a["bad_frames"] == 1
    assert a["bits"] == BITS_A + "0"  # trailing on-pulse reads as a short bit
    assert a["needs_cleaning"]
    assert a["frame_map"][0] == {"pulses": 13, "ok": False}


def test_clean_keeps_complete_frames_sent_once() -> None:
    raw = capture(BITS_A, frames=12, repeat=3)
    cleaned = codec.clean(raw, frames=4)
    a = codec.analyze(cleaned)
    assert a["repeat"] == 0
    assert a["frames"] == a["good_frames"] == 4
    assert a["bits"] == codec.analyze(raw)["bits"]
    assert not a["needs_cleaning"]
    assert a["sent_ms"] < codec.analyze(raw)["sent_ms"] / 5
    # Cleaning twice changes nothing.
    assert codec.clean(cleaned, frames=4) == cleaned


def test_clean_pads_short_capture() -> None:
    cleaned = codec.clean(capture(BITS_A, frames=2, truncated=False), frames=4)
    assert codec.analyze(cleaned)["good_frames"] == 4


def test_fingerprint_ignores_hold_time() -> None:
    assert codec.fingerprint(capture(BITS_A, 12)) == codec.fingerprint(capture(BITS_A, 5, 0, False))
    assert codec.fingerprint(capture(BITS_A)) != codec.fingerprint(capture(BITS_B))


def test_ir_is_not_reshaped() -> None:
    packet = codec.Packet(codec.TYPE_IR, 2, [300, 150, 20, 20, 20, 60, 20, 3000])
    code = codec.to_b64(codec.encode(packet))
    out = codec.decode(codec.clean(code))
    assert out.type == codec.TYPE_IR
    assert out.repeat == 0
    assert out.pulses == packet.pulses
    assert not codec.analyze(code)["needs_cleaning"]


def test_hold_fills_duration() -> None:
    raw = capture(BITS_A, frames=12)
    frame_ms = codec.analyze(codec.clean(raw, frames=1))["frame_ms"]
    short = codec.analyze(codec.hold(raw, 0.2))
    assert short["repeat"] == 0
    assert abs(short["sent_ms"] - 200) <= frame_ms
    long = codec.analyze(codec.hold(raw, 2))
    assert long["repeat"] >= 1
    assert long["good_frames"] <= codec.MAX_FRAMES_PER_PACKET
    assert abs(long["sent_ms"] - 2000) <= frame_ms * (long["repeat"] + 1)
    assert codec.hold(raw, 0) == codec.to_b64(codec.encode(codec.decode(raw)))


def test_reclean_to_fewer_or_more_frames() -> None:
    four = codec.clean(capture(BITS_A), frames=4)
    one = codec.analyze(codec.clean(four, frames=1))
    assert one["good_frames"] == 1 and one["bits"] == codec.analyze(four)["bits"]
    assert codec.analyze(codec.clean(four, frames=2))["good_frames"] == 2
    eight = codec.decode(codec.clean(four, frames=8))
    frames = codec.split_frames(eight.pulses)
    assert len(frames) == 8
    inner_gaps = {f.gap for f in frames[:-1]}
    assert inner_gaps == {codec.split_frames(codec.decode(four).pulses)[0].gap}  # no 49 ms pause inside
    # Back up from a single frame: the gap is estimated, never the closing silence.
    back = codec.split_frames(codec.decode(codec.clean(codec.clean(four, frames=1), frames=3)).pulses)
    assert len(back) == 3 and max(f.gap for f in back[:-1]) < codec.TAIL_GAP_TICKS


def test_problem_flags_codes_that_are_not_a_remote() -> None:
    """Reported by a user: a code pasted from another app was stored with an unknown
    type byte and a repeat count that would have sent it for about 94 s."""
    good = codec.clean(capture(BITS_A))
    assert codec.problem(good) is None
    codec.ensure_usable(good)
    assert codec.analyze(good)["problem"] is None

    alien = codec.to_b64(codec.encode(codec.Packet(0x52, 0, frame(BITS_A) + [245])))
    assert codec.problem(alien) == codec.PROBLEM_NOT_RF_IR
    with pytest.raises(codec.CodecError, match="0x52"):
        codec.ensure_usable(alien)

    endless = capture(BITS_A, frames=4, repeat=192, truncated=False)
    assert codec.analyze(endless)["problem"] == codec.PROBLEM_TOO_LONG
    with pytest.raises(codec.CodecError, match="repeat 192"):
        codec.ensure_usable(endless)
    # Cleaning makes it a normal press again…
    assert codec.problem(codec.clean(endless)) is None
    # …and the longest hold the panel offers is still fine.
    assert codec.problem(codec.hold(good, 10)) is None


def _app_code(bits: str | None, repeat: int = 192) -> str:
    """A 433 MHz code as some Broadlink apps store it: type 0xB1, huge repeat count."""
    pulses = codec.decode(capture(bits, frames=6)).pulses if bits else [7, 31, 12, 66, 9] * 4
    return codec.to_b64(codec.encode(codec.Packet(codec.TYPE_RF433_APP, repeat, pulses)))


def test_broadlink_app_codes_are_converted_by_cleaning() -> None:
    """Reported by a user: a code copied from the Broadlink app (0xB1, repeat 192) held the
    remote's frames; cleaning turns it into the same code a capture would give."""
    app = _app_code(BITS_A)
    assert codec.problem(app) == codec.PROBLEM_CONVERTIBLE
    assert codec.analyze(app)["needs_cleaning"]
    with pytest.raises(codec.CodecError, match="Broadlink app"):
        codec.ensure_usable(app)

    converted = codec.clean(app)
    packet = codec.decode(converted)
    assert (packet.type, packet.repeat) == (codec.TYPE_RF433, 0)
    assert codec.problem(converted) is None
    assert codec.analyze(converted)["bits"].startswith(BITS_A)
    assert converted == codec.clean(capture(BITS_A))

    # The panel's paste dialog proposes the converted code straight away.
    result = codec.capture_result(app, None)
    assert result["code"] == converted and result["analysis"]["problem"] is None

    # Not a remote inside: stays refused, cleaning cannot make it usable.
    junk = _app_code(None)
    assert codec.problem(junk) == codec.PROBLEM_NOT_RF_IR
    assert codec.problem(codec.clean(junk)) == codec.PROBLEM_NOT_RF_IR


def _parts(code: str) -> list[tuple[int, int | None]]:
    return [(f.length, f.gap) for f in codec.split_frames(codec.decode(code).pulses)]


def test_clean_keeps_the_preamble_of_a_two_part_remote() -> None:
    """Reported with a curtain motor: each repetition is a preamble, a pause and the data.
    Cleaning kept only the data and the motor ignored it."""
    raw = two_part_capture(BITS_A)
    data = len(frame(BITS_A))
    a = codec.analyze(raw)
    assert a["parts"] == 2
    assert (a["frames"], a["good_frames"], a["bad_frames"]) == (9, 8, 1)  # repetitions, not parts
    assert a["frame_map"][0] == {"pulses": 21, "ok": False}
    assert a["frame_map"][1] == {"pulses": 17 + 1 + data, "ok": True}
    assert a["bits"] == BITS_A + "0"  # the data, not the preamble
    assert a["needs_cleaning"]

    cleaned = codec.clean(raw, frames=4)
    assert _parts(cleaned) == [(17, PREAMBLE_GAP), (data, DATA_GAP)] * 3 + [
        (17, PREAMBLE_GAP),
        (data, codec.TAIL_GAP_TICKS),
    ]
    frames = codec.split_frames(codec.decode(cleaned).pulses)
    assert all(f.pulses == frame(BITS_A) for f in frames[1::2])
    assert all(abs(p - q) <= 1 for f in frames[0::2] for p, q in zip(f.pulses, preamble(), strict=True))
    c = codec.analyze(cleaned)
    assert c["repeat"] == 0
    assert (c["frames"], c["good_frames"], c["bad_frames"], c["parts"]) == (4, 4, 0, 2)
    assert c["bits"] == a["bits"] and abs(c["frame_ms"] - a["frame_ms"]) <= 0.2
    assert not c["needs_cleaning"]
    assert codec.clean(cleaned, frames=4) == cleaned  # cleaning twice changes nothing

    result = codec.capture_result(raw, 433.92)
    assert result["code"] == cleaned
    assert result["analysis"]["good_frames"] == codec.DEFAULT_FRAMES


def test_two_part_remote_fingerprint_reclean_and_hold() -> None:
    raw = two_part_capture(BITS_A)
    cleaned = codec.clean(raw)
    # The buttons share the preamble: the identity is the data.
    assert codec.fingerprint(raw) == codec.fingerprint(cleaned)
    assert codec.fingerprint(raw) == codec.fingerprint(two_part_capture(BITS_A, groups=3, truncated=False))
    assert codec.fingerprint(raw) != codec.fingerprint(two_part_capture(BITS_B))
    # Down to one repetition and back up: the preamble stays in front of the data.
    one = codec.clean(cleaned, frames=1)
    a = codec.analyze(one)
    assert (a["frames"], a["good_frames"], a["parts"], a["needs_cleaning"]) == (1, 1, 2, False)
    assert codec.fingerprint(one) == codec.fingerprint(raw)
    back = _parts(codec.clean(one, frames=3))
    assert [n for n, _ in back] == [17, len(frame(BITS_A))] * 3
    assert back[0][1] == PREAMBLE_GAP and back[1][1] < codec.TAIL_GAP_TICKS
    # Holding the button repeats whole groups.
    held = codec.analyze(codec.hold(cleaned, 2))
    assert held["parts"] == 2 and held["bad_frames"] == 0
    assert held["good_frames"] <= codec.MAX_FRAMES_PER_PACKET
    assert abs(held["sent_ms"] - 2000) <= a["frame_ms"] * (held["repeat"] + 1)


def test_two_part_remote_with_a_missed_preamble() -> None:
    """Two data frames in a row (a preamble was not received) do not make it a one-part remote."""
    raw = two_part_capture(BITS_A, skip_preamble=2)
    a = codec.analyze(raw)
    assert a["parts"] == 2 and a["good_frames"] >= 5
    cleaned = codec.clean(raw)
    assert [n for n, _ in _parts(cleaned)] == [17, len(frame(BITS_A))] * 4
    assert codec.fingerprint(cleaned) == codec.fingerprint(two_part_capture(BITS_A))


def test_one_part_remotes_are_not_grouped() -> None:
    for code in (capture(BITS_A), capture(BITS_A, frames=2, truncated=False), capture(BITS_A, frames=1)):
        assert codec.analyze(code)["parts"] == 1
    # Kept exactly as before: the first complete frames of the capture, untouched.
    kept = codec.split_frames(codec.decode(codec.clean(capture(BITS_A))).pulses)
    assert [f.pulses for f in kept] == [frame(BITS_A)] * 4

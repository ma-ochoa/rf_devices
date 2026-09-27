"""Codec tests: no Home Assistant needed."""

import pytest

from custom_components.rf_devices import codec

from .helpers import BITS_A, BITS_B, capture


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

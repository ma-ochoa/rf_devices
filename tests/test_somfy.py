"""Somfy RTS frames: building, timings and decoding."""

from __future__ import annotations

from itertools import pairwise

import pytest

from custom_components.rf_devices.protocols import somfy


def test_frame_matches_the_reference_algorithm():
    # Same steps as Somfy_Remote_Lib.buildFrame, written out by hand.
    frame = somfy.build_frame(0x123456, "up", 0x0042)
    clear = [0xA7, 0x20, 0x00, 0x42, 0x12, 0x34, 0x56]
    checksum = 0
    for b in clear:
        checksum ^= b ^ (b >> 4)
    clear[1] |= checksum & 0xF
    for i in range(1, 7):
        clear[i] ^= clear[i - 1]
    assert list(frame) == clear


def test_parse_is_the_inverse_of_build():
    for button in somfy.BUTTONS:
        frame = somfy.build_frame(0xABCDEF, button, 513)
        assert somfy.parse_frame(frame) == somfy.Press(0xABCDEF, button, 513)


def test_bad_checksum_is_refused():
    frame = bytearray(somfy.build_frame(0xABCDEF, "down", 7))
    frame[6] ^= 0x01  # the last byte only changes itself once de-obfuscated
    assert somfy.parse_frame(bytes(frame)) is None


@pytest.mark.parametrize("bad", [0, somfy.MAX_ADDRESS + 1])
def test_address_range(bad):
    with pytest.raises(somfy.SomfyError):
        somfy.build_frame(bad, "up", 1)


def test_unknown_button():
    with pytest.raises(somfy.SomfyError):
        somfy.build_frame(1, "jump", 1)


def test_timings_shape():
    timings = somfy.encode(0x123456, "my", 10, repeats=2)
    assert timings[0] == somfy.WAKEUP_HIGH
    assert timings[1] == -somfy.WAKEUP_LOW
    # Alternating signs: nothing to merge any more.
    assert all((a > 0) != (b > 0) for a, b in pairwise(timings))
    # Every frame ends with the long gap.
    assert sum(1 for v in timings[2:] if v <= -somfy.FRAME_GAP) == 3
    assert timings[-1] <= -somfy.FRAME_GAP


@pytest.mark.parametrize("button", list(somfy.BUTTONS))
def test_decode_own_timings(button):
    timings = somfy.encode(0x0F00F0, button, 0xFFFE, repeats=3)
    presses = somfy.decode(timings)
    assert len(presses) == 4
    assert set(presses) == {somfy.Press(0x0F00F0, button, 0xFFFE)}


def test_decode_with_receiver_jitter():
    timings = somfy.encode(0x010203, "down", 300, repeats=1)
    noisy = [round(v * (1.12 if i % 3 else 0.9)) for i, v in enumerate(timings)]
    assert somfy.decode(noisy)[0] == somfy.Press(0x010203, "down", 300)


def test_decode_split_bursts_and_noise():
    timings = somfy.encode(0x777777, "up", 1, repeats=0)
    # A receiver may drop the wake-up and deliver the frame alone.
    frame_only = timings[2:]
    assert somfy.decode([120, -80, *frame_only]) == [somfy.Press(0x777777, "up", 1)]
    assert somfy.decode([300, -300] * 50) == []


def test_repeats_for_hold():
    assert somfy.repeats_for(0) == somfy.DEFAULT_REPEATS
    assert somfy.repeats_for(3) > somfy.DEFAULT_REPEATS
    assert somfy.repeats_for(1000) == somfy.MAX_REPEATS


@pytest.mark.parametrize("button", list(somfy.BUTTONS))
def test_decode_frames_without_the_final_silence(button):
    """A receiver ends each burst on the last mark: the trailing gap is not reported."""
    timings = somfy.encode(0x13579B, button, 501, repeats=0)
    frame = [t for t in timings[2:] if t > -12_000]
    assert somfy.decode(frame) == [somfy.Press(0x13579B, button, 501)]

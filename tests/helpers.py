"""Synthetic Broadlink RF packets for tests."""

from custom_components.rf_devices import codec

SHORT, LONG, GAP = 9, 25, 245  # ticks: ~0.3 ms, ~0.8 ms, ~8 ms


def frame(bits: str) -> list[int]:
    """PWM frame: '1' = long on + short off, '0' = short on + long off; ends with an on-pulse."""
    pulses: list[int] = []
    for b in bits:
        pulses += [LONG, SHORT] if b == "1" else [SHORT, LONG]
    pulses.append(SHORT)
    return pulses


def capture(bits: str, frames: int = 12, repeat: int = 1, truncated: bool = True) -> str:
    """What the Broadlink returns when the button is held: a cut frame, then repetitions."""
    one = frame(bits)
    pulses: list[int] = []
    if truncated:
        pulses += one[-13:] + [GAP]
    for _ in range(frames):
        pulses += one + [GAP]
    pulses[-1] = 1500
    return codec.to_b64(codec.encode(codec.Packet(codec.TYPE_RF433, repeat, pulses)))


BITS_A = "101100001111000010100101"
BITS_B = "101100001111000010101010"

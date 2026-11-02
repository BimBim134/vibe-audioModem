"""The three Presets and the PHY profile each one names.

All three send M-FSK with 8 tones, 1 / symbol duration apart, and spread the coded bits over the
whole Transmission; they differ by the symbol duration, which trades airtime against range and
occupied band. The measurements behind the choices are in `docs/measurements/README.md` and
`docs/adr/0004-three-presets-of-8-fsk.md`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PhyProfile:
    tones: int
    symbol_ms: float
    interleave: bool


DEFAULT_PRESET = "standard"

PRESETS = {
    "max-range": PhyProfile(tones=8, symbol_ms=320.0, interleave=True),
    "standard": PhyProfile(tones=8, symbol_ms=80.0, interleave=True),
    "fast": PhyProfile(tones=8, symbol_ms=40.0, interleave=True),
}


def profile(preset: str) -> PhyProfile:
    """The PHY profile of a Preset, or a ValueError that lists the Presets there are."""
    try:
        return PRESETS[preset]
    except KeyError:
        known = ", ".join(PRESETS)
        raise ValueError(f"unknown Preset {preset!r}: the Presets are {known}") from None

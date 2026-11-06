"""The interface every modem candidate implements, so the bench can measure any of them."""

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Reception:
    """One Message found in the audio, with how well it was received.

    Metrics a candidate cannot provide stay None.
    """

    message: bytes
    snr_db: float | None = None  # estimated SNR in a 2,500 Hz reference bandwidth
    frequency_offset_hz: float | None = None
    sync_score: float | None = None
    start_sample: int | None = None  # where the Signal starts in the audio that was given


@dataclass(frozen=True)
class Detection:
    """A Signal found in the audio whose Message could not be read."""

    start_sample: int
    frequency_hz: float  # of its lowest tone
    sync_score: float


@dataclass(frozen=True)
class Report:
    """Everything a receiver found in a recording."""

    receptions: list[Reception]
    undecoded: list[Detection]  # found whole, but the checksum or the code refused them
    arriving: list[Detection] = field(default_factory=list)  # found, but not heard to the end yet


class Modem(Protocol):
    """A candidate modem: Message and Preset to audio samples, and audio samples to Messages."""

    def modulate(self, message: bytes, preset: str) -> np.ndarray:
        """Audio samples (mono, float) that carry the Message, formed for the named Preset."""
        ...

    def demodulate(self, samples: np.ndarray) -> list[Reception]:
        """Every Message found in the audio; empty when nothing could be received."""
        ...

"""A deliberately simple modem that validates the bench: coherent BPSK, no synchronisation.

Its error rate on white noise has a textbook formula, so a measured curve that disagrees
with theory points at a bug in the bench rather than in a candidate. It knows the tone
phase and bit timing (they are fixed by construction), carries no error correction and
returns one Message made of every complete byte in the audio.
"""

import numpy as np

from bench.channel import ChannelConfig
from vibemodem.core.modem import Reception

SAMPLE_RATE = int(ChannelConfig().sample_rate)  # the toy and the channel must agree
TONE_HZ = 1500
BIT_RATE = 100  # bits per second
AMPLITUDE = 0.5
SAMPLES_PER_BIT = SAMPLE_RATE // BIT_RATE
PRESET = "standard"

# One bit of tone holds a whole number of cycles, so every bit starts at the same phase.
_TONE = np.cos(2 * np.pi * TONE_HZ * np.arange(SAMPLES_PER_BIT) / SAMPLE_RATE)
_TONE.flags.writeable = False  # shared by every ToyModem


class ToyModem:
    def modulate(self, message: bytes, preset: str) -> np.ndarray:
        if preset != PRESET:
            raise ValueError(f"the toy modem only knows the {PRESET!r} Preset, not {preset!r}")
        bits = np.unpackbits(np.frombuffer(message, dtype=np.uint8))
        polarity = 2.0 * bits - 1.0  # bit 1 -> +tone, bit 0 -> -tone
        return AMPLITUDE * np.repeat(polarity, SAMPLES_PER_BIT) * np.tile(_TONE, bits.size)

    def demodulate(self, samples: np.ndarray) -> list[Reception]:
        whole_bytes = samples.size // SAMPLES_PER_BIT // 8
        if whole_bytes == 0:
            return []
        bit_slots = samples[: whole_bytes * 8 * SAMPLES_PER_BIT].reshape(-1, SAMPLES_PER_BIT)
        bits = (bit_slots @ _TONE > 0).astype(np.uint8)
        return [Reception(message=np.packbits(bits).tobytes())]

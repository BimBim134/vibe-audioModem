"""An 8-FSK modem that works with any error-correcting code.

8-FSK in about 100 Hz, a fixed-size Frame protected by a CRC-32 and by the code given at
construction, decoded from soft values, and a known 32-symbol preamble that the receiver looks
for at every start time and audio frequency. Modems that differ only by their code come from
here, so a difference in their Success threshold is the code's.
"""

import math

import numpy as np

from vibemodem.core import frame, mfsk
from vibemodem.core.code import Code
from vibemodem.core.modem import Reception

PRESET = "standard"
SAMPLE_RATE = mfsk.SAMPLE_RATE
NOISE_BANDWIDTH_HZ = 2500  # the reference bandwidth in which SNRs are quoted
# The search keeps a few arrays of (windows x frequencies) numbers; this bounds their size.
MAX_RECORDING_SECONDS = 600

# For each bit of a symbol, which of the 8 tones stand for a 0.
_ZERO_TONES = np.array(
    [
        [(tone >> (mfsk.BITS_PER_SYMBOL - 1 - bit)) & 1 == 0 for tone in range(mfsk.TONES)]
        for bit in range(mfsk.BITS_PER_SYMBOL)
    ]
)
_ZERO_TONES.flags.writeable = False
# How the energy ratio at a tone becomes an SNR: the noise of the reference bandwidth over one
# symbol.
_ENERGY_RATIO_PER_SNR = mfsk.SYMBOL_SECONDS * NOISE_BANDWIDTH_HZ


def _soft_bits(relative_energy: np.ndarray) -> np.ndarray:
    """One soft value per coded bit, positive when the tones for 0 are the louder ones."""
    soft = np.empty((relative_energy.shape[0], mfsk.BITS_PER_SYMBOL))
    for bit, zero_tones in enumerate(_ZERO_TONES):
        zero = np.where(zero_tones, relative_energy, -np.inf).max(axis=1)
        one = np.where(~zero_tones, relative_energy, -np.inf).max(axis=1)
        soft[:, bit] = zero - one
    return soft.reshape(-1)


class CodedMfskModem:
    """Sends one Message per Transmission; receives every Message found in a recording.

    Receptions of the same Message (a repeated Transmission) are merged into one.
    """

    def __init__(self, code: Code):
        if code.info_bits != frame.FRAME_BITS:
            raise ValueError(f"the code must take a Frame of {frame.FRAME_BITS} bits")
        self.code = code
        self._data_symbols = math.ceil(code.coded_bits / mfsk.BITS_PER_SYMBOL)

    def _data_tones(self, message: bytes) -> np.ndarray:
        coded = self.code.encode(frame.encode_frame(message))
        padding = np.zeros(self._data_symbols * mfsk.BITS_PER_SYMBOL - coded.size, dtype=np.uint8)
        symbols = np.concatenate([coded, padding]).reshape(self._data_symbols, -1)
        return symbols @ mfsk.BIT_WEIGHTS

    def modulate(self, message: bytes, preset: str) -> np.ndarray:
        if preset != PRESET:
            raise ValueError(f"unknown Preset {preset!r}: this modem only has {PRESET!r}")
        tones = np.concatenate([mfsk.PREAMBLE_TONES, self._data_tones(message)])
        return mfsk.synthesize(tones)

    def demodulate(self, samples: np.ndarray) -> list[Reception]:
        samples = np.asarray(samples, dtype=float)
        if samples.ndim != 1:
            raise ValueError("audio must be one channel (a 1-D array of samples)")
        if samples.size > MAX_RECORDING_SECONDS * SAMPLE_RATE:
            raise ValueError(
                f"recording too long: at most {MAX_RECORDING_SECONDS} s can be searched at once"
            )
        if not np.isfinite(samples).all():
            raise ValueError("audio samples must be finite numbers")

        received: dict[bytes, Reception] = {}
        for candidate in mfsk.find_signals(samples):
            reception = self._decode(samples, mfsk.refine(samples, candidate))
            if reception and (
                reception.message not in received
                or reception.sync_score > received[reception.message].sync_score
            ):
                received[reception.message] = reception
        return sorted(received.values(), key=lambda r: -r.sync_score)

    def _decode(self, samples: np.ndarray, signal: mfsk.Candidate) -> Reception | None:
        first_data_sample = signal.start_sample + mfsk.PREAMBLE_SYMBOLS * mfsk.SAMPLES_PER_SYMBOL
        if first_data_sample + self._data_symbols * mfsk.SAMPLES_PER_SYMBOL > samples.size:
            return None
        energy = mfsk.tone_energies(
            samples, first_data_sample, signal.first_tone_hz, self._data_symbols
        )
        # One tone in eight is loud, so the noise level is read below the median, where the
        # other seven are (7/8 of the values, half of them under their own median).
        noise_energy = np.quantile(energy, 7 / 16) / np.log(2)
        relative = energy / max(noise_energy, mfsk.NOISE_FLOOR_RATIO * energy.max() + 1e-300)

        decoded = self.code.decode(_soft_bits(relative)[: self.code.coded_bits])
        message = None if decoded is None else frame.decode_frame(decoded)
        if message is None:
            return None

        sent = self._data_tones(message)
        ratio = max(relative[np.arange(self._data_symbols), sent].mean() - 1.0, 1e-6)
        return Reception(
            message=message,
            snr_db=float(10 * np.log10(ratio / _ENERGY_RATIO_PER_SNR)),
            frequency_offset_hz=signal.first_tone_hz - mfsk.FIRST_TONE_HZ,
            sync_score=signal.score,
        )

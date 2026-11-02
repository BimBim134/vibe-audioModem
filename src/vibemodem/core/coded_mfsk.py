"""An M-FSK modem that works with any error-correcting code.

8-FSK in about 100 Hz by default, a fixed-size Frame protected by a CRC-32 and by the code given
at construction, decoded from soft values, and a known 32-symbol preamble that the receiver
looks for at every start time and audio frequency. Modems that differ only by their code come
from here, so a difference in their Success threshold is the code's.

The number of tones and the symbol duration can be changed, and the coded bits can be spread
over the whole Transmission (`interleave`) and sent several times (`repetitions`); the bench
sweeps these.
"""

import math

import numpy as np

from vibemodem.core import mfsk
from vibemodem.core.code import Code
from vibemodem.core.coded_modem import NOISE_BANDWIDTH_HZ, CodedModem
from vibemodem.core.modem import Reception

SAMPLE_RATE = mfsk.SAMPLE_RATE


class CodedMfskModem(CodedModem):
    """The modem that sends its coded bits as M-FSK symbols."""

    def __init__(
        self,
        code: Code,
        *,
        tones: int = 8,
        symbol_ms: float = 80.0,
        interleave: bool = False,
        repetitions: int = 1,
    ):
        super().__init__(code, interleave=interleave, repetitions=repetitions)
        self.waveform = mfsk.Waveform(tones=tones, symbol_seconds=symbol_ms / 1000)
        self._data_symbols = math.ceil(self._sent_bits / self.waveform.bits_per_symbol)
        # How the energy ratio at a tone becomes an SNR: the noise of the reference bandwidth
        # over one symbol.
        self._energy_ratio_per_snr = self.waveform.symbol_seconds * NOISE_BANDWIDTH_HZ

    @property
    def parameters(self) -> dict:
        """What a result file records so the waveform that was measured can be told apart."""
        return {
            "tones": self.waveform.tones,
            "symbol_ms": round(self.waveform.symbol_seconds * 1000, 6),
            "interleave": self._interleave,
            "repetitions": self._repetitions,
        }

    def _soft_bits(self, relative_energy: np.ndarray) -> np.ndarray:
        """One soft value per sent bit, positive when the tones for 0 are the louder ones."""
        waveform = self.waveform
        soft = np.empty((relative_energy.shape[0], waveform.bits_per_symbol))
        for bit, zero_tones in enumerate(waveform.zero_tones):
            zero = np.where(zero_tones, relative_energy, -np.inf).max(axis=1)
            one = np.where(~zero_tones, relative_energy, -np.inf).max(axis=1)
            soft[:, bit] = zero - one
        return soft.reshape(-1)

    def _data_tones(self, message: bytes) -> np.ndarray:
        sent = self._sent_stream(message)
        bits_per_symbol = self.waveform.bits_per_symbol
        padding = np.zeros(self._data_symbols * bits_per_symbol - sent.size, dtype=np.uint8)
        symbols = np.concatenate([sent, padding]).reshape(self._data_symbols, -1)
        return symbols @ self.waveform.bit_weights

    def _audio(self, message: bytes) -> np.ndarray:
        tones = np.concatenate([self.waveform.preamble_tones, self._data_tones(message)])
        return self.waveform.synthesize(tones)

    def _find(self, samples: np.ndarray) -> list[mfsk.Candidate]:
        return [
            self.waveform.refine(samples, candidate)
            for candidate in self.waveform.find_signals(samples)
        ]

    def _decode(self, samples: np.ndarray, signal: mfsk.Candidate) -> Reception | None:
        waveform = self.waveform
        size = waveform.samples_per_symbol
        first_data_sample = signal.start_sample + mfsk.PREAMBLE_SYMBOLS * size
        if first_data_sample + self._data_symbols * size > samples.size:
            return None
        energy = waveform.tone_energies(
            samples, first_data_sample, signal.first_tone_hz, self._data_symbols
        )
        # One tone in `tones` is loud, so the noise level is read below the median, where the
        # others are (a share (tones - 1) / tones of the values, half of them under their own
        # median).
        quiet_median = (waveform.tones - 1) / (2 * waveform.tones)
        noise_energy = np.quantile(energy, quiet_median) / np.log(2)
        relative = energy / max(noise_energy, mfsk.NOISE_FLOOR_RATIO * energy.max() + 1e-300)

        message = self._message(self._soft_bits(relative))
        if message is None:
            return None

        sent = self._data_tones(message)
        ratio = max(relative[np.arange(self._data_symbols), sent].mean() - 1.0, 1e-6)
        return Reception(
            message=message,
            snr_db=float(10 * np.log10(ratio / self._energy_ratio_per_snr)),
            frequency_offset_hz=signal.first_tone_hz - mfsk.FIRST_TONE_HZ,
            sync_score=signal.score,
        )

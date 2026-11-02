"""An M-FSK modem that works with any error-correcting code.

8-FSK of the Preset it is built for (standard by default), a fixed-size Frame protected by a
CRC-32 and by the code given at construction, decoded from soft values, and a known 32-symbol
preamble that the receiver looks for at every start time and audio frequency. Modems that
differ only by their code come from here, so a difference in their Success threshold is the
code's.

The Preset (see `presets`) sets the tones, the symbol duration and the interleaving; any of them
can be overridden by hand, and the coded bits can be sent several times (`repetitions`); the
bench sweeps these.
"""

import math

import numpy as np

from vibemodem.core import mfsk, presets
from vibemodem.core.code import Code
from vibemodem.core.coded_modem import NOISE_BANDWIDTH_HZ, CodedModem
from vibemodem.core.modem import Reception
from vibemodem.core.presets import DEFAULT_PRESET

SAMPLE_RATE = mfsk.SAMPLE_RATE
MIN_SIGNALS = 3  # a recording of one Frame still looks for a few, as the search always did


class CodedMfskModem(CodedModem):
    """The modem that sends its coded bits as M-FSK symbols."""

    def __init__(
        self,
        code: Code,
        *,
        preset: str = DEFAULT_PRESET,
        first_tone_hz: float = mfsk.FIRST_TONE_HZ,
        tones: int | None = None,
        symbol_ms: float | None = None,
        interleave: bool | None = None,
        repetitions: int = 1,
    ):
        chosen = presets.profile(preset)
        tones = chosen.tones if tones is None else tones
        symbol_ms = chosen.symbol_ms if symbol_ms is None else symbol_ms
        interleave = chosen.interleave if interleave is None else interleave
        super().__init__(code, preset=preset, interleave=interleave, repetitions=repetitions)
        self.waveform = mfsk.Waveform(
            tones=tones, symbol_seconds=symbol_ms / 1000, first_tone_hz=first_tone_hz
        )
        self._data_symbols = math.ceil(self._sent_bits / self.waveform.bits_per_symbol)
        # How the energy ratio at a tone becomes an SNR: the noise of the reference bandwidth
        # over one symbol.
        self._energy_ratio_per_snr = self.waveform.symbol_seconds * NOISE_BANDWIDTH_HZ

    @property
    def parameters(self) -> dict:
        """What a result file records so the waveform that was measured can be told apart."""
        return {
            "preset": self.preset,
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
        # A Transmission is a Frame after another, each with its own Preamble: look for as many
        # Signals as Frames that would fill the recording, and a couple more.
        found = self.waveform.find_signals(
            samples, max_candidates=max(MIN_SIGNALS, samples.size // self.frame_samples() + 2)
        )
        return [self.waveform.refine(samples, candidate) for candidate in found]

    def frame_samples(self) -> int:
        return (mfsk.PREAMBLE_SYMBOLS + self._data_symbols) * self.waveform.samples_per_symbol

    def _same_signal_samples(self) -> int:
        return self.waveform.samples_per_symbol  # a symbol: the refined start is much finer

    def _decode(self, samples: np.ndarray, signal: mfsk.Candidate) -> Reception | None:
        waveform = self.waveform
        size = waveform.samples_per_symbol
        first_data_sample = signal.start_sample + mfsk.PREAMBLE_SYMBOLS * size
        if not self._fits(samples, signal):
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
            start_sample=signal.start_sample,
        )

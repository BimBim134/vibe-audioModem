"""A GFSK modem that works with any error-correcting code.

One coded bit per symbol, a known preamble that the receiver looks for at every start time and
audio frequency, and a fixed-size Frame protected by a CRC-32 and by the code given at
construction, decoded from soft values. Baud rate, modulation index and Gaussian filter can be
changed, and the coded bits can be interleaved and repeated as for the M-FSK modem, so the bench
measures both on the same footing.
"""

import numpy as np

from vibemodem.core import gfsk
from vibemodem.core.code import Code
from vibemodem.core.coded_modem import NOISE_BANDWIDTH_HZ, CodedModem
from vibemodem.core.modem import Reception


class CodedGfskModem(CodedModem):
    """The modem that sends its coded bits as GFSK."""

    def __init__(
        self,
        code: Code,
        *,
        baud: int = 50,
        h: float = 0.5,
        bt: float | None = 0.5,
        interleave: bool = False,
        repetitions: int = 1,
    ):
        super().__init__(code, interleave=interleave, repetitions=repetitions)
        self.waveform = gfsk.Waveform(baud=baud, h=h, bt=bt)
        # How the energy ratio at a bit's frequency becomes an SNR: the noise of the reference
        # bandwidth over one bit.
        self._energy_ratio_per_snr = NOISE_BANDWIDTH_HZ / baud

    @property
    def parameters(self) -> dict:
        """What a result file records so the waveform that was measured can be told apart."""
        return {
            "baud": self.waveform.baud,
            "h": self.waveform.h,
            "bt": self.waveform.bt,
            "interleave": self._interleave,
            "repetitions": self._repetitions,
        }

    def _audio(self, message: bytes) -> np.ndarray:
        bits = np.concatenate([self.waveform.preamble_bits, self._sent_stream(message)])
        return self.waveform.synthesize(bits)

    def _find(self, samples: np.ndarray) -> list[gfsk.Candidate]:
        work = self.waveform.decimate(samples)
        return [self.waveform.refine(work, c) for c in self.waveform.find_signals(work)]

    def _decode(self, samples: np.ndarray, signal: gfsk.Candidate) -> Reception | None:
        waveform = self.waveform
        work = waveform.decimate(samples)
        start = signal.start_sample // 8 + waveform.preamble_bits.size * waveform._work_bit
        if start + self._sent_bits * waveform._work_bit > work.size:
            return None
        energy = waveform.bit_energies(work, start, signal.carrier_hz, self._sent_bits)
        noise = waveform.noise_energy(work, start, signal.carrier_hz, self._sent_bits)
        if not noise > 0:  # nowhere in the band to read noise (a Signal filling it)
            noise = np.quantile(energy, 0.25) / np.log(2)
        relative = energy / max(noise, 1e-9 * energy.max() + 1e-300)

        message = self._message(relative[:, 0] - relative[:, 1])
        if message is None:
            return None

        sent = self._sent_stream(message).astype(int)
        ratio = max(relative[np.arange(sent.size), sent].mean() - 1.0, 1e-6)
        return Reception(
            message=message,
            snr_db=float(10 * np.log10(ratio / self._energy_ratio_per_snr)),
            frequency_offset_hz=signal.carrier_hz - gfsk.CARRIER_HZ,
            sync_score=signal.score,
        )

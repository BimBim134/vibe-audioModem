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

from vibemodem.core import frame, mfsk
from vibemodem.core.code import Code
from vibemodem.core.modem import Reception

PRESET = "standard"
SAMPLE_RATE = mfsk.SAMPLE_RATE
NOISE_BANDWIDTH_HZ = 2500  # the reference bandwidth in which SNRs are quoted
# The search keeps a few arrays of (windows x frequencies) numbers; this bounds their size.
MAX_RECORDING_SECONDS = 600
MAX_REPETITIONS = 8
_GOLDEN_RATIO_FRACTION = (math.sqrt(5) - 1) / 2


def _send_order(count: int, copy: int, interleave: bool) -> np.ndarray:
    """For each position of one copy of the coded bits as sent, which coded bit goes there.

    Without interleaving, the order of the code. With it, position j carries bit
    (j * stride) mod count, the stride being a share of `count` close to a golden-ratio multiple
    (so that bits sent next to each other are far apart in the code word, and any run of
    positions is spread evenly over it), and a different stride for each copy.
    """
    if not interleave:
        return np.arange(count)
    stride = max(1, round(count * ((copy + 1) * _GOLDEN_RATIO_FRACTION % 1)))
    while math.gcd(stride, count) != 1:
        stride += 1
    return (np.arange(count) * stride) % count


class CodedMfskModem:
    """Sends one Message per Transmission; receives every Message found in a recording.

    Receptions of the same Message (a repeated Transmission) are merged into one.
    """

    def __init__(
        self,
        code: Code,
        *,
        tones: int = 8,
        symbol_ms: float = 80.0,
        interleave: bool = False,
        repetitions: int = 1,
    ):
        if code.info_bits != frame.FRAME_BITS:
            raise ValueError(f"the code must take a Frame of {frame.FRAME_BITS} bits")
        if not isinstance(repetitions, int) or not 1 <= repetitions <= MAX_REPETITIONS:
            raise ValueError(f"repetitions must be a whole number from 1 to {MAX_REPETITIONS}")
        if not isinstance(interleave, bool):
            raise ValueError("interleave must be true or false")
        self.code = code
        self.waveform = mfsk.Waveform(tones=tones, symbol_seconds=symbol_ms / 1000)
        self._interleave = interleave
        self._repetitions = repetitions
        self._sent_bits = repetitions * code.coded_bits
        self._data_symbols = math.ceil(self._sent_bits / self.waveform.bits_per_symbol)
        self._orders = [
            _send_order(code.coded_bits, copy, interleave) for copy in range(repetitions)
        ]
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
        coded = self.code.encode(frame.encode_frame(message))
        sent = np.concatenate([coded[order] for order in self._orders])
        bits_per_symbol = self.waveform.bits_per_symbol
        padding = np.zeros(self._data_symbols * bits_per_symbol - sent.size, dtype=np.uint8)
        symbols = np.concatenate([sent, padding]).reshape(self._data_symbols, -1)
        return symbols @ self.waveform.bit_weights

    def _combine(self, soft_sent: np.ndarray) -> np.ndarray:
        """The soft value of each coded bit: its copies, put back in place, added up."""
        coded = self.code.coded_bits
        combined = np.zeros(coded)
        for copy, order in enumerate(self._orders):
            combined[order] += soft_sent[copy * coded : (copy + 1) * coded]
        return combined

    def modulate(self, message: bytes, preset: str) -> np.ndarray:
        if preset != PRESET:
            raise ValueError(f"unknown Preset {preset!r}: this modem only has {PRESET!r}")
        tones = np.concatenate([self.waveform.preamble_tones, self._data_tones(message)])
        return self.waveform.synthesize(tones)

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
        for candidate in self.waveform.find_signals(samples):
            reception = self._decode(samples, self.waveform.refine(samples, candidate))
            if reception and (
                reception.message not in received
                or reception.sync_score > received[reception.message].sync_score
            ):
                received[reception.message] = reception
        return sorted(received.values(), key=lambda r: -r.sync_score)

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

        decoded = self.code.decode(self._combine(self._soft_bits(relative)[: self._sent_bits]))
        message = None if decoded is None else frame.decode_frame(decoded)
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

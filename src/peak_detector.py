import time
import sys
import logging

import numpy as np
from gnuradio import gr, audio, blocks, fft
from gnuradio.fft import window
from scipy.signal import find_peaks

from config import SignalConfig
from config import DEFAULT_SIGNAL_CONFIG

logging.basicConfig(format="%(levelname)s: %(module)s: %(message)s", level=logging.DEBUG)


class FrequencyListener(gr.top_block):
    def __init__(self, samp_rate: int, fft_size: int):
        """main FrequencyListtenner class. Its purpose is to compute fft from audio source.

        Args:
            samp_rate (int): sample rate
            fft_size (int): fft size
        """
        gr.top_block.__init__(self, "Frequency Listener")
        logging.info("FrequencyListener class instanciated")

        # variables
        self.fft_size = fft_size
        self.samp_rate = samp_rate

        # blocks
        self.audio_src = audio.source(self.samp_rate, "", True)
        self.stream_to_vec = blocks.stream_to_vector(gr.sizeof_float, self.fft_size)
        self.window = window.blackmanharris(self.fft_size)
        self.fft = fft.fft_vfc(self.fft_size, True, self.window, False, 1)
        self.to_mag = blocks.complex_to_mag(self.fft_size)
        self.probe = blocks.probe_signal_vf(self.fft_size)

        # Connections
        self.connect(self.audio_src, self.stream_to_vec)
        self.connect(self.stream_to_vec, self.fft)
        self.connect(self.fft, self.to_mag)
        self.connect(self.to_mag, self.probe)


def wait_for_beep(sig: SignalConfig, fft_size: int = 2048) -> np.float64:
    """listen to audio source, finds the most proeminent frequency peak and output its frequency.

    Args:
        sig (SignalConfig): signal configuration. Only used for sample rate.
        fft_size (int, optional): fft size. Defaults to 2048.

    Returns:
        float: frequency (Hz)
    """
    tb = FrequencyListener(sig.samp_rate, fft_size)
    tb.start()
    logging.info("FrequencyListener started")

    found_freq = None
    try:
        while True:
            raw_spectrum = np.array(tb.probe.level())
            positive_spectrum = raw_spectrum[: fft_size // 2]
            positive_spectrum[0] = 0
            peaks, properties = find_peaks(
                positive_spectrum, height=5.0, prominence=4.0, width=(1, 10)
            )

            if len(peaks) > 0:
                best_peak_idx = peaks[np.argmax(properties["prominences"])]
                found_freq = float(best_peak_idx * (sig.samp_rate / fft_size))
                if 500 < found_freq < 15000:
                    logging.info(f"frequency peak found at {found_freq:2f} Hz")
                    break

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        tb.stop()
        tb.wait()
        del tb  # Libération de la carte son
        logging.info("FrequencyListener instance deleted")

    return found_freq

logging.info("peak_detector module loaded")

if __name__ == "__main__":
    freq = wait_for_beep(DEFAULT_SIGNAL_CONFIG)
    if freq:
        print(f"incomming transmission at {freq} Hz !")

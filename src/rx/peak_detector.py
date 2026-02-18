import time
import sys
import logging

import numpy as np
from scipy.signal import find_peaks
import zmq

from src.config import SignalConfig
from src.config import DEFAULT_SIGNAL_CONFIG

logging.basicConfig(format="%(levelname)s: %(module)s: %(message)s", level=logging.DEBUG)

def search_for_incomming_transmission(
        zmq_port: int = 5555,
        fft_size: int = 2048,
        sig: SignalConfig = DEFAULT_SIGNAL_CONFIG
    ):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{zmq_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    logging.info(f"peak detector subscribed to fft on port {zmq_port}")

    try:
        while True:
            msg = socket.recv()
            data = np.frombuffer(msg, dtype=np.float32)

            if data.size != fft_size:
                continue

            half_size = fft_size // 2
            real_spectrum = data[half_size:]

            peaks, properties = find_peaks(real_spectrum, height=0.5, distance=20)

            freq_resolution = sig.samp_rate / fft_size
            peak_freqs = peaks * freq_resolution
            peak_amps = properties['peak_heights']

            if len(peak_freqs) > 0:
                logging.debug(f"peak detected at {peak_freqs} Hz, {peak_amps}")



    except KeyboardInterrupt:
        socket.close()
        context.term()

logging.info("peak_detector module loaded")

if __name__ == "__main__":
    pass

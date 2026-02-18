import time
import sys
import logging

import numpy as np
from scipy.signal import find_peaks
import zmq

from src.config import SignalConfig, PortsConfig
from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG

logging.basicConfig(format="%(levelname)s: %(processName)s - %(process)d: %(module)s: %(message)s", level=logging.DEBUG)

def search_for_incomming_transmission(
        ports: PortsConfig = DEFAULT_PORTS_CONFIG,
        sig: SignalConfig = DEFAULT_SIGNAL_CONFIG
    ):
    logging.info("search_for_incomming_transmission function started")
    logging.info(ports)
    logging.info(sig)
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{ports.fft_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    logging.info(f"peak detector subscribed to fft on port {ports.fft_port}")

    try:
        while True:
            msg = socket.recv()
            data = np.frombuffer(msg, dtype=np.float32)

            if data.size != ports.fft_size:
                continue

            half_size = ports.fft_size // 2
            real_spectrum = data[half_size:]

            peaks, properties = find_peaks(real_spectrum, height=0.5, distance=20)

            freq_resolution = sig.samp_rate / ports.fft_size
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

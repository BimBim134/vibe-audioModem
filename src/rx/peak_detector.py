import time
import sys
import logging
import multiprocessing

import numpy as np
from scipy.signal import find_peaks
import zmq

from src.config import SignalConfig, PortsConfig
from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG

logging.basicConfig(format="%(asctime)s: %(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)


def search_for_incomming_transmission(
        ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
        signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
        stop_event = None
    ):
    logging.info("search_for_incomming_transmission function started")
    logging.info(ports_conf)
    logging.info(signal_conf)
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{ports_conf.fft_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    
    # Set timeout for recv() to allow checking stop_event
    socket.setsockopt(zmq.RCVTIMEO, 500) 
    
    logging.info(f"peak detector subscribed to fft on port {ports_conf.fft_port}")

    half_size = ports_conf.fft_size // 2
    freq_resolution = signal_conf.samp_rate / ports_conf.fft_size

    try:
        active_demodulators = {}
        
        while stop_event is None or not stop_event.is_set():
            try:
                msg = socket.recv()
            except zmq.Again:
                continue
                
            # Cleanup old or finished processes
            dead_freqs = []
            for freq, p in active_demodulators.items():
                if not p.is_alive():
                    dead_freqs.append(freq)
                    
            for freq in dead_freqs:
                del active_demodulators[freq]
                logging.debug("Demodulator for %s Hz finished and removed from tracking.", freq)
                
            data = np.frombuffer(msg, dtype=np.float32)

            if data.size != ports_conf.fft_size:
                continue

            real_spectrum = data[half_size:]

            peaks, properties = find_peaks(real_spectrum, distance=int(signal_conf.baudrate*freq_resolution), prominence=0.2)

            peak_freqs = peaks * freq_resolution
            peak_amps = properties['prominences']

            if len(peak_freqs) > 0:
                for pf, pa in zip(peak_freqs, peak_amps):
                    if pf > 200:
                        
                        # Debounce check: see if a demodulator is already running near this frequency (tolerance = sig.baudrate)
                        is_running = False
                        for active_freq in list(active_demodulators.keys()):
                            # A DQPSK signal stretches across its baudrate (e.g., 500Hz), so we use that as our tolerance band.
                            if abs(pf - active_freq) < signal_conf.baudrate:
                                is_running = True
                                break
                                
                        if not is_running:
                            logging.info("Transmission detected at %.2f Hz, with prominence %.2f. Launching Demodulator...", pf, pa)
                            from src.rx.demodulator import launch_demodulator # Import here to avoid circular dependencies if any
                            
                            # Allocate a new port so multiple demodulators don't crash
                            assigned_port = ports_conf.raw_packets_port + len(active_demodulators) + 1
                            
                            p = multiprocessing.Process(
                                target=launch_demodulator,
                                kwargs={
                                    "sig": signal_conf,
                                    "carrier_frequency": pf,
                                    "ports": ports_conf,
                                },
                                name=f"Demodulator_{int(pf)}Hz"
                            )
                            p.start()
                            active_demodulators[pf] = p

    except KeyboardInterrupt:
        logging.info("Peak detector: KeyboardInterrupt received")
    finally:
        logging.info("Peak detector: closing socket and context")
        socket.close()
        context.term()
        
        if 'active_demodulators' in locals():
            for freq, p in active_demodulators.items():
                if p.is_alive():
                    logging.info("Terminating active demodulator at %s Hz...", freq)
                    p.terminate()
                    p.join()


if __name__ == "__main__":
    pass

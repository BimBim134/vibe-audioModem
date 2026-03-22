import time
import sys
import logging
import multiprocessing
import copy
import os
from collections import deque

import numpy as np
from scipy.signal import find_peaks
import zmq
import pmt

from src.config import SignalConfig, PortsConfig, PacketConfig
from src.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
    DEFAULT_DQPSK_CONST,
)
from src.rx.demodulator import launch_demodulator

logger = logging.getLogger(__name__)


class DemodulatorWorker:
    """Helper to manage a persistent demodulator process."""

    def __init__(self, worker_id, sig_conf, ports_conf, pkt_conf, constellation):
        self.worker_id = worker_id
        self.command_queue = multiprocessing.Queue()
        self.status_queue = multiprocessing.Queue()

        self.process = multiprocessing.Process(
            target=launch_demodulator,
            kwargs={
                "sig": sig_conf,
                "ports": ports_conf,
                "pkt": pkt_conf,
                "constellation": None,  # Pass None to avoid pickling GNU Radio objects
                "command_queue": self.command_queue,
                "status_queue": self.status_queue,
            },
            name=f"DemodulatorWorker_{worker_id}",
        )
        self.process.start()
        self.active_freq = None
        self.state = "initializing"  # initializing, ready, running
        self.missed_frames = 0

    def start_tuning(self, freq, preset, system_pub_socket=None):
        self.active_freq = freq
        self.state = "running"
        self.missed_frames = 0
        self.command_queue.put({"action": "start", "freq": freq, "preset": preset})
        if system_pub_socket:
            try:
                msg = {
                    "type": "system",
                    "status": "dispatching",
                    "frequency": freq,
                    "worker_id": self.worker_id,
                }
                system_pub_socket.send(pmt.serialize_str(pmt.to_pmt(msg)))
            except Exception as e:
                logger.error(f"Failed to send dispatching message: {e}")

    def stop_tuning(self):
        logger.info(
            "Stopping worker %d (was at %.2f Hz)", self.worker_id, self.active_freq
        )
        self.active_freq = None
        self.state = "ready"
        self.command_queue.put({"action": "stop"})

    def update_state(self):
        """Drain status queue to update internal state."""
        while not self.status_queue.empty():
            try:
                status = self.status_queue.get_nowait()
                if status.get("status") == "ready":
                    self.state = "ready"
                elif status.get("status") == "running":
                    self.state = "running"
            except:
                break

    def terminate(self):
        self.command_queue.put(None)
        self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()


def search_for_incomming_transmission(
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    constellation=DEFAULT_DQPSK_CONST,
    stop_event=multiprocessing.Event(),
    nb_workers: int = 2,
    persistence: int = 50,
    fft_buffer_size: int = 10,
    min_prominence: float = 2.0,
):
    logger.info("search_for_incomming_transmission function started")
    logger.info("Ports: %s", ports_conf)
    logger.info("Signal: %s", signal_conf)
    logger.info("Nb Workers: %d", nb_workers)

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{ports_conf.fft_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    config_socket = context.socket(zmq.SUB)
    config_socket.connect(f"tcp://127.0.0.1:{ports_conf.config_port}")
    config_socket.setsockopt(zmq.SUBSCRIBE, b"PRESET:")

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    logger.info(f"peak detector subscribed to fft on port {ports_conf.fft_port}")

    # Socket for sending system messages to web UI
    system_pub_socket = context.socket(zmq.PUB)
    system_pub_socket.bind(f"tcp://*:{ports_conf.peak_detector_system_port}")
    logger.info(f"peak detector publishing system messages on port {ports_conf.peak_detector_system_port}")

    half_size = ports_conf.fft_size // 2
    freq_resolution = signal_conf.samp_rate / ports_conf.fft_size

    # Pre-spawn workers
    logger.info("Pre-spawning %d demodulator workers...", nb_workers)
    workers = []
    for i in range(nb_workers):
        # Assign unique constellation port for each worker
        worker_ports = copy.copy(ports_conf)
        worker_ports.constellation_port = ports_conf.constellation_port + i
        workers.append(DemodulatorWorker(i, signal_conf, worker_ports, pkt_conf, constellation))

    fft_buffer = deque(maxlen=fft_buffer_size)

    try:
        while not stop_event.is_set():
            socks = dict(poller.poll(100))

            if config_socket in socks and socks[config_socket] == zmq.POLLIN:
                try:
                    config_msg = config_socket.recv_string(flags=zmq.NOBLOCK)
                    if config_msg.startswith("PRESET:"):
                        preset_name = config_msg.split(":")[1]
                        from src.config import MODULATION_PRESETS
                        if preset_name in MODULATION_PRESETS:
                            signal_conf.modulation_preset = preset_name
                            signal_conf.baudrate = MODULATION_PRESETS[preset_name].baudrate
                            logger.info(f"Peak detector config updated to {preset_name}")
                except zmq.Again:
                    pass

            if socket not in socks or socks[socket] != zmq.POLLIN:
                continue

            try:
                msg = socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                continue

            data = np.frombuffer(msg, dtype=np.float32)
            if data.size != ports_conf.fft_size:
                continue

            real_spectrum = data[half_size:]
            fft_buffer.append(real_spectrum)
            
            avg_spectrum = np.mean(fft_buffer, axis=0)

            peaks, properties = find_peaks(
                avg_spectrum,
                distance=max(1, int(signal_conf.baudrate / freq_resolution)),
                prominence=min_prominence,
            )

            peak_freqs = peaks * freq_resolution
            # peak_amps = properties["prominences"]

            # 1. Update existing running workers state and check for signal loss
            for worker in workers:
                worker.update_state()
                if worker.state == "running":
                    found = False
                    bandwidth = signal_conf.baudrate  # the bandwidth roughly equals the baudrate for BPSK/DQPSK
                    for pf in peak_freqs:
                        if abs(pf - worker.active_freq) <= bandwidth / 2:
                            found = True
                            worker.missed_frames = 0
                            break
                    if not found:
                        worker.missed_frames += 1
                        if worker.missed_frames > persistence:
                            worker.stop_tuning()

            # 2. Check detected peaks and dispatch to idle workers
            if len(peak_freqs) > 0:
                for pf in peak_freqs:
                    if pf <= 1000:
                        continue

                    # Check if any worker is already handling this freq (within bandwidth)
                    already_handled = False
                    bandwidth = signal_conf.baudrate
                    for worker in workers:
                        if (
                            worker.state == "running"
                            and abs(pf - worker.active_freq) <= bandwidth / 2
                        ):
                            already_handled = True
                            break

                    if not already_handled:
                        # Find an idle worker
                        for worker in workers:
                            if worker.state == "ready":
                                logger.info(
                                    "Transmission detected at %.2f Hz. Dispatching to worker %d",
                                    pf,
                                    worker.worker_id,
                                )
                                worker.start_tuning(pf, signal_conf.modulation_preset, system_pub_socket)
                                break

    except KeyboardInterrupt:
        logger.info("Peak detector: KeyboardInterrupt received")
    finally:
        logger.info("Peak detector: cleaning up workers...")
        for worker in workers:
            worker.terminate()
        logger.info("Peak detector: closing socket and context")
        config_socket.close()
        socket.close()
        system_pub_socket.close()
        context.term()


if __name__ == "__main__":
    pass

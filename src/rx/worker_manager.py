import logging
import multiprocessing
import copy
import pmt
import zmq

from src.rx.demodulator import launch_demodulator

logger = logging.getLogger(__name__)

class DemodulatorWorker:
    """Helper to manage a persistent demodulator process."""

    def __init__(self, worker_id, sig_conf, ports_conf, pkt_conf):
        self.worker_id = worker_id
        self.command_queue = multiprocessing.Queue()
        self.status_queue = multiprocessing.Queue()

        self.process = multiprocessing.Process(
            target=launch_demodulator,
            kwargs={
                "sig": sig_conf,
                "ports": ports_conf,
                "pkt": pkt_conf,
                "command_queue": self.command_queue,
                "status_queue": self.status_queue,
            },
            name=f"DemodulatorWorker_{worker_id}",
        )
        self.process.start()
        self.active_freq = None
        self.state = "initializing"  # initializing, ready, running
        self.missed_frames = 0

    def start_tuning(self, freq, system_pub_socket=None):
        self.active_freq = freq
        self.state = "running"
        self.missed_frames = 0
        self.command_queue.put({"action": "start", "freq": freq})
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

    def update_preset(self, sig_conf):
        """Send preset update command to worker."""
        self.command_queue.put({
            "action": "update_preset",
            "baudrate": sig_conf.baudrate,
            "beeper_duration": sig_conf.beeper_duration,
            "carrier_freq": sig_conf.carrier_freq,
        })
        logger.info(f"Sent config update to worker {self.worker_id}: baudrate={sig_conf.baudrate}, freq={sig_conf.carrier_freq}")

    def terminate(self):
        self.command_queue.put(None)
        self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()


class WorkerManager:
    """Manages a pool of DemodulatorWorker instances."""

    def __init__(self, nb_workers, signal_conf, ports_conf, pkt_conf, system_pub_socket=None):
        self.nb_workers = nb_workers
        self.system_pub_socket = system_pub_socket
        self.workers = []
        
        logger.info("Pre-spawning %d demodulator workers...", nb_workers)
        for i in range(nb_workers):
            worker_ports = copy.copy(ports_conf)
            self.workers.append(DemodulatorWorker(i, signal_conf, worker_ports, pkt_conf))

    def update_worker_states(self, detected_freqs, baudrate, persistence_threshold):
        """Update running workers and stop those that lost signal."""
        for worker in self.workers:
            worker.update_state()
            if worker.state == "running":
                found = False
                bandwidth = baudrate
                for pf in detected_freqs:
                    if abs(pf - worker.active_freq) <= bandwidth / 2:
                        found = True
                        worker.missed_frames = 0
                        break
                if not found:
                    worker.missed_frames += 1
                    if worker.missed_frames > persistence_threshold:
                        worker.stop_tuning()

    def dispatch_peaks(self, detected_freqs, baudrate):
        """Dispatch detected peaks to idle workers."""
        for pf in detected_freqs:
            if pf <= 1000: # Ignore low frequencies
                continue

            # Check if any worker is already handling this freq (within bandwidth)
            already_handled = False
            bandwidth = baudrate
            for worker in self.workers:
                if (
                    worker.state == "running"
                    and abs(pf - worker.active_freq) <= bandwidth / 2
                ):
                    already_handled = True
                    break

            if not already_handled:
                # Find an idle worker
                for worker in self.workers:
                    if worker.state == "ready":
                        logger.info(
                            "Transmission detected at %.2f Hz. Dispatching to worker %d",
                            pf,
                            worker.worker_id,
                        )
                        worker.start_tuning(pf, self.system_pub_socket)
                        break

    def update_all_presets(self, signal_conf):
        """Propagate configuration updates to all workers."""
        for worker in self.workers:
            worker.update_preset(signal_conf)

    def terminate_all(self):
        """Gracefully shutdown all worker processes."""
        for worker in self.workers:
            worker.terminate()

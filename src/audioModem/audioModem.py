import os
import multiprocessing
import logging
import time
import threading
import json
import queue
from copy import deepcopy
from typing import Optional, Dict, Any
import zmq
import pmt

from src.misc.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
    SignalConfig,
    PortsConfig,
    PacketConfig,
)
from src.rx.audio_interface import start_audio_interface
from src.rx.peak_detector import search_for_incomming_transmission
from src.rx.packet_decoding import listen_for_packets
from src.tx.transmitter import send_data
from src.audioModem.http_server import run_http_server, set_controller

logger = logging.getLogger(__name__)

STOP_EVENT = multiprocessing.Event()
INTERNAL_STOP_EVENT = threading.Event()




class ModemController:
    def __init__(
        self,
        signal_conf: Optional[SignalConfig] = None,
        pkt_conf: Optional[PacketConfig] = None,
        ports_conf: Optional[PortsConfig] = None,
        presets_path: Optional[str] = None,
        test_mode: bool = False,
    ):
        self.signal_conf = deepcopy(signal_conf or DEFAULT_SIGNAL_CONFIG)
        self.pkt_conf = pkt_conf or DEFAULT_PACKET_CONFIG
        self.ports_conf = ports_conf or DEFAULT_PORTS_CONFIG
        self.presets_path = presets_path
        self.test_mode = test_mode
        self.receiver_active = False
        self.receiver_nb_workers = 1
        self.receiver_processes = []

        self._transmission_queue = queue.Queue()
        self._is_transmitting = False
        self._transmission_thread = None
        self._transmission_lock = threading.Lock()
        self._cancel_event = threading.Event()

        self._received_messages = queue.Queue()
        self._messages_lock = threading.Lock()

        self.context = zmq.Context()
        self.config_pub_socket = self.context.socket(zmq.PUB)
        self.config_pub_socket.bind(f"tcp://*:{self.ports_conf.config_port}")

        self._messages_sub_socket = self.context.socket(zmq.SUB)
        self._messages_sub_socket.connect(f"tcp://localhost:{self.ports_conf.messages_port}")
        self._messages_sub_socket.setsockopt(zmq.SUBSCRIBE, b"")

        self._message_listener_thread = None

        logger.info("ModemController initialized")
        logger.info(f"Config pub port: {self.ports_conf.config_port}")
        logger.info(f"Subscribing to messages on port {self.ports_conf.messages_port}")

        self._message_listener_thread = threading.Thread(
            target=self._listen_for_messages,
            daemon=True,
            name="MessageListener"
        )
        self._message_listener_thread.start()

    def _restart_zmq_sockets(self):
        """Restart ZMQ sockets with current ports config."""
        self.config_pub_socket.close()
        self._messages_sub_socket.close()
        self.config_pub_socket = self.context.socket(zmq.PUB)
        self.config_pub_socket.bind(f"tcp://*:{self.ports_conf.config_port}")
        self._messages_sub_socket = self.context.socket(zmq.SUB)
        self._messages_sub_socket.connect(f"tcp://localhost:{self.ports_conf.messages_port}")
        self._messages_sub_socket.setsockopt(zmq.SUBSCRIBE, b"")
        logger.info(f"Restarted ZMQ sockets. Config pub port: {self.ports_conf.config_port}, Messages sub port: {self.ports_conf.messages_port}")

    def _stop_receiver_processes(self):
        """Stop all active receiver processes."""
        if not self.receiver_active:
            return
        logger.info("Stopping receiver processes...")
        STOP_EVENT.set()
        for p in self.receiver_processes:
            p.join(timeout=2.0)
            if p.is_alive():
                p.terminate()
        self.receiver_processes = []
        if not INTERNAL_STOP_EVENT.is_set():
            STOP_EVENT.clear()
        self.receiver_active = False
        logger.info("Receiver processes stopped.")

    def _start_receiver_processes(self, nb_workers: int = 1, input_file: str = None):
        """Start receiver processes (AudioInterface, PeakDetector, PacketDecoder)."""
        if self.receiver_active:
            self._stop_receiver_processes()
        logger.info(f"Starting receiver processes with {nb_workers} workers...")
        self.receiver_nb_workers = nb_workers
        # AudioInterface
        audio_process = multiprocessing.Process(
            target=start_audio_interface,
            kwargs={
                "signal_conf": self.signal_conf,
                "ports_conf": self.ports_conf,
                "stop_event": STOP_EVENT,
                "input_file": input_file,
            },
            name="AudioInterfaceProcess",
        )
        # PeakDetector with nb_workers
        peak_process = multiprocessing.Process(
            target=search_for_incomming_transmission,
            kwargs={
                "signal_conf": self.signal_conf,
                "ports_conf": self.ports_conf,
                "pkt_conf": self.pkt_conf,
                "stop_event": STOP_EVENT,
                "nb_workers": nb_workers,
            },
            name="PeakDetectorProcess",
        )
        # PacketDecoder
        packet_process = multiprocessing.Process(
            target=listen_for_packets,
            kwargs={
                "pkt_conf": self.pkt_conf,
                "ports_conf": self.ports_conf,
                "stop_event": STOP_EVENT,
            },
            name="PacketDecoderProcess",
        )
        # Start all processes
        for p in [audio_process, peak_process, packet_process]:
            p.start()
            self.receiver_processes.append(p)
        self.receiver_active = True
        logger.info("Receiver processes started.")

    def _load_presets(self) -> Dict[str, Any]:
        if self.presets_path and os.path.exists(self.presets_path):
            try:
                with open(self.presets_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load presets: {e}")
        return {}

    def _listen_for_messages(self):
        logger.info("Message listener thread started")
        while not INTERNAL_STOP_EVENT.is_set():
            try:
                message = self._messages_sub_socket.recv(flags=zmq.NOBLOCK)
                if message:
                    try:
                        data = pmt.to_python(pmt.deserialize_str(message))
                        with self._messages_lock:
                            self._received_messages.put(data)
                        sender = data.get("sender_name", "unknown") if isinstance(data, dict) else "unknown"
                        logger.info(f"Received message from: {sender}")
                    except Exception as e:
                        logger.error(f"Failed to deserialize message: {e}")
            except zmq.Again:
                time.sleep(0.1)
                continue
            except Exception as e:
                logger.error(f"Message listener error: {e}")
                time.sleep(0.1)
        logger.info("Message listener thread stopped")

    def get_received_messages(self) -> list:
        messages = []
        with self._messages_lock:
            while not self._received_messages.empty():
                try:
                    messages.append(self._received_messages.get_nowait())
                except queue.Empty:
                    break
        return messages

    def _broadcast_preset_update(self, preset_name: str):
        msg = {
            "type": "preset_update",
            "preset": preset_name,
            "baudrate": self.signal_conf.baudrate,
            "beeper_duration": self.signal_conf.beeper_duration,
            "constellation_name": self.signal_conf.constellation_name,
        }
        try:
            self.config_pub_socket.send(pmt.serialize_str(pmt.to_pmt(msg)))
            logger.info(f"Broadcast preset update: {preset_name}")
        except Exception as e:
            logger.error(f"Failed to broadcast preset: {e}")

    def _process_transmission_queue(self):
        while not INTERNAL_STOP_EVENT.is_set():
            try:
                if self._cancel_event.is_set():
                    logger.info("Transmission cancelled before processing")
                    with self._transmission_lock:
                        self._is_transmitting = False
                    # Don't break here, wait for next item or None
                
                try:
                    item = self._transmission_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if item is None:
                    break

                if self._cancel_event.is_set():
                    logger.info("Transmission cancelled before processing")
                    with self._transmission_lock:
                        self._is_transmitting = False
                    break

                with self._transmission_lock:
                    self._is_transmitting = True

                message_text = item["message"]
                sender_name = item.get("sender_name", "unknown")

                logger.info(f"Processing transmission: {message_text[:50]}... from {sender_name}")

                try:
                    send_data(
                        message_text,
                        pkt=self.pkt_conf,
                        sig=self.signal_conf,
                        sender_name=sender_name,
                        handle_signals=False,
                        cancel_event=self._cancel_event,
                        output_file=item.get("output_file"),
                        silence_padding=item.get("silence_padding", 0.0),
                    )
                    if self._cancel_event.is_set():
                        logger.info("Transmission cancelled mid-flight")
                    else:
                        logger.info("Transmission completed successfully")
                except Exception as e:
                    logger.error(f"Transmission failed: {e}")

                with self._transmission_lock:
                    self._is_transmitting = False

            except Exception as e:
                logger.error(f"Queue processing error: {e}")

    def _queue_transmission(self, message: str, sender_name: str = "unknown", output_file: str = None, silence_padding: float = 0.0):
        item = {
            "message": message,
            "sender_name": sender_name,
            "output_file": output_file,
            "silence_padding": silence_padding,
        }
        self._transmission_queue.put(item)
        logger.info(f"Transmission queued (queue size: {self._transmission_queue.qsize()})")

        if self._transmission_thread is None or not self._transmission_thread.is_alive():
            self._transmission_thread = threading.Thread(
                target=self._process_transmission_queue,
                daemon=True,
                name="TransmissionWorker"
            )
            self._transmission_thread.start()

    def handle_transmit(self, data: Dict[str, Any]) -> Dict[str, Any]:
        message = data.get("message", "")
        sender_name = data.get("sender_name", "HTTP")
        output_file = "test.wav" if self.test_mode else None
        silence_padding = 10.0 if self.test_mode else 0.0

        if not message:
            return {"status": "error", "error": "Message is required"}

        self._cancel_event.clear()
        self._queue_transmission(message, sender_name, output_file=output_file, silence_padding=silence_padding)

        return {"status": "queued", "message": message, "sender": sender_name}

    def handle_receive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        nb_workers = data.get("nb_workers", 1)
        try:
            nb_workers = int(nb_workers)
        except (ValueError, TypeError):
            return {"status": "error", "error": "nb_workers must be an integer"}
        input_file = "test.wav" if self.test_mode else None
        if input_file and not os.path.exists(input_file):
            return {"status": "error", "error": f"Input file '{input_file}' not found. Send a message first to create it."}
        self._start_receiver_processes(nb_workers, input_file=input_file)
        return {"status": "ok", "receiver_active": True, "nb_workers": nb_workers}

    def handle_setup(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Full modem reset with new config (signal, packet, port)."""
        signal_cfg = data.get("signal", {})
        packet_cfg = data.get("packet", {})
        port_cfg = data.get("port", {})

        # Update signal config
        if "samp_rate" in signal_cfg:
            self.signal_conf.samp_rate = signal_cfg["samp_rate"]
        if "carrier_freq" in signal_cfg:
            self.signal_conf.carrier_freq = float(signal_cfg["carrier_freq"])
        if "baudrate" in signal_cfg:
            self.signal_conf.baudrate = signal_cfg["baudrate"]
        if "beeper_duration" in signal_cfg:
            self.signal_conf.beeper_duration = signal_cfg["beeper_duration"]
        if "constellation_name" in signal_cfg:
            self.signal_conf.constellation_name = signal_cfg["constellation_name"]

        # Update packet config
        if "total_packets_len" in packet_cfg:
            self.pkt_conf.total_packets_len = packet_cfg["total_packets_len"]
        if "preamble_packets" in packet_cfg:
            self.pkt_conf.preamble_packets = packet_cfg["preamble_packets"]
        if "postamble_packets" in packet_cfg:
            self.pkt_conf.postamble_packets = packet_cfg["postamble_packets"]
        if "error_correction_len" in packet_cfg:
            self.pkt_conf.error_correction_len = packet_cfg["error_correction_len"]

        # Update port config (requires ZMQ socket restart)
        ports_changed = False
        if "audio_port" in port_cfg:
            self.ports_conf.audio_port = port_cfg["audio_port"]
            ports_changed = True
        if "fft_port" in port_cfg:
            self.ports_conf.fft_port = port_cfg["fft_port"]
            ports_changed = True
        if "fft_size" in port_cfg:
            self.ports_conf.fft_size = port_cfg["fft_size"]
        if "raw_packets_port" in port_cfg:
            self.ports_conf.raw_packets_port = port_cfg["raw_packets_port"]
        if "messages_port" in port_cfg:
            self.ports_conf.messages_port = port_cfg["messages_port"]
            ports_changed = True
        if "config_port" in port_cfg:
            self.ports_conf.config_port = port_cfg["config_port"]
            ports_changed = True
        if "peak_detector_system_port" in port_cfg:
            self.ports_conf.peak_detector_system_port = port_cfg["peak_detector_system_port"]

        if ports_changed:
            self._restart_zmq_sockets()

        # Restart receiver if active to apply new configs
        if self.receiver_active:
            self._start_receiver_processes(self.receiver_nb_workers)

        return self.handle_get_config()

    def handle_set_preset(self, data: Dict[str, Any]) -> Dict[str, Any]:
        preset_name = data.get("preset")

        if not preset_name:
            return {"status": "error", "error": "Preset name required"}

        presets = self._load_presets()

        if preset_name not in presets:
            return {"status": "error", "error": f"Unknown preset: {preset_name}"}

        preset = presets[preset_name]
        self.signal_conf.baudrate = preset.get("baudrate", self.signal_conf.baudrate)
        self.signal_conf.beeper_duration = preset.get("beeper_duration", self.signal_conf.beeper_duration)
        self.signal_conf.constellation_name = preset.get("constellation", self.signal_conf.constellation_name)

        self._broadcast_preset_update(preset_name)

        return {
            "status": "ok",
            "preset": preset_name,
            "baudrate": self.signal_conf.baudrate,
            "constellation": self.signal_conf.constellation_name,
        }

    def handle_set_carrier_freq(self, data: Dict[str, Any]) -> Dict[str, Any]:
        frequency = data.get("frequency")

        if frequency is None:
            return {"status": "error", "error": "Frequency required"}

        self.signal_conf.carrier_freq = float(frequency)

        return {"status": "ok", "frequency": self.signal_conf.carrier_freq}

    def handle_get_config(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "status": "ok",
            "signal": {
                "samp_rate": self.signal_conf.samp_rate,
                "carrier_freq": self.signal_conf.carrier_freq,
                "baudrate": self.signal_conf.baudrate,
                "beeper_duration": self.signal_conf.beeper_duration,
                "constellation_name": self.signal_conf.constellation_name,
            },
            "packet": {
                "total_packets_len": self.pkt_conf.total_packets_len,
                "preamble_packets": self.pkt_conf.preamble_packets,
                "postamble_packets": self.pkt_conf.postamble_packets,
                "error_correction_len": self.pkt_conf.error_correction_len,
            },
            "port": {
                "audio_port": self.ports_conf.audio_port,
                "fft_port": self.ports_conf.fft_port,
                "fft_size": self.ports_conf.fft_size,
                "raw_packets_port": self.ports_conf.raw_packets_port,
                "messages_port": self.ports_conf.messages_port,
                "config_port": self.ports_conf.config_port,
                "peak_detector_system_port": self.ports_conf.peak_detector_system_port,
            },
        }

    def handle_get_status(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._transmission_lock:
            is_transmitting = self._is_transmitting

        return {
            "status": "ok",
            "is_transmitting": is_transmitting,
            "queue_size": self._transmission_queue.qsize(),
        }

    def cancel_queue(self):
        logger.info("Cancelling transmission queue...")
        self._cancel_event.set()
        while not self._transmission_queue.empty():
            try:
                self._transmission_queue.get_nowait()
            except queue.Empty:
                break
        self._transmission_queue.put(None)
        with self._transmission_lock:
            self._is_transmitting = False

    def handle_cancel_queue(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.cancel_queue()
        return {"status": "cancelled"}

    def handle_stop(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Stop receiver (-rx) and/or transmitter (-tx)."""
        rx = data.get("rx", False)
        tx = data.get("tx", False)
        if isinstance(rx, str):
            rx = rx.lower() in ("true", "1", "yes")
        if isinstance(tx, str):
            tx = tx.lower() in ("true", "1", "yes")

        stopped = []
        if rx:
            self._stop_receiver_processes()
            stopped.append("receiver")
        if tx:
            self.cancel_queue()
            stopped.append("transmitter")
        if not stopped:
            return {"status": "error", "error": "Specify rx=true and/or tx=true"}
        return {"status": "ok", "stopped": stopped}

    def handle_quit(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Trigger full graceful shutdown."""
        logger.info("Quit command received. Signaling shutdown.")
        INTERNAL_STOP_EVENT.set()
        # Set STOP_EVENT in a separate thread to avoid blocking the HTTP response
        # if there's any lock contention with child processes.
        def signal_children():
            try:
                STOP_EVENT.set()
            except Exception as e:
                logger.error(f"Error signaling children: {e}")
        
        threading.Thread(target=signal_children, daemon=True).start()
        return {"status": "stopping"}

    def shutdown(self):
        self._stop_receiver_processes()
        self.cancel_queue()
        if self._transmission_thread and self._transmission_thread.is_alive():
            self._transmission_thread.join(timeout=2.0)

        if self._message_listener_thread and self._message_listener_thread.is_alive():
            self._message_listener_thread.join(timeout=2.0)

        self._messages_sub_socket.close()
        self.config_pub_socket.close()
        self.context.term()

        logger.info("ModemController shutdown complete")


def start_audiomodem(http_port: int = 8000, cli: bool = False, cli_exit_event=None, test_mode: bool = False):
    from src.audioModem.cli import start_cli
    
    logger.info("Starting audio modem...")

    controller = ModemController(test_mode=test_mode)
    set_controller(controller)

    http_thread = threading.Thread(
        target=run_http_server,
        kwargs={"port": http_port, "stop_event": STOP_EVENT},
        daemon=True,
        name="HTTPServer"
    )
    http_thread.start()
    logger.info(f"HTTP server starting on port {http_port}")

    if cli:
        start_cli(base_url="http://localhost:8000", cli_exit_event=cli_exit_event)

    try:
        while not INTERNAL_STOP_EVENT.is_set():
            if cli_exit_event and cli_exit_event.is_set():
                INTERNAL_STOP_EVENT.set()
                break
            time.sleep(0.2)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received in main loop.")
        INTERNAL_STOP_EVENT.set()
    finally:
        logger.info("Starting graceful shutdown sequence...")
        STOP_EVENT.set()
        controller.shutdown()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    start_audiomodem()

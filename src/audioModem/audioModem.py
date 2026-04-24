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


AUDIO_INTERFACE = {
    "target": start_audio_interface,
    "kwargs": {
        "signal_conf": DEFAULT_SIGNAL_CONFIG,
        "ports_conf": DEFAULT_PORTS_CONFIG,
        "stop_event": STOP_EVENT,
    },
    "name": "AudioInterfaceProcess",
}

PEAK_DETECTOR = {
    "target": search_for_incomming_transmission,
    "kwargs": {
        "signal_conf": DEFAULT_SIGNAL_CONFIG,
        "ports_conf": DEFAULT_PORTS_CONFIG,
        "stop_event": STOP_EVENT,
    },
    "name": "PeakDetectorProcess",
}

PACKET_DECODER = {
    "target": listen_for_packets,
    "kwargs": {
        "pkt_conf": DEFAULT_PACKET_CONFIG,
        "ports_conf": DEFAULT_PORTS_CONFIG,
        "stop_event": STOP_EVENT,
    },
    "name": "PacketDecoderProcess",
}

class ModemController:
    def __init__(
        self,
        signal_conf: Optional[SignalConfig] = None,
        pkt_conf: Optional[PacketConfig] = None,
        ports_conf: Optional[PortsConfig] = None,
        presets_path: Optional[str] = None,
    ):
        self.signal_conf = deepcopy(signal_conf or DEFAULT_SIGNAL_CONFIG)
        self.pkt_conf = pkt_conf or DEFAULT_PACKET_CONFIG
        self.ports_conf = ports_conf or DEFAULT_PORTS_CONFIG
        self.presets_path = presets_path

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
        while True:
            try:
                if STOP_EVENT.is_set():
                    break
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
                continue
            except Exception as e:
                logger.error(f"Message listener error: {e}")
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
        while True:
            try:
                if self._cancel_event.is_set():
                    logger.info("Transmission cancelled before processing")
                    with self._transmission_lock:
                        self._is_transmitting = False
                    break

                item = self._transmission_queue.get()
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

    def _queue_transmission(self, message: str, sender_name: str = "unknown"):
        item = {
            "message": message,
            "sender_name": sender_name,
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

        if not message:
            return {"status": "error", "error": "Message is required"}

        self._cancel_event.clear()
        self._queue_transmission(message, sender_name)

        return {"status": "queued", "message": message, "sender": sender_name}

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

    def shutdown(self):
        self.cancel_queue()
        if self._transmission_thread and self._transmission_thread.is_alive():
            self._transmission_thread.join(timeout=2.0)

        if self._message_listener_thread and self._message_listener_thread.is_alive():
            self._message_listener_thread.join(timeout=2.0)

        self._messages_sub_socket.close()
        self.config_pub_socket.close()
        self.context.term()

        logger.info("ModemController shutdown complete")


def start_audiomodem(http_port: int = 8000, cli: bool = False, cli_exit_event=None):
    from src.audioModem.cli import start_cli
    
    logger.info("Starting audio modem...")

    controller = ModemController()
    set_controller(controller)

    http_thread = threading.Thread(
        target=run_http_server,
        kwargs={"port": http_port, "stop_event": STOP_EVENT},
        daemon=True,
        name="HTTPServer"
    )
    http_thread.start()
    logger.info(f"HTTP server starting on port {http_port}")

    process_configs = [
        AUDIO_INTERFACE,
        PEAK_DETECTOR,
        PACKET_DECODER,
    ]

    processes = []
    for config in process_configs:
        p = multiprocessing.Process(
            target=config["target"],
            args=config.get("args", ()),
            kwargs=config.get("kwargs", {}),
            name=config.get("name", "Process"),
        )
        processes.append(p)
        p.start()

    if cli:
        start_cli(base_url="http://localhost:8000", cli_exit_event=cli_exit_event)

    try:
        while all(p.is_alive() for p in processes):
            if cli_exit_event and cli_exit_event.is_set():
                break
            time.sleep(0.2)

        STOP_EVENT.set()
    except KeyboardInterrupt:
        STOP_EVENT.set()
    finally:
        for p in processes:
            p.join(timeout=2.0)
            if p.is_alive():
                p.terminate()

    controller.shutdown()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    start_audiomodem()

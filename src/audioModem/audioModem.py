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

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

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
from src.audioModem.cli import start_cli

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
        cmd_port: int = 5561,
    ):
        self.signal_conf = deepcopy(signal_conf or DEFAULT_SIGNAL_CONFIG)
        self.pkt_conf = pkt_conf or DEFAULT_PACKET_CONFIG
        self.ports_conf = ports_conf or DEFAULT_PORTS_CONFIG
        self.presets_path = presets_path
        self.cmd_port = cmd_port

        self._transmission_queue = queue.Queue()
        self._is_transmitting = False
        self._transmission_thread = None
        self._transmission_lock = threading.Lock()

        self.context = zmq.Context()
        self.command_socket = self.context.socket(zmq.REP)
        self.command_socket.bind(f"tcp://*:{self.cmd_port}")

        self.config_pub_socket = self.context.socket(zmq.PUB)
        self.config_pub_socket.bind(f"tcp://*:{self.ports_conf.config_port}")

        logger.info("ModemController initialized")
        logger.info(f"  Command port: {self.cmd_port}")
        logger.info(f"  Config pub port: {self.ports_conf.config_port}")

    def _load_presets(self) -> Dict[str, Any]:
        if self.presets_path and os.path.exists(self.presets_path):
            try:
                with open(self.presets_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load presets: {e}")
        return {}

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
                item = self._transmission_queue.get()
                if item is None:
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
                    )
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

    def handle_command(self, cmd: Any) -> Dict[str, Any]:
        action = cmd.get("action") if isinstance(cmd, dict) else None

        handlers = {
            "transmit": self.handle_transmit,
            "set_preset": self.handle_set_preset,
            "set_carrier_freq": self.handle_set_carrier_freq,
            "get_config": self.handle_get_config,
            "get_status": self.handle_get_status,
        }

        handler = handlers.get(action) if action else None
        if not handler:
            return {"status": "error", "error": f"Unknown action: {action}"}

        try:
            return handler(cmd)
        except Exception as e:
            logger.error(f"Command handler error: {e}")
            return {"status": "error", "error": str(e)}

    def run_command_loop(self, stop_event):
        poller = zmq.Poller()
        poller.register(self.command_socket, zmq.POLLIN)

        logger.info("Command loop started")

        while not stop_event.is_set():
            try:
                socks = dict(poller.poll(100))

                if self.command_socket in socks and socks[self.command_socket] == zmq.POLLIN:
                    raw_msg = self.command_socket.recv()
                    try:
                        cmd = json.loads(raw_msg.decode("utf-8"))
                        logger.info(f"Received command: {cmd.get('action')}")
                    except json.JSONDecodeError:
                        cmd = pmt.to_python(pmt.deserialize_str(raw_msg))

                    response = self.handle_command(cmd)

                    self.command_socket.send(json.dumps(response).encode("utf-8"))
                    logger.info(f"Sent response: {response.get('status')}")

            except Exception as e:
                logger.error(f"Command loop error: {e}")

        logger.info("Command loop stopped")

    def shutdown(self):
        self._transmission_queue.put(None)
        if self._transmission_thread and self._transmission_thread.is_alive():
            self._transmission_thread.join(timeout=2.0)

        self.command_socket.close()
        self.config_pub_socket.close()
        self.context.term()

        logger.info("ModemController shutdown complete")


app = FastAPI(title="Vibe Audio Modem")
_controller: Optional[ModemController] = None


def set_controller(controller: ModemController):
    global _controller
    _controller = controller


@app.get("/status")
async def get_status():
    return _controller.handle_get_status()


@app.get("/config")
async def get_config():
    return _controller.handle_get_config()


@app.post("/transmit")
async def transmit(request: Request):
    data = await request.json()
    return _controller.handle_transmit(data)


@app.post("/preset")
async def set_preset(request: Request):
    data = await request.json()
    return _controller.handle_set_preset(data)


@app.post("/carrier")
async def set_carrier(request: Request):
    data = await request.json()
    return _controller.handle_set_carrier_freq(data)


def run_http_server(host: str = "0.0.0.0", port: int = 8000, stop_event=None):
    logger.info(f"Starting HTTP server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_processes(process_configs, stop_event, timeout=2.0):
    processes = []

    for config in process_configs:
        p = multiprocessing.Process(
            target=config["target"],
            args=config.get("args", ()),
            kwargs=config.get("kwargs", {}),
            name=config.get("name", "Process"),
        )
        processes.append(p)
        logger.info("Starting process: %s", config.get("name", "Process"))
        p.start()

    try:
        while all(p.is_alive() for p in processes):
            time.sleep(0.2)

        logger.info("A process ended. Signaling remaining processes to stop...")
        stop_event.set()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, signaling processes to stop...")
        stop_event.set()
    finally:
        for p in processes:
            p.join(timeout=timeout)

        for p in processes:
            if p.is_alive():
                logger.warning("%s still alive, terminating...", p.name)
                p.terminate()


def main(http_port: int = 8000, cli: bool = False):
    logger.info("Starting audio modem...")

    controller = ModemController(cmd_port=5561)
    set_controller(controller)

    controller_thread = threading.Thread(
        target=controller.run_command_loop,
        args=(STOP_EVENT,),
        daemon=True,
        name="ModemController"
    )
    controller_thread.start()
    logger.info("ModemController running on port 5561")

    http_thread = threading.Thread(
        target=run_http_server,
        kwargs={"port": http_port, "stop_event": STOP_EVENT},
        daemon=True,
        name="HTTPServer"
    )
    http_thread.start()
    logger.info(f"HTTP server starting on port {http_port}")

    if cli:
        cli_thread = threading.Thread(
            target=start_cli,
            daemon=False,
            name="CLI"
        )
        cli_thread.start()
        cli_thread.join()

    process_configs = [
        AUDIO_INTERFACE,
        PEAK_DETECTOR,
        PACKET_DECODER,
    ]
    run_processes(process_configs, STOP_EVENT)

    controller.shutdown()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()

import multiprocessing
import logging
import time
import argparse

from src.misc.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
)
from src.rx.audio_interface import start_audio_interface
from src.rx.peak_detector import search_for_incomming_transmission
from src.rx.packet_decoding import listen_for_packets
from src.ui.webUI.webUI import start_dashboard

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

WEB_UI = {
    "target": start_dashboard,
    "kwargs": {"stop_event": STOP_EVENT},
    "name": "WebUIProcess",
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


def run_processes(process_configs, stop_event, timeout=2.0):
    """
    Run and manage a list of multiprocessing.Process configurations.

    Args:
        process_configs: List of dicts with 'target', 'args', and 'name'.
        stop_event: multiprocessing.Event used to signal processes to stop.
        timeout: Time in seconds to wait for processes to exit gracefully.
    """
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
        # Keep the main process alive until any process exits or interrupt occurs
        while all(p.is_alive() for p in processes):
            time.sleep(0.2)

        logger.info("A process ended. Signaling remaining processes to stop...")
        stop_event.set()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, signaling processes to stop...")
        stop_event.set()
    finally:
        # Give processes some time to exit gracefully
        for p in processes:
            p.join(timeout=timeout)

        # Force terminate if still alive
        for p in processes:
            if p.is_alive():
                logger.warning("%s still alive, terminating...", p.name)
                p.terminate()


def main():
    process_configs = [
        AUDIO_INTERFACE,
        PEAK_DETECTOR,
        PACKET_DECODER,
    ]
    run_processes(process_configs, STOP_EVENT)

    logger.info("Shutdown complete.")
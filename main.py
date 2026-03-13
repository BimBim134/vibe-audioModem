import multiprocessing
import logging
import time
import argparse

from src.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
)
from src.rx.audio_interface import start_audio_interface
from research.audio_from_file import (
    start_audio_interface as test_audio_interface,
)
from src.rx.peak_detector import search_for_incomming_transmission
from src.rx.packet_decoding import listen_for_packets
from src.UI.webUI.webUI import start_dashboard
from src.UI.pyqt.visual_signal_debugger import run_visual_debugger
from src.UI.pyqt.graphics_app import run_graphics_app

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

AUDIO_INTERFACE_FROM_FILE = {
    "target": test_audio_interface,
    "kwargs": {
        "signal_conf": DEFAULT_SIGNAL_CONFIG,
        "ports_conf": DEFAULT_PORTS_CONFIG,
        "stop_event": STOP_EVENT,
        "file": "research/ultimate_test.wav",
        "start_delay" : 10.0
    },
    "name": "TestAudioInterfaceProcess",
}

WEB_UI = {
    "target": start_dashboard,
    "kwargs": {"stop_event": STOP_EVENT},
    "name": "WebUIProcess",
}

QT_DEBUGGER = {
    "target": run_visual_debugger,
    "name": "qtSignalDebuggerProcess",
}

QT_GRAPHICS_APP = {
    "target": run_graphics_app,
    "kwargs": {
        "signal_conf": DEFAULT_SIGNAL_CONFIG,
        "ports_conf": DEFAULT_PORTS_CONFIG,
    },
    "name": "qtGraphicsAppProcess",
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


def main(test: bool = False, ui: bool = False):
    if ui:
        logger.info("ui mode")
        process_configs = [QT_GRAPHICS_APP]
    else:
        logger.info("test mode: %s", test)

        process_configs = [
            AUDIO_INTERFACE_FROM_FILE if test else AUDIO_INTERFACE,
            # WEB_UI,
            # QT_DEBUGGER,
            QT_GRAPHICS_APP,
            PEAK_DETECTOR,
            PACKET_DECODER,
        ]

    run_processes(process_configs, STOP_EVENT)

    logger.info("Shutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--ui", action="store_true")
    args = parser.parse_args()
    main(test=args.test, ui=args.ui)

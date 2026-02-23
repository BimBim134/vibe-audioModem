import multiprocessing
import logging
import time

from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG, DEFAULT_PACKET_CONFIG
from src.rx.audio_interface import start_audio_interface
# from research.audio_from_file import start_audio_interface
from src.rx.peak_detector import search_for_incomming_transmission
from src.rx.packet_decoding import listen_for_packets
from src.UI.webUI import start_dashboard

logging.basicConfig(format="%(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)

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
            target=config['target'],
            args=config.get('args', ()),
            kwargs=config.get('kwargs', {}),
            name=config.get('name', 'Process')
        )
        processes.append(p)
        p.start()
        
    try:
        # Keep the main process alive until any process exits or interrupt occurs
        while all(p.is_alive() for p in processes):
            time.sleep(0.1)
            
        logging.info("Main: A process ended. Signaling remaining processes to stop...")
        stop_event.set()
            
    except KeyboardInterrupt:
        logging.info("Main: KeyboardInterrupt received, signaling processes to stop...")
        stop_event.set()
    finally:
        # Give processes some time to exit gracefully
        for p in processes:
            p.join(timeout=timeout)
            
        # Force terminate if still alive
        for p in processes:
            if p.is_alive():
                logging.warning("Main: %s still alive, terminating...", p.name)
                p.terminate()

def main():
    stop_event = multiprocessing.Event()
    
    process_configs = [
        {
            "target": start_audio_interface,
            "kwargs": {
                "signal_conf": DEFAULT_SIGNAL_CONFIG,
                "ports_conf": DEFAULT_PORTS_CONFIG,
                "stop_event": stop_event
            },
            "name": "AudioInterfaceProcess"
        },
        #{
        #    "target": search_for_incomming_transmission,
        #    "kwargs": {
        #        "ports": DEFAULT_PORTS_CONFIG,
        #        "sig": DEFAULT_SIGNAL_CONFIG,
        #        "stop_event": stop_event
        #    },
        #    "name": "PeakDetectorProcess"
        #},
        #{
        #    "target": listen_for_packets,
        #    "kwargs": {
        #        "pkt": DEFAULT_PACKET_CONFIG,
        #        "ports": DEFAULT_PORTS_CONFIG,
        #        "stop_event": stop_event
        #    },
        #    "name": "RawPacketDecoderProcess"
        #},
        {
            "target": start_dashboard,
            "kwargs": {
                "ports_conf": DEFAULT_PORTS_CONFIG,
                "signal_conf": DEFAULT_SIGNAL_CONFIG,
                "stop_event": stop_event
            },
            "name": "DashboardProcess"
        },
    ]
    
    run_processes(process_configs, stop_event)
            
    logging.info("Shutdown complete.")

if __name__ == "__main__":
    main()

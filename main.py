import multiprocessing
import logging
import time

from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG
from src.rx.audio_interface import start_audio_interface
from src.rx.peak_detector import search_for_incomming_transmission

logging.basicConfig(format="%(levelname)s: %(processName)s - %(process)d: %(module)s: %(message)s", level=logging.DEBUG)

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
            name=config.get('name', 'Process')
        )
        processes.append(p)
        p.start()
        
    try:
        # Keep the main process alive until processes exit or interrupt
        while any(p.is_alive() for p in processes):
            time.sleep(0.1)
            
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
            "args": (DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG, stop_event),
            "name": "AudioInterfaceProcess"
        },
        {
            "target": search_for_incomming_transmission,
            "args": (DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG, stop_event),
            "name": "PeakDetectorProcess"
        }
    ]
    
    run_processes(process_configs, stop_event)
            
    logging.info("Graceful shutdown complete.")

if __name__ == "__main__":
    main()

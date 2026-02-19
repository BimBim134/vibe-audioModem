import multiprocessing
import logging
import time

from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG
from src.rx.audio_interface import start_audio_interface
from src.rx.peak_detector import search_for_incomming_transmission

logging.basicConfig(format="%(levelname)s: %(processName)s - %(process)d: %(module)s: %(message)s", level=logging.DEBUG)

def main():
    stop_event = multiprocessing.Event()
    
    p1 = multiprocessing.Process(
        target=start_audio_interface, 
        args=(DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG, stop_event),
        name="AudioInterfaceProcess"
    )
    p2 = multiprocessing.Process(
        target=search_for_incomming_transmission, 
        args=(DEFAULT_PORTS_CONFIG, DEFAULT_SIGNAL_CONFIG, stop_event),
        name="PeakDetectorProcess"
    )

    try:
        p1.start()
        p2.start()
        
        # Keep the main process alive until processes exit or interrupt
        while p1.is_alive() or p2.is_alive():
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        logging.info("Main: KeyboardInterrupt received, signaling processes to stop...")
        stop_event.set()
    finally:
        # Give processes some time to exit gracefully
        p1.join(timeout=2)
        p2.join(timeout=2)
        
        # Force terminate if still alive
        if p1.is_alive():
            logging.warning("Main: p1 still alive, terminating...")
            p1.terminate()
        if p2.is_alive():
            logging.warning("Main: p2 still alive, terminating...")
            p2.terminate()
            
    print("Graceful shutdown complete. yeeah")

if __name__ == "__main__":
    main()

from concurrent.futures import ProcessPoolExecutor
import logging

from src.config import DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG
from src.rx.audio_interface import start_audio_interface
from src.rx.peak_detector import search_for_incomming_transmission

logging.basicConfig(format="%(levelname)s: %(processName)s - %(process)d: %(module)s: %(message)s", level=logging.DEBUG)

def main():
    with ProcessPoolExecutor() as executor:
        executor.submit(start_audio_interface, DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG)
        # executor.submit(search_for_incomming_transmission, 5555, 2048, DEFAULT_SIGNAL_CONFIG)
    print("yeeah")

if __name__ == "__main__":
    main()
    pass

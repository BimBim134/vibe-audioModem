from concurrent.futures import ProcessPoolExecutor
import logging

from src.config import DEFAULT_SIGNAL_CONFIG
from src.rx.audio_interface import start_audio_interface
from src.rx.listenner import launch_demodulator

logging.basicConfig(format="%(levelname)s: %(processName)s - %(process)d: %(module)s: %(message)s", level=logging.DEBUG)

def main():
    with ProcessPoolExecutor() as executor:
        executor.submit(start_audio_interface, DEFAULT_SIGNAL_CONFIG, 2048)
        executor.submit(launch_demodulator)
    print("yeeah")

if __name__ == "__main__":
    main()
    pass

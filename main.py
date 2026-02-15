import threading
import time
import sys

from src import receiver, packet2bin, transmitter, config
from src.rx.audio_interface import start_audio_interface

def wait_for_messages() -> None:
    threads = [
        threading.Thread(target=func, daemon=True)
        for func in (
            start_audio_interface(config.DEFAULT_SIGNAL_CONFIG, 2048),
        )
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
            # Optional: Check if threads are still alive
            if not any(t.is_alive() for t in threads):
                break
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)


if __name__ == "__main__":
    wait_for_messages()


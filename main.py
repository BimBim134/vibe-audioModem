import logging
import argparse
import multiprocessing
import threading
import sys

from src.misc.config import setup_logging

setup_logging(level=logging.INFO)

from src.audioModem.audioModem import start_audiomodem

STOP_EVENT = multiprocessing.Event()
CLI_EXIT_EVENT = threading.Event()


def main(http_port: int = 8000, cli: bool = False):
    if cli:
        start_audiomodem(http_port=http_port, cli=cli, cli_exit_event=CLI_EXIT_EVENT)
    else:
        import multiprocessing as mp
        modem_process = mp.Process(
            target=start_audiomodem,
            name="AudioModem",
            kwargs={"cli": False}
        )
        modem_process.start()
        try:
            modem_process.join()
        except KeyboardInterrupt:
            if modem_process.is_alive():
                modem_process.terminate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vibe Audio Modem")
    parser.add_argument("--cli", action="store_true", help="Enable CLI terminal interface")
    args = parser.parse_args()
    main(cli=args.cli)

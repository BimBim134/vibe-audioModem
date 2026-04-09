import logging
import argparse

from src.audioModem.audioModem import main
from src.misc.config import setup_logging

setup_logging(level=logging.INFO)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vibe Audio Modem")
    parser.add_argument("--cli", action="store_true", help="Enable CLI terminal interface")
    args = parser.parse_args()
    main(cli=args.cli)

import logging
import argparse

from src.audioModem.audioModem import main

logging.basicConfig(
    format="%(asctime)s: %(levelname)s: %(message)s",
    level=logging.INFO,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vibe Audio Modem")
    parser.add_argument("--port", type=int, default=8000, help="HTTP server port (default: 8000)")
    args = parser.parse_args()
    main(http_port=args.port)

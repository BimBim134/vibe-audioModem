"""How much bandwidth a modem's output occupies.

The band runs from the lowest to the highest frequency whose power is within `drop_db` of the
strongest one (20 dB by default), averaged over the transmissions of several random Messages.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import welch

from bench.settings import describe_settings, parse_settings
from bench.threshold import load_modem
from vibemodem.core.modem import Modem

RESULT_SCHEMA_VERSION = 1
SAMPLE_RATE = 48_000
SEGMENT = 2**16  # 1.4 s: bins of 0.73 Hz, finer than the narrowest tone spacing measured
DEFAULT_DROP_DB = 20.0


def _power_spectrum(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    if samples.size < SEGMENT:
        raise ValueError(f"audio too short to measure a band: need {SEGMENT} samples or more")
    return welch(samples, fs=sample_rate, nperseg=SEGMENT, noverlap=SEGMENT // 2)


def _band(frequencies: np.ndarray, power: np.ndarray, drop_db: float) -> tuple[float, float]:
    if not power.max() > 0:
        raise ValueError("audio is silent: it occupies no band")
    inside = np.flatnonzero(power >= power.max() * 10 ** (-drop_db / 10))
    return float(frequencies[inside[0]]), float(frequencies[inside[-1]])


def occupied_band(samples: np.ndarray, sample_rate: int, drop_db: float) -> tuple[float, float]:
    """Lowest and highest frequency, in Hz, within `drop_db` of the strongest frequency."""
    frequencies, power = _power_spectrum(np.asarray(samples, dtype=float), sample_rate)
    return _band(frequencies, power, drop_db)


def measure_band(
    modem: Modem, preset: str, messages: int, message_bytes: int, seed: int, drop_db: float
) -> tuple[tuple[float, float], float]:
    """The band of the average spectrum of random Messages, and a Transmission's length."""
    rng = np.random.default_rng(seed)
    total, seconds = None, 0.0
    for _ in range(messages):
        message = rng.integers(0, 256, message_bytes, dtype=np.uint8).tobytes()
        transmission = np.asarray(modem.modulate(message, preset), dtype=float)
        frequencies, power = _power_spectrum(transmission, SAMPLE_RATE)
        total = power if total is None else total + power
        seconds = transmission.size / SAMPLE_RATE
    return _band(frequencies, total, drop_db), seconds


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Measure the bandwidth a modem's output occupies.")
    parser.add_argument("--modem", required=True, help="package.module:ClassName of the candidate")
    parser.add_argument(
        "--set", action="append", default=[], metavar="NAME=VALUE",
        help="a setting of the modem, e.g. --set tones=4 --set symbol_ms=160 (repeatable)",
    )  # fmt: skip
    parser.add_argument("--preset", default="standard")
    parser.add_argument("--messages", type=int, default=5, help="random Messages averaged")
    parser.add_argument("--message-bytes", type=int, default=12, help="length of each Message")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--drop-db", type=float, default=DEFAULT_DROP_DB,
        help="how far below the strongest frequency the band still counts, in dB",
    )  # fmt: skip
    parser.add_argument("--out", required=True, type=Path, help="JSON file to write")
    args = parser.parse_args(argv)

    if args.messages < 1 or args.message_bytes < 0 or not args.drop_db > 0:
        parser.error("need --messages >= 1, --message-bytes >= 0 and --drop-db > 0")
    try:
        options = parse_settings(args.set)
        modem = load_modem(args.modem, options, args.preset)
        (low, high), seconds = measure_band(
            modem, args.preset, args.messages, args.message_bytes, args.seed, args.drop_db
        )
    except ValueError as error:
        parser.error(str(error))

    chosen = describe_settings(modem, options)
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "modem": args.modem,
        **chosen,
        "preset": args.preset,
        "seed": args.seed,
        "messages": args.messages,
        "message_bytes": args.message_bytes,
        "drop_db": args.drop_db,
        "low_hz": low,
        "high_hz": high,
        "bandwidth_hz": high - low,
        "transmission_seconds": seconds,
    }
    print(f"Occupied band at -{args.drop_db:g} dB: {low:.1f} to {high:.1f} Hz, {high - low:.1f} Hz")
    print(f"Transmission: {seconds:.1f} s")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

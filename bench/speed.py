"""How fast a candidate receives, against real time.

Run it on the machines you care about: the numbers belong to the machine they come from.
"""

import argparse
import json
import os
import platform
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from bench.channel import ChannelConfig, apply_channel
from bench.threshold import load_modem
from vibemodem.core.modem import Modem

LEAD_IN_SECONDS = 5.0
TAIL_SECONDS = 6.0
SNR_DB = -14.0  # near the threshold, where decoding has the most to do
FREQ_OFFSET_HZ = 300.0
CODE_REPEATS = 50


@dataclass(frozen=True)
class SpeedResult:
    recording_seconds: float
    receive_seconds: float  # median time to receive the whole recording
    real_time_factor: float  # recording length over receive time: 200 means 200 times faster
    repeats: int
    # Median time for the modem's Code alone on a clean Frame and on soft values that never
    # decode (the full iteration budget); empty for a modem that has no `code`.
    code_decode_seconds: dict[str, float] = field(default_factory=dict)


def _median_seconds(action: Callable[[], object], repeats: int) -> float:
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        action()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def measure_speed(
    modem: Modem, *, preset: str = "standard", repeats: int = 7, seed: int = 1
) -> SpeedResult:
    """Time the reception of one Transmission hidden in a noisy recording."""
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    rate = ChannelConfig().sample_rate
    transmission = modem.modulate(b"speed test", preset)
    recording = np.concatenate(
        [
            np.zeros(round(LEAD_IN_SECONDS * rate)),
            transmission,
            np.zeros(round(TAIL_SECONDS * rate)),
        ]
    )
    heard = apply_channel(
        recording,
        ChannelConfig(snr_db=SNR_DB, freq_offset_hz=FREQ_OFFSET_HZ),
        seed,
        signal_power=float(np.mean(np.square(transmission))),
    )
    receive = _median_seconds(lambda: modem.demodulate(heard), repeats)

    code_seconds = {}
    code = getattr(modem, "code", None)
    if code is not None:
        rng = np.random.default_rng(seed)
        clean = 1.0 - 2.0 * code.encode(rng.integers(0, 2, code.info_bits, dtype=np.uint8))
        hopeless = rng.normal(size=code.coded_bits)
        code_seconds = {
            "clean": _median_seconds(lambda: code.decode(clean), CODE_REPEATS),
            "failing": _median_seconds(lambda: code.decode(hopeless), CODE_REPEATS),
        }
    seconds = recording.size / rate
    return SpeedResult(
        recording_seconds=seconds,
        receive_seconds=receive,
        real_time_factor=seconds / receive,
        repeats=repeats,
        code_decode_seconds=code_seconds,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Time how fast a candidate modem receives.")
    parser.add_argument("--modem", required=True, help="package.module:ClassName of the candidate")
    parser.add_argument("--preset", default="standard")
    parser.add_argument(
        "--repeats", type=int, default=7, help="receptions timed; the median counts"
    )
    parser.add_argument("--out", type=Path, help="JSON file to write")
    args = parser.parse_args(argv)

    try:
        result = measure_speed(
            load_modem(args.modem, preset=args.preset), preset=args.preset, repeats=args.repeats
        )
    except ValueError as error:
        parser.error(str(error))

    print(
        f"Received a {result.recording_seconds:.1f} s recording in "
        f"{1000 * result.receive_seconds:.0f} ms: {result.real_time_factor:.0f} times real time"
    )
    for what, seconds in result.code_decode_seconds.items():
        print(f"  code alone, {what}: {1000 * seconds:.2f} ms")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        saved = {
            "modem": args.modem,
            "preset": args.preset,
            "machine": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
                "numpy": np.__version__,
            },
            **asdict(result),
        }
        args.out.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

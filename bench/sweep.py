"""Sweep the number of tones and the symbol duration of an M-FSK modem.

For each combination, the occupied bandwidth, the duration of a Transmission and the SNRs at
which 95%, 90% and 80% of the test Messages are received. A fixed seed gives the same file.
"""

import argparse
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

from bench.bandwidth import DEFAULT_DROP_DB, measure_band
from bench.channel import REFERENCE_BANDWIDTH_HZ
from bench.scenarios import SCENARIOS
from bench.settings import parse_settings
from bench.threshold import _snr_grid, load_modem, measure_curve, success_threshold

RESULT_SCHEMA_VERSION = 1
LEVELS = (0.95, 0.9, 0.8)


@dataclass(frozen=True)
class Job:
    """One configuration to measure: everything a worker process needs."""

    modem: str
    options: dict
    scenario: str
    snr_db_values: list[float]
    trials: int
    seed: int
    message_bytes: int
    max_lead_in_s: float
    tail_s: float
    freq_offset_range_hz: tuple[float, float]
    drop_db: float


def _measure(job: Job) -> dict:
    modem = load_modem(job.modem, job.options)
    points = measure_curve(
        modem,
        preset="standard",
        snr_db_values=job.snr_db_values,
        trials=job.trials,
        seed=job.seed,
        message_bytes=job.message_bytes,
        channel=SCENARIOS[job.scenario].config,
        max_lead_in_s=job.max_lead_in_s,
        tail_s=job.tail_s,
        freq_offset_range_hz=job.freq_offset_range_hz,
    )
    (low, high), seconds = measure_band(modem, "standard", 3, job.message_bytes, 1, job.drop_db)
    return {
        **job.options,
        "modem_parameters": getattr(modem, "parameters", None),
        "bandwidth_hz": high - low,
        "transmission_seconds": seconds,
        "thresholds_db": {str(level): success_threshold(points, level) for level in LEVELS},
        "curve": [{**asdict(p), "success_rate": p.success_rate} for p in points],
    }


def _numbers(text: str, kind: type) -> list:
    try:
        return [kind(item) for item in text.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"expected comma-separated numbers, got {text!r}"
        ) from error


def _print_table(configurations: list[dict]) -> None:
    columns = ["tones", "symbol_ms", "bandwidth_hz", "airtime_s", "95%", "90%", "80%"]
    print(" ".join(f"{name:>12}" for name in columns))
    for configuration in configurations:
        thresholds = [configuration["thresholds_db"][str(level)] for level in LEVELS]
        cells = [
            f"{configuration['tones']}",
            f"{configuration['symbol_ms']:g}",
            f"{configuration['bandwidth_hz']:.1f}",
            f"{configuration['transmission_seconds']:.1f}",
            *("-" if t is None else f"{t:g}" for t in thresholds),
        ]
        print(" ".join(f"{cell:>12}" for cell in cells))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Sweep the tones and symbol duration of an M-FSK modem against the bench."
    )
    parser.add_argument("--modem", required=True, help="package.module:ClassName of the candidate")
    parser.add_argument("--tones", default="2,4,8,16", help="numbers of tones, comma-separated")
    parser.add_argument(
        "--symbol-ms", default="40,80,160,320", help="symbol durations in ms, comma-separated"
    )
    parser.add_argument(
        "--set", action="append", default=[], metavar="NAME=VALUE",
        help="a setting given to every configuration, e.g. --set interleave=true (repeatable)",
    )  # fmt: skip
    parser.add_argument("--scenario", default="white", choices=sorted(SCENARIOS))
    parser.add_argument("--snr-from", type=float, default=-24.0, help="lowest SNR tested, in dB")
    parser.add_argument("--snr-to", type=float, default=-8.0, help="highest SNR tested, in dB")
    parser.add_argument("--snr-step", type=float, default=1.0, help="step between SNRs, dB")
    parser.add_argument("--trials", type=int, default=100, help="Messages sent at each SNR")
    parser.add_argument("--message-bytes", type=int, default=12, help="length of each Message")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-lead-in-s", type=float, default=10.0)
    parser.add_argument("--tail-s", type=float, default=1.0)
    parser.add_argument("--freq-offset-from", type=float, default=-1100.0)
    parser.add_argument("--freq-offset-to", type=float, default=1100.0)
    parser.add_argument("--drop-db", type=float, default=DEFAULT_DROP_DB)
    parser.add_argument("--jobs", type=int, default=1, help="configurations measured at once")
    parser.add_argument("--out", required=True, type=Path, help="JSON file to write")
    args = parser.parse_args(argv)

    try:
        tones, symbol_ms = _numbers(args.tones, int), _numbers(args.symbol_ms, float)
        fixed = parse_settings(args.set)
        if args.jobs < 1 or args.trials < 1 or args.message_bytes < 1 or not args.drop_db > 0:
            raise ValueError("need --jobs >= 1, --trials >= 1, --message-bytes >= 1, --drop-db > 0")
        grid = _snr_grid(args.snr_from, args.snr_to, args.snr_step)
        jobs = [
            Job(
                modem=args.modem,
                options={**fixed, "tones": count, "symbol_ms": duration},
                scenario=args.scenario,
                snr_db_values=grid,
                trials=args.trials,
                seed=args.seed,
                message_bytes=args.message_bytes,
                max_lead_in_s=args.max_lead_in_s,
                tail_s=args.tail_s,
                freq_offset_range_hz=(args.freq_offset_from, args.freq_offset_to),
                drop_db=args.drop_db,
            )
            for count, duration in product(tones, symbol_ms)
        ]
        for job in jobs:
            load_modem(job.modem, job.options)  # refuse a bad configuration before any work
        if args.jobs == 1:
            configurations = [_measure(job) for job in jobs]
        else:
            context = multiprocessing.get_context("spawn")  # the same on every platform
            with ProcessPoolExecutor(max_workers=args.jobs, mp_context=context) as pool:
                configurations = list(pool.map(_measure, jobs))
    except (ValueError, argparse.ArgumentTypeError) as error:
        parser.error(str(error))

    _print_table(configurations)
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "modem": args.modem,
        "modem_options": fixed,
        "scenario": args.scenario,
        "seed": args.seed,
        "trials": args.trials,
        "message_bytes": args.message_bytes,
        "max_lead_in_s": args.max_lead_in_s,
        "tail_s": args.tail_s,
        "freq_offset_range_hz": [args.freq_offset_from, args.freq_offset_to],
        "reference_bandwidth_hz": REFERENCE_BANDWIDTH_HZ,
        "drop_db": args.drop_db,
        "configurations": configurations,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

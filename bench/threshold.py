"""Success threshold: the lowest SNR at which a modem receives enough Messages correctly."""

import argparse
import importlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from bench.channel import REFERENCE_BANDWIDTH_HZ, ChannelConfig, apply_channel
from bench.report import write_report
from bench.scenarios import SCENARIOS
from vibemodem.core.modem import Modem

REQUIRED_SUCCESS_RATE = 0.95
RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CurvePoint:
    """How many of the test Messages sent at one SNR were received correctly."""

    snr_db: float  # in a 2,500 Hz reference noise bandwidth
    trials: int
    successes: int
    false_receptions: int = 0  # wrong Messages the modem handed over, across all trials

    def __post_init__(self) -> None:
        if self.trials < 1:
            raise ValueError("trials must be at least 1")
        if not 0 <= self.successes <= self.trials:
            raise ValueError("successes must be between 0 and trials")

    @property
    def success_rate(self) -> float:
        return self.successes / self.trials


def success_threshold(
    points: list[CurvePoint], required: float = REQUIRED_SUCCESS_RATE
) -> float | None:
    """The lowest tested SNR that reaches the required success rate.

    Every higher tested SNR must reach it too, so one lucky point in the noisy region does not
    count. None when even the highest tested SNR falls short. The resolution is that of the
    tested SNR grid, and with N trials per point a measured rate near the required one is
    only known to about 1/sqrt(N) (roughly 2% with 100 trials).
    """
    threshold = None
    for point in sorted(points, key=lambda p: p.snr_db, reverse=True):
        if point.success_rate < required:
            break
        threshold = point.snr_db
    return threshold


def measure_curve(
    modem: Modem,
    *,
    preset: str,
    snr_db_values: list[float],
    trials: int,
    seed: int,
    message_bytes: int,
    channel: ChannelConfig | None = None,
    max_lead_in_s: float = 0.0,
    tail_s: float = 0.0,
    freq_offset_range_hz: tuple[float, float] = (0.0, 0.0),
) -> list[CurvePoint]:
    """Send random Messages through the channel at each SNR and count the correct receptions.

    A trial succeeds only when the modem returns exactly one Message and it is the one that was
    sent: a wrong Message handed over next to the right one is a failure, and every wrong
    Message is counted as a false reception. Every trial draws its Message and its channel
    noise from the seed, so a run is reproducible. The channel impairments other than white
    noise default to none.

    A real receiver does not know when a Transmission starts or where it sits in the audio band.
    With `max_lead_in_s` and `tail_s` each Transmission is hidden at a random moment in a
    recording of constant length (silence before and after, filled with the channel's noise), and
    `freq_offset_range_hz` shifts it by a random number of Hz. The SNR stays that of the
    Transmission itself, not of the whole recording.
    """
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if message_bytes < 1:
        raise ValueError("message_bytes must be at least 1")
    if max_lead_in_s < 0 or tail_s < 0:
        raise ValueError("max_lead_in_s and tail_s must not be negative")
    if freq_offset_range_hz[0] > freq_offset_range_hz[1]:
        raise ValueError("freq_offset_range_hz must be (low, high) with low <= high")
    channel = channel or ChannelConfig()
    points = []
    for index, snr_db in enumerate(snr_db_values):
        successes = false_receptions = 0
        for trial in range(trials):
            sequence = np.random.SeedSequence(seed, spawn_key=(index, trial))
            rng = np.random.default_rng(sequence)
            message = rng.integers(0, 256, message_bytes, dtype=np.uint8).tobytes()
            lead = rng.uniform(0.0, max_lead_in_s)
            offset = rng.uniform(*freq_offset_range_hz)

            transmission = modem.modulate(message, preset)
            rate = channel.sample_rate
            before = round(lead * rate)
            after = round((max_lead_in_s + tail_s) * rate) - before
            recording = np.concatenate([np.zeros(before), transmission, np.zeros(after)])
            trial_channel = replace(channel, snr_db=snr_db)
            if freq_offset_range_hz != (0.0, 0.0):
                trial_channel = replace(trial_channel, freq_offset_hz=offset)
            noisy = apply_channel(
                recording,
                trial_channel,
                seed=int(sequence.generate_state(1)[0]),
                signal_power=float(np.mean(np.square(transmission))),
            )
            received = [r.message for r in modem.demodulate(noisy)]
            successes += received == [message]
            false_receptions += sum(m != message for m in received)
        points.append(
            CurvePoint(
                snr_db=snr_db,
                trials=trials,
                successes=successes,
                false_receptions=false_receptions,
            )
        )
    return points


def load_modem(spec: str) -> Modem:
    """Build a candidate from "package.module:ClassName" (the class takes no arguments)."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ValueError(f"expected 'package.module:ClassName', got {spec!r}")
    try:
        return getattr(importlib.import_module(module_name), attribute)()
    except (ImportError, AttributeError, TypeError) as error:
        raise ValueError(f"cannot load modem {spec!r}: {error}") from error


def _snr_grid(start: float, stop: float, step: float) -> list[float]:
    if step <= 0 or stop < start:
        raise ValueError("need --snr-step > 0 and --snr-to >= --snr-from")
    return np.round(np.arange(start, stop + step / 2, step), 6).tolist()


def _print_report(points: list[CurvePoint], threshold: float | None) -> None:
    print(f"{'SNR (dB)':>9}  {'received':>9}")
    for point in points:
        print(f"{point.snr_db:>9.1f}  {point.successes:>4}/{point.trials:<4}")
    if threshold is None:
        low, high = points[0].snr_db, points[-1].snr_db
        print(f"Success threshold: not reached between {low:g} and {high:g} dB")
    else:
        print(f"Success threshold: {threshold:g} dB")


def _describe_code(modem: Modem) -> dict | None:
    code = getattr(modem, "code", None)
    if code is None:
        return None
    return {"info_bits": code.info_bits, "coded_bits": code.coded_bits, **code.parameters}


def _result(
    args: argparse.Namespace,
    modem: Modem,
    channel: ChannelConfig,
    points: list[CurvePoint],
    threshold: float | None,
) -> dict:
    # No date or commit here on purpose: the same run must give a byte-identical file.
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "modem": args.modem,
        "scenario": args.scenario,
        "code": _describe_code(modem),
        "preset": args.preset,
        "seed": args.seed,
        "trials": args.trials,
        "message_bytes": args.message_bytes,
        "max_lead_in_s": args.max_lead_in_s,
        "tail_s": args.tail_s,
        "freq_offset_range_hz": [args.freq_offset_from, args.freq_offset_to],
        "reference_bandwidth_hz": REFERENCE_BANDWIDTH_HZ,
        "required_success_rate": REQUIRED_SUCCESS_RATE,
        "channel": {k: v for k, v in asdict(channel).items() if k != "snr_db"},
        "curve": [{**asdict(p), "success_rate": p.success_rate} for p in points],
        "threshold_db": threshold,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Measure the Success threshold of a candidate modem on white noise."
    )
    parser.add_argument("--modem", required=True, help="package.module:ClassName of the candidate")
    parser.add_argument("--preset", default="standard")
    parser.add_argument(
        "--scenario", default="white", choices=sorted(SCENARIOS),
        help="; ".join(f"{name}: {SCENARIOS[name].description}" for name in sorted(SCENARIOS)),
    )  # fmt: skip
    parser.add_argument("--snr-from", type=float, default=-20.0, help="lowest SNR tested, in dB")
    parser.add_argument("--snr-to", type=float, default=0.0, help="highest SNR tested, in dB")
    parser.add_argument("--snr-step", type=float, default=1.0, help="step between tested SNRs, dB")
    parser.add_argument("--trials", type=int, default=100, help="Messages sent at each SNR")
    parser.add_argument("--message-bytes", type=int, default=2, help="length of each Message")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--max-lead-in-s",
        type=float,
        default=0.0,
        help="hide the signal up to this many seconds in",
    )
    parser.add_argument("--tail-s", type=float, default=0.0, help="silence kept after the signal")
    parser.add_argument("--freq-offset-from", type=float, default=0.0, help="lowest shift, in Hz")
    parser.add_argument("--freq-offset-to", type=float, default=0.0, help="highest shift, in Hz")
    parser.add_argument("--out", required=True, type=Path, help="JSON file to write")
    parser.add_argument("--html", type=Path, help="also write a human-readable HTML report")
    args = parser.parse_args(argv)

    channel = SCENARIOS[args.scenario].config
    try:
        modem = load_modem(args.modem)
        points = measure_curve(
            modem,
            preset=args.preset,
            snr_db_values=_snr_grid(args.snr_from, args.snr_to, args.snr_step),
            trials=args.trials,
            seed=args.seed,
            message_bytes=args.message_bytes,
            channel=channel,
            max_lead_in_s=args.max_lead_in_s,
            tail_s=args.tail_s,
            freq_offset_range_hz=(args.freq_offset_from, args.freq_offset_to),
        )
    except ValueError as error:
        parser.error(str(error))

    threshold = success_threshold(points)
    _print_report(points, threshold)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = _result(args, modem, channel, points, threshold)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.html:
        write_report([result], args.html)


if __name__ == "__main__":
    main()

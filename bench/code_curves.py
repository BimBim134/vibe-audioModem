"""How often a code loses a frame on white noise, against Eb/N0.

A quick way to compare error-correcting codes without the modem around them: each frame's coded
bits are sent as +1 or -1, white noise is added, and the soft values go to the code's decoder.
Eb/N0 is the energy per information bit over the noise density, so codes of different rates
are compared fairly. A frame is lost when the decoder returns nothing or any wrong bit.
"""

import argparse
import importlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from vibemodem.core.code import Code


@dataclass(frozen=True)
class FramePoint:
    ebn0_db: float
    frames: int
    errors: int  # frames lost, whether the decoder said nothing or gave wrong bits
    no_answer: int  # of those, frames for which the decoder returned nothing


def frame_error_rate(code: Code, ebn0_db: float, frames: int, seed: int) -> float:
    return _lost_frames(code, ebn0_db, frames, seed)[0] / frames


def _lost_frames(code: Code, ebn0_db: float, frames: int, seed: int) -> tuple[int, int]:
    """(frames lost, of which the decoder returned nothing)."""
    if frames < 1:
        raise ValueError("frames must be at least 1")
    rate = code.info_bits / code.coded_bits
    noise_std = math.sqrt(1 / (2 * rate * 10 ** (ebn0_db / 10)))
    rng = np.random.default_rng(seed)
    lost = silent = 0
    for _ in range(frames):
        info = rng.integers(0, 2, code.info_bits, dtype=np.uint8)
        sent = 1.0 - 2.0 * code.encode(info)
        received = sent + noise_std * rng.normal(size=sent.size)
        decoded = code.decode(2.0 * received / noise_std**2)  # soft values: positive means 0
        silent += decoded is None
        lost += decoded is None or not np.array_equal(decoded, info)
    return lost, silent


def parse_settings(assignments: list[str]) -> dict:
    """ "name=value" pairs, each value a JSON literal (7, 0.9, "text"), as keyword arguments."""
    settings = {}
    for assignment in assignments:
        name, equals, text = assignment.partition("=")
        if not equals or not name:
            raise ValueError(f"expected name=value, got {assignment!r}")
        try:
            settings[name] = json.loads(text)
        except ValueError as error:
            raise ValueError(f"the value of {name} is not a JSON literal: {text!r}") from error
    return settings


def load_code(spec: str, info_bits: int, settings: dict | None = None) -> Code:
    """Build a code from "package.module:ClassName", called with `info_bits=` and settings."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ValueError(f"expected 'package.module:ClassName', got {spec!r}")
    try:
        return getattr(importlib.import_module(module_name), attribute)(
            info_bits=info_bits, **(settings or {})
        )
    except (ImportError, AttributeError, TypeError) as error:
        raise ValueError(f"cannot load code {spec!r}: {error}") from error


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Frame error rate of a code on white noise.")
    parser.add_argument("--code", required=True, help="package.module:ClassName of the code")
    parser.add_argument("--info-bits", type=int, default=200)
    parser.add_argument(
        "--set", action="append", default=[], metavar="NAME=VALUE",
        help="a setting of the code, e.g. --set max_iterations=20 (repeatable)",
    )  # fmt: skip
    parser.add_argument("--ebn0-from", type=float, default=1.0, help="lowest Eb/N0, in dB")
    parser.add_argument("--ebn0-to", type=float, default=3.0, help="highest Eb/N0, in dB")
    parser.add_argument("--ebn0-step", type=float, default=0.5, help="step in dB")
    parser.add_argument("--frames", type=int, default=800, help="frames sent at each Eb/N0")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, help="JSON file to write")
    args = parser.parse_args(argv)

    if args.ebn0_step <= 0 or args.ebn0_to < args.ebn0_from:
        parser.error("need --ebn0-step > 0 and --ebn0-to >= --ebn0-from")
    if args.frames < 1:
        parser.error("--frames must be at least 1")
    try:
        code = load_code(args.code, args.info_bits, parse_settings(args.set))
    except ValueError as error:
        parser.error(str(error))

    grid = np.round(np.arange(args.ebn0_from, args.ebn0_to + args.ebn0_step / 2, args.ebn0_step), 6)
    points = []
    for ebn0 in grid:
        lost, silent = _lost_frames(code, float(ebn0), args.frames, args.seed)
        points.append(FramePoint(float(ebn0), args.frames, lost, silent))

    print(f"{'Eb/N0 (dB)':>10}  {'frames lost':>12}  {'no answer':>9}")
    for point in points:
        share = point.errors / point.frames
        print(
            f"{point.ebn0_db:>10.1f}  {point.errors:>5}/{point.frames:<5} {share:>6.1%}"
            f"  {point.no_answer:>9}"
        )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        saved = {
            "code": {"info_bits": code.info_bits, "coded_bits": code.coded_bits, **code.parameters},
            "seed": args.seed,
            "curve": [asdict(point) for point in points],
        }
        args.out.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

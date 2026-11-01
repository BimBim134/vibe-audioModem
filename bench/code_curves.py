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
    errors: int


def frame_error_rate(code: Code, ebn0_db: float, frames: int, seed: int) -> float:
    return _lost_frames(code, ebn0_db, frames, seed) / frames


def _lost_frames(code: Code, ebn0_db: float, frames: int, seed: int) -> int:
    if frames < 1:
        raise ValueError("frames must be at least 1")
    rate = code.info_bits / code.coded_bits
    noise_std = math.sqrt(1 / (2 * rate * 10 ** (ebn0_db / 10)))
    rng = np.random.default_rng(seed)
    lost = 0
    for _ in range(frames):
        info = rng.integers(0, 2, code.info_bits, dtype=np.uint8)
        sent = 1.0 - 2.0 * code.encode(info)
        received = sent + noise_std * rng.normal(size=sent.size)
        decoded = code.decode(2.0 * received / noise_std**2)  # soft values: positive means 0
        lost += decoded is None or not np.array_equal(decoded, info)
    return lost


def load_code(spec: str, info_bits: int) -> Code:
    """Build a code from "package.module:ClassName", called with `info_bits=`."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ValueError(f"expected 'package.module:ClassName', got {spec!r}")
    try:
        return getattr(importlib.import_module(module_name), attribute)(info_bits=info_bits)
    except (ImportError, AttributeError, TypeError) as error:
        raise ValueError(f"cannot load code {spec!r}: {error}") from error


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Frame error rate of a code on white noise.")
    parser.add_argument("--code", required=True, help="package.module:ClassName of the code")
    parser.add_argument("--info-bits", type=int, default=200)
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
        code = load_code(args.code, args.info_bits)
    except ValueError as error:
        parser.error(str(error))

    grid = np.round(np.arange(args.ebn0_from, args.ebn0_to + args.ebn0_step / 2, args.ebn0_step), 6)
    points = [
        FramePoint(
            float(ebn0), args.frames, _lost_frames(code, float(ebn0), args.frames, args.seed)
        )
        for ebn0 in grid
    ]

    print(f"{'Eb/N0 (dB)':>10}  {'frames lost':>12}")
    for point in points:
        share = point.errors / point.frames
        print(f"{point.ebn0_db:>10.1f}  {point.errors:>5}/{point.frames:<5} {share:>6.1%}")
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

"""How often a receiver reports a Signal in noise alone.

A Signal is reported when its Preamble matches strongly enough (the score) but the Frame cannot
be read. In noise there is no Signal, so every report is a false alarm. The rate is counted over
hours of white noise, or of noise as an SSB radio gives it (filtered to 300-2700 Hz).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from bench.channel import ChannelConfig, apply_channel
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.turbo_modem import TurboModem

RECORDING_SECONDS = 120


def count_false_alarms(preset: str, hours: float, seed: int, ssb: bool) -> dict:
    """Reports of Signals, and of Messages, in `hours` of noise with no Signal in it."""
    modem = TurboModem(preset=preset)
    recordings = max(1, round(hours * 3600 / RECORDING_SECONDS))
    config = ChannelConfig(snr_db=0.0, band_filter=ssb)
    signals = messages = 0
    for number in range(recordings):
        silence = np.zeros(RECORDING_SECONDS * SAMPLE_RATE)
        # A tiny carrier gives the channel a "signal power" to set the noise level against.
        heard = apply_channel(silence, config, seed + number, signal_power=0.05)
        report = modem.demodulate_report(heard)
        signals += len(report.undecoded)
        messages += len(report.receptions)
    return {
        "preset": preset,
        "noise": "ssb" if ssb else "white",
        "hours": recordings * RECORDING_SECONDS / 3600,
        "reported_signals": signals,
        "reported_messages": messages,
        "signals_per_hour": signals / (recordings * RECORDING_SECONDS / 3600),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Count false alarms of the receiver in noise.")
    parser.add_argument("--preset", default="standard", choices=["max-range", "standard", "fast"])
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ssb", action="store_true", help="noise filtered like an SSB radio's")
    parser.add_argument("--out", type=Path, help="JSON file to write")
    args = parser.parse_args(argv)
    if not args.hours > 0:
        parser.error("--hours must be positive")
    result = count_false_alarms(args.preset, args.hours, args.seed, args.ssb)
    print(
        f"{result['preset']}, {result['noise']} noise, {result['hours']:.2f} h: "
        f"{result['reported_signals']} Signals reported, {result['reported_messages']} Messages "
        f"({result['signals_per_hour']:.2f} Signals per hour)"
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

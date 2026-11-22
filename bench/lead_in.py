"""Does a Lead-in change what the receiver does? Same noise, with and without the tone before.

For each Preset, at its success threshold and a little above, `--trials` Transmissions are sent
through white noise with no Lead-in and with one. Counted: Messages received correctly, and
Signals reported without a Message beside the one sent (the false alarms a tone could cause).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from bench.channel import ChannelConfig, apply_channel
from vibemodem.core import mfsk
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import Fragment
from vibemodem.core.transmission import lead_in, transmit
from vibemodem.core.turbo_modem import TurboModem

THRESHOLDS_DB = {"max-range": -22.0, "standard": -16.0, "fast": -13.0}
MESSAGE = b"hello"


def trial(modem, preset: str, snr_db: float, seed: int, lead_in_ms: int) -> tuple[bool, int]:
    sound = transmit(modem, MESSAGE, preset, msg_id=1)
    power = float(np.mean(sound**2))  # the noise is set against the Signal alone, in both cases
    if lead_in_ms:
        tone = lead_in(mfsk.FIRST_TONE_HZ, lead_in_ms, float(np.abs(sound).max()))
        sound = np.concatenate([tone, sound])
    quiet = np.zeros(2 * SAMPLE_RATE, dtype=np.float32)
    heard = apply_channel(
        np.concatenate([quiet, sound, quiet]),
        ChannelConfig(snr_db=snr_db),
        seed,
        signal_power=power,
    )
    report = modem.demodulate_report(heard)
    ok = any(
        (fragment := Fragment.unpack(r.message)) and fragment.payload == MESSAGE
        for r in report.receptions
    )
    return ok, len(report.undecoded)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare reception with and without a Lead-in.")
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--lead-in-ms", type=int, default=500)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    rows = []
    for preset, threshold in THRESHOLDS_DB.items():
        modem = TurboModem(preset=preset)
        for snr_db in (threshold, threshold + 2.0):
            row = {"preset": preset, "snr_db": snr_db, "trials": args.trials}
            for name, ms in (("without", 0), ("with", args.lead_in_ms)):
                results = [trial(modem, preset, snr_db, seed, ms) for seed in range(args.trials)]
                row[name] = {
                    "received": sum(ok for ok, _ in results),
                    "extra_signals": sum(extra for _, extra in results),
                }
            rows.append(row)
            print(row, flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"lead_in_ms": args.lead_in_ms, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()

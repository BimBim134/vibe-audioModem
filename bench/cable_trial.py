"""A trial over a real sound chain at known SNRs: send Messages at each SNR, count what arrives.

The sending computer adds white noise to each Transmission itself, so the SNR is known exactly
(as in the simulator, against a 2,500 Hz reference), and plays the result through its sound card
and an audio cable into the receiving computer, whose application keeps what it receives. The
loss against the simulator is then that of the real chain alone: sound cards, their clocks, the
cable and the receiver's own filtering, with no room in between.

    # on the sending computer
    python -m bench.cable_trial send --preset fast --output "USB Audio" --per-level 20

    # on the receiving computer, with "Keep" switched on in the Advanced settings and the
    # stored receptions cleared, listening to the same Preset; then, when it is all sent:
    python -m bench.cable_trial report ~/.local/share/vibemodem/receptions --preset fast

Both sides must be given the same `--snr=-16,-14` list (with an equals sign: a list starting
with a minus is not read otherwise) and `--per-level` number (or both leave the
defaults). Each Message is a short text that names its own SNR and number, so the report does
not need the list of what was sent. Run one Preset at a time and clear the stored receptions
between two Presets.
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from bench.channel import ChannelConfig, apply_channel
from bench.field_check import check_directory
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import random_message_id
from vibemodem.core.presets import PRESETS
from vibemodem.core.transmission import transmit
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import Audio, SoundCard

# Success thresholds on white noise, from docs/measurements/presets/ (95 % of Messages received)
SIMULATED_THRESHOLD_DB = {"max-range": -22.0, "standard": -16.0, "fast": -13.0}
REQUIRED_RATE = 0.95
PEAK = 0.9  # the loudest sample played, so that the card never clips
_LABEL = re.compile(r"T(-?\d+(?:\.\d+)?) #(\d+)")


@dataclass(frozen=True)
class LevelRow:
    snr_db: float
    received: int
    sent: int

    @property
    def rate(self) -> float:
        return self.received / self.sent if self.sent else 0.0


def _number(snr_db: float) -> str:
    return f"{snr_db:g}"


def label(snr_db: float, number: int) -> str:
    """The text of a Message of the trial: its SNR and its number at that SNR."""
    return f"T{_number(snr_db)} #{number:02d}"


def trial_messages(levels: list[float], per_level: int) -> list[str]:
    return [label(snr, k) for snr in levels for k in range(per_level)]


def default_levels(preset: str) -> list[float]:
    """From 2 dB under the simulated threshold to 8 dB over it, every 2 dB: a chain that loses
    a few dB still crosses 95 % inside the range."""
    threshold = SIMULATED_THRESHOLD_DB[preset]
    return [threshold + offset for offset in range(-2, 9, 2)]


def render(
    modem: TurboModem, preset: str, text: str, snr_db: float, seed: int, gap_seconds: float = 0.0
) -> np.ndarray:
    """The Transmission of a text in white noise at an SNR, noise all around it, scaled to fit.

    The noise covers the gaps as well: the receiver measures the noise it hears over its whole
    recording, so a quiet gap beside a noisy Transmission would make the trial easier than the
    simulator's."""
    sound = transmit(modem, text.encode(), preset, msg_id=random_message_id(), copies=1)
    gap = np.zeros(round(gap_seconds * SAMPLE_RATE))
    power = float(np.mean(sound**2))
    noisy = apply_channel(
        np.concatenate([gap, sound, gap]), ChannelConfig(snr_db=snr_db), seed, signal_power=power
    )
    return noisy * (PEAK / np.abs(noisy).max())


def run_send(
    audio: Audio,
    *,
    output,
    preset: str,
    levels: list[float],
    per_level: int,
    gap_seconds: float = 2.0,
    seed: int = 1,
    progress=lambda text: None,
) -> None:
    modem = TurboModem(preset=preset)
    messages = trial_messages(levels, per_level)
    snrs = [snr for snr in levels for _ in range(per_level)]
    for number, (snr, text) in enumerate(zip(snrs, messages, strict=True)):
        progress(f"{number + 1} of {len(messages)}: {text}")
        audio.play(render(modem, preset, text, snr, seed + number, gap_seconds), device=output)


def report(directory: Path, preset: str, levels: list[float], per_level: int) -> list[LevelRow]:
    """For each SNR, how many of its Messages the receiver kept in full."""
    sent = [text.encode() for text in trial_messages(levels, per_level)]
    results = check_directory(directory, sent, preset=preset)
    heard = [m for result in results for m in result.received]
    counts = {snr: 0 for snr in levels}
    for message in heard:
        found = _LABEL.fullmatch(message.decode("utf-8", errors="replace"))
        if found and float(found[1]) in counts:
            counts[float(found[1])] += 1
    return [LevelRow(snr, counts[snr], per_level) for snr in sorted(levels)]


def measured_threshold(rows: list[LevelRow]) -> float | None:
    """The lowest SNR from which up to the loudest level 95 % of the Messages arrived."""
    threshold = None
    for row in sorted(rows, key=lambda r: r.snr_db, reverse=True):
        if row.rate < REQUIRED_RATE:
            break
        threshold = row.snr_db
    return threshold


def device_argument(text: str | None) -> int | str | None:
    """A device given as digits is a device number, anything else a part of a name."""
    return int(text) if text is not None and text.isdigit() else text


def _levels(text: str) -> list[float]:
    try:
        levels = sorted({float(part) for part in text.split(",")})
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a list of SNRs like -16,-14,-12"
        ) from None
    return levels


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trial of a real sound chain at known SNRs.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("send", "report"):
        command = commands.add_parser(name)
        command.add_argument("--preset", choices=sorted(PRESETS), required=True)
        command.add_argument("--snr", type=_levels, help="SNRs in dB, comma separated")
        command.add_argument("--per-level", type=int, default=20)
        if name == "send":
            command.add_argument("--output", help="output device (number or part of its name)")
            command.add_argument("--gap", type=float, default=2.0, help="noise before and after")
            command.add_argument("--seed", type=int, default=1)
        else:
            command.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    levels = args.snr or default_levels(args.preset)
    if args.command == "send":
        run_send(
            SoundCard(),
            output=device_argument(args.output),
            preset=args.preset,
            levels=levels,
            per_level=args.per_level,
            gap_seconds=args.gap,
            seed=args.seed,
            progress=print,
        )
        return
    rows = report(args.directory, args.preset, levels, args.per_level)
    for row in rows:
        print(f"{row.snr_db:6g} dB  {row.received:3d} of {row.sent}  {row.rate:4.0%}")
    simulated = SIMULATED_THRESHOLD_DB[args.preset]
    measured = measured_threshold(rows)
    if measured is None:
        print(f"95 % not reached at the loudest level; the simulator's threshold is {simulated} dB")
    else:
        print(
            f"measured threshold {measured:g} dB, simulator {simulated:g} dB: "
            f"the real chain loses {measured - simulated:+.1f} dB"
        )


if __name__ == "__main__":
    main()

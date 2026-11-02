"""Replay stored receptions through the decoder, to check they give what they gave live.

    python -m bench.replay ~/.local/share/vibemodem/receptions

Each reception was kept with its audio and its indicators. Replaying it decodes the audio again
with the same modem and Preset: a Frame that was read must give the same Message, at the same
frequency (to 1 Hz) and the same SNR (to 1 dB); a Signal that was lost must still be lost, so a
change in the decoder shows up as the receptions that change.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from bench.threshold import load_modem
from vibemodem.app.store import ReceptionStore
from vibemodem.io.wav import read_wav

FREQUENCY_TOLERANCE_HZ = 1.0
SNR_TOLERANCE_DB = 1.0


@dataclass(frozen=True)
class Replayed:
    name: str
    decoded: bool  # as it was kept
    matches: bool
    detail: str
    snr_db: float | None = None
    stored_snr_db: float | None = None
    frequency_hz: float | None = None
    stored_frequency_hz: float | None = None


def replay_one(wav: Path, saved: dict) -> Replayed:
    spec = saved["modem"]
    if not isinstance(spec, str) or not spec.startswith("vibemodem."):
        # What is in a file of that folder is not trusted: only our own modems are loaded.
        return Replayed(wav.name, bool(saved.get("decoded")), False, f"unknown modem {spec!r}")
    modem = load_modem(spec, {"preset": saved["preset"]})
    report = modem.demodulate_report(read_wav(wav))
    if not saved["decoded"]:
        read = [r for r in report.receptions]
        if read:
            return Replayed(wav.name, False, False, f"now read ({read[0].message.hex()})")
        return Replayed(wav.name, False, True, "still lost")
    body = bytes.fromhex(saved["body_hex"])
    for reception in report.receptions:
        if reception.message != body:
            continue
        frequency = 1450.0 + reception.frequency_offset_hz
        same_frequency = abs(frequency - saved["frequency_hz"]) <= FREQUENCY_TOLERANCE_HZ
        same_snr = abs(reception.snr_db - saved["snr_db"]) <= SNR_TOLERANCE_DB
        detail = "same Message" + ("" if same_frequency and same_snr else ", other figures")
        return Replayed(
            wav.name,
            True,
            same_frequency and same_snr,
            detail,
            snr_db=reception.snr_db,
            stored_snr_db=saved["snr_db"],
            frequency_hz=frequency,
            stored_frequency_hz=saved["frequency_hz"],
        )
    return Replayed(wav.name, True, False, "the Message is no longer read")


def replay_directory(directory: Path) -> list[Replayed]:
    """Replay every reception kept in a directory, oldest first."""
    store = ReceptionStore(directory, max_bytes=10**15)
    results = []
    for wav, saved in store.receptions():
        try:
            results.append(replay_one(wav, saved))
        except (KeyError, TypeError, ValueError, OSError) as error:  # a damaged reception
            decoded = bool(saved.get("decoded"))
            results.append(Replayed(wav.name, decoded, False, f"cannot be replayed ({error})"))
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Replay kept receptions through the decoder.")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    results = replay_directory(args.directory)
    if not results:
        print("no receptions in that directory")
        return
    for result in results:
        print(f"{'ok      ' if result.matches else 'MISMATCH'}  {result.name}  {result.detail}")
    good = sum(r.matches for r in results)
    print(f"{good} of {len(results)} give the same result")
    if good < len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

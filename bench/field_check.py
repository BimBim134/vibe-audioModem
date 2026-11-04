"""Check a field trial: what was sent against what a receiver kept.

    python -m bench.field_check ~/.local/share/vibemodem/receptions sent.txt [--preset fast]

`sent.txt` lists the Messages that were sent, one per line (UTF-8, blank lines ignored; a Message
sent twice is listed twice). The receiver must have kept its receptions during the trial (the
"Keep" switch of the Advanced settings). The kept Fragments are put back into Messages the way
the application does and compared with the list: received, missing, incomplete, and heard but
not listed. With `--redecode` the audio is decoded again instead of trusting the figures kept
with it, so the result does not depend on what the application did live.

Check one Preset at a time: every Preset found in the folder is compared with the whole list,
so clear the stored receptions between two Presets, or select one with `--preset`.
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from bench.threshold import load_modem
from vibemodem.app.store import ReceptionStore
from vibemodem.core.message import Fragment, Incomplete, Reassembler
from vibemodem.io.wav import read_wav


@dataclass
class FieldResult:
    preset: str
    sent: int
    received: list[bytes] = field(default_factory=list)
    missing: list[bytes] = field(default_factory=list)
    unexpected: list[bytes] = field(default_factory=list)
    incomplete: list[Incomplete] = field(default_factory=list)
    signals_lost: int = 0
    snr_db: list[float] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return len(self.received) / self.sent if self.sent else 1.0


def read_sent(path: Path) -> list[bytes]:
    """The Messages listed in a file, one per line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.encode("utf-8") for line in lines if line.strip()]


def _frames(wav: Path, saved: dict, redecode: bool) -> list[tuple[bytes, float]]:
    """(Frame body, SNR) of the Frames read in one kept reception."""
    if not saved["decoded"] and not redecode:
        return []
    if not redecode:
        return [(bytes.fromhex(saved["body_hex"]), saved["snr_db"])]
    spec = saved["modem"]
    if not isinstance(spec, str) or not spec.startswith("vibemodem."):
        raise ValueError(f"unknown modem {spec!r}")  # only our own modems are loaded
    modem = load_modem(spec, {"preset": saved["preset"]})
    report = modem.demodulate_report(read_wav(wav))
    return [(r.message, r.snr_db) for r in sorted(report.receptions, key=lambda r: r.start_sample)]


def check_directory(
    directory: Path, sent: list[bytes], *, redecode: bool = False, preset: str | None = None
) -> list[FieldResult]:
    """One result per Preset found among the receptions kept in a folder."""
    store = ReceptionStore(directory, max_bytes=10**15)
    reassemblers: dict[str, Reassembler] = {}
    results: dict[str, FieldResult] = {}
    waiting: dict[str, list[bytes]] = {}
    for wav, saved in store.receptions():
        name = saved.get("preset")
        if preset is not None and name != preset:
            continue
        result = results.setdefault(name, FieldResult(name, len(sent)))
        waiting.setdefault(name, list(sent))
        reassembler = reassemblers.setdefault(name, Reassembler())
        if not saved["decoded"]:
            result.signals_lost += 1
        try:
            frames = _frames(wav, saved, redecode)
        except (KeyError, TypeError, ValueError, OSError):
            result.signals_lost += 1  # a damaged reception counts as a Signal not read
            continue
        for body, snr in frames:
            result.snr_db.append(snr)
            fragment = Fragment.unpack(body)
            done = reassembler.add(fragment) if fragment else None
            if done is None:
                continue
            if done.message in waiting[name]:
                waiting[name].remove(done.message)
                result.received.append(done.message)
            else:
                result.unexpected.append(done.message)
    for name, result in results.items():
        result.missing = waiting[name]
        result.incomplete = reassemblers[name].finish()
    return list(results.values())


def _show(message: bytes) -> str:
    text = message.decode("utf-8", errors="replace")
    return repr(text if len(text) <= 40 else text[:37] + "...")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare the Messages sent with those received.")
    parser.add_argument("directory", type=Path, help="the folder of kept receptions")
    parser.add_argument("sent", type=Path, help="the Messages sent, one per line")
    parser.add_argument("--preset", help="check only this Preset")
    parser.add_argument("--redecode", action="store_true", help="decode the audio again")
    args = parser.parse_args(argv)
    results = check_directory(
        args.directory, read_sent(args.sent), redecode=args.redecode, preset=args.preset
    )
    if not results:
        print("no receptions in that directory")
        return
    for r in results:
        snr = f", SNR {min(r.snr_db):.1f} to {max(r.snr_db):.1f} dB" if r.snr_db else ""
        print(
            f"{r.preset}: {len(r.received)} of {r.sent} received ({r.rate:.0%}), "
            f"{len(r.incomplete)} incomplete, {len(r.unexpected)} not listed, "
            f"{r.signals_lost} Signals lost{snr}"
        )
        for message in r.missing:
            print(f"  missing     {_show(message)}")
        for lost in r.incomplete:
            print(
                f"  incomplete  id {lost.msg_id}, {lost.missing} of {lost.total} Fragments missing"
            )
        for message in r.unexpected:
            print(f"  not listed  {_show(message)}")
    if any(r.missing for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

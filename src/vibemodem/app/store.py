"""Receptions kept on disk: the raw audio and the indicators of each, within a bound.

A reception is a WAV file (16-bit mono, 48 kHz) and a JSON file of the same name that say how it
was received. The JSON is written last, by renaming, so a reception without it is not complete
and is cleaned away. Only regular files named like ours are ever counted, read or deleted, so a
directory shared with other things is safe, and what is read from it is not trusted. Names begin
with the time in UTC, so the oldest go first when the bound is passed.
"""

import itertools
import json
import math
import os
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

from vibemodem.io.wav import write_wav

SCHEMA_VERSION = 1
_NAME = re.compile(r"\d{8}-\d{6}-\d{3}-\d{4}\.(wav|json)")


def default_directory() -> Path:
    """Where receptions are kept for the current user, by the habits of the platform."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return base / "VibeModem" / "receptions"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "VibeModem" / "receptions"
    base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / "vibemodem" / "receptions"


def checked_bound(max_bytes: int) -> int:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("the bound of the store is a whole number of bytes, at least 1")
    return max_bytes


def _plain(value):
    """What JSON can hold: numpy numbers become numbers, a number that is no number is None."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class ReceptionStore:
    def __init__(self, directory: Path, max_bytes: int):
        self.directory = Path(directory)
        self._max_bytes = checked_bound(max_bytes)
        self._lock = threading.Lock()
        self._sequence = itertools.count()

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    # Looking at the directory: always under the lock, and file by file -------------------------

    def _files(self) -> list[Path]:
        try:
            names = sorted(self.directory.iterdir())
        except OSError:  # not made yet, or gone
            return []
        return [p for p in names if _NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()]

    @staticmethod
    def _size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:  # deleted by someone else since it was listed
            return 0

    def _receptions(self) -> dict[str, list[Path]]:
        """The files of each reception (WAV and JSON), by name, oldest first."""
        found: dict[str, list[Path]] = {}
        for path in self._files():
            found.setdefault(path.stem, []).append(path)
        return found

    def usage(self) -> tuple[int, int]:
        """How many complete receptions are kept, and how many bytes their files take."""
        with self._lock:
            groups = self._receptions()
            complete = sum(len(files) == 2 for files in groups.values())
            return complete, sum(self._size(p) for files in groups.values() for p in files)

    def receptions(self) -> list[tuple[Path, dict]]:
        """Each complete reception, oldest first: its WAV file and its indicators. Files that
        cannot be read, or are not what they should be, are left out."""
        with self._lock:
            found = []
            for files in self._receptions().values():
                wav = next((p for p in files if p.suffix == ".wav"), None)
                record = next((p for p in files if p.suffix == ".json"), None)
                if wav is None or record is None:
                    continue
                try:
                    saved = json.loads(record.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(saved, dict):
                    found.append((wav, saved))
            return found

    # Changing it --------------------------------------------------------------------------------

    def _new_name(self) -> str:
        now = time.time()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now))
        while True:
            name = f"{stamp}-{int(now * 1000) % 1000:03d}-{next(self._sequence) % 10000:04d}"
            if not (self.directory / f"{name}.wav").exists():
                return name

    def save(self, audio: np.ndarray, indicators: dict) -> Path:
        """Keep a reception; returns the WAV file. Raises if it alone would pass the bound."""
        with self._lock:
            name = self._new_name()
            record = {"schema_version": SCHEMA_VERSION, "wav": f"{name}.wav", **indicators}
            text = json.dumps(_plain(record), indent=2) + "\n"
            size = 44 + 2 * len(audio) + len(text.encode("utf-8"))
            if size > self._max_bytes:
                raise ValueError(
                    f"a reception of {size} bytes is over the bound of the store "
                    f"({self._max_bytes} bytes): it is not kept"
                )
            self.directory.mkdir(parents=True, exist_ok=True)
            wav = self.directory / f"{name}.wav"
            partial = self.directory / f"{name}.json.part"
            try:
                write_wav(wav, audio)
                partial.write_text(text, encoding="utf-8")
                partial.replace(self.directory / f"{name}.json")  # the reception is complete
            except BaseException:
                wav.unlink(missing_ok=True)
                partial.unlink(missing_ok=True)
                raise
            self._enforce()
        return wav

    def _enforce(self) -> None:
        """Delete what is not a whole reception, then the oldest ones until the bound holds."""
        groups = self._receptions()
        for name, files in list(groups.items()):
            if len(files) != 2:  # a WAV without its JSON, or the contrary: left by a crash
                for path in files:
                    path.unlink(missing_ok=True)
                del groups[name]
        used = sum(self._size(p) for files in groups.values() for p in files)
        for files in groups.values():  # oldest first: the names begin with the time
            if used <= self._max_bytes:
                break
            for path in files:
                used -= self._size(path)
                path.unlink(missing_ok=True)

    def set_max_bytes(self, max_bytes: int) -> None:
        with self._lock:
            self._max_bytes = checked_bound(max_bytes)
            self._enforce()

    def clear(self) -> int:
        """Delete every reception, and the pieces of unfinished ones; returns how many."""
        with self._lock:
            groups = self._receptions()
            for files in groups.values():
                for path in files:
                    path.unlink(missing_ok=True)
        return sum(len(files) == 2 for files in groups.values())

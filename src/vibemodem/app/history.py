"""The history of the conversation: each Message sent or received, kept in a SQLite file.

Only text and figures are kept, never sound (that is the job of the kept receptions). The file
stays on the computer. It is made when the first Message is written, so a station that never
sends nor receives leaves nothing behind. Each call opens its own short connection, so the threads
of the application never share one.
"""

import csv
import io
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from vibemodem.app import callsign as callsign_module

LOADED = 1_000  # the most recent Messages shown again when the application starts
COLUMNS = ("time", "direction", "callsign", "text", "frequency_hz", "snr_db", "preset", "state")
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")  # a spreadsheet would run a cell starting so

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    direction TEXT NOT NULL,
    callsign TEXT,
    text TEXT NOT NULL,
    frequency_hz REAL,
    snr_db REAL,
    preset TEXT,
    state TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}'
)
"""


class History:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self, create: bool) -> sqlite3.Connection | None:
        if not create and not self.path.exists():
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        link = sqlite3.connect(self.path, timeout=5.0)
        link.execute(_SCHEMA)
        return link

    def add(
        self,
        *,
        at: float,
        direction: str,
        text: str,
        frequency_hz: float | None,
        snr_db: float | None,
        preset: str,
        state: str,
        detail: dict | None = None,
    ) -> None:
        """Write a Message. Raises `sqlite3.Error` or `OSError` if the file cannot be written."""
        link = self._connect(create=True)
        try:
            with link:
                link.execute(
                    "INSERT INTO messages (at, direction, callsign, text, frequency_hz, snr_db,"
                    " preset, state, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        at,
                        direction,
                        callsign_module.callsign_of(text),
                        text,
                        frequency_hz,
                        snr_db,
                        preset,
                        state,
                        json.dumps(detail or {}),
                    ),
                )
        finally:
            link.close()

    def rows(self, limit: int | None = None) -> list[dict]:
        """The Messages, oldest first (the last `limit` of them). A file that is missing or
        cannot be read gives none."""
        try:
            link = self._connect(create=False)
            if link is None:
                return []
            try:
                found = link.execute(
                    "SELECT id, at, direction, callsign, text, frequency_hz, snr_db, preset,"
                    " state, detail FROM messages ORDER BY at DESC, id DESC LIMIT ?",
                    (-1 if limit is None else limit,),
                ).fetchall()
            finally:
                link.close()
        except (sqlite3.Error, OSError):
            return []
        keys = ("id", "at", "direction", "callsign", "text", "frequency_hz", "snr_db", "preset")
        rows = []
        for row in reversed(found):
            item = dict(zip(keys, row[:8], strict=True))
            item["state"] = row[8]
            try:
                item["detail"] = json.loads(row[9])
            except ValueError:
                item["detail"] = {}
            rows.append(item)
        return rows

    def clear(self) -> int:
        """Forget every Message; how many there were."""
        link = self._connect(create=False)
        if link is None:
            return 0
        try:
            with link:
                return link.execute("DELETE FROM messages").rowcount
        finally:
            link.close()

    def export_csv(self) -> bytes:
        """Every Message as a CSV that opens in a spreadsheet, French ones included."""
        return csv_of(self.rows())


def csv_of(rows: list[dict]) -> bytes:
    """UTF-8 with a byte order mark, separated by `;`, in the order given."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        when = datetime.fromtimestamp(row["at"], UTC).strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow(
            [
                when,
                row["direction"],
                _safe(row["callsign"]),
                _safe(row["text"]),
                _number(row["frequency_hz"]),
                _number(row["snr_db"]),  # a negative number is a number, not a formula
                row["preset"],
                row["state"],
            ]
        )
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.1f}"


def _safe(cell) -> str:
    """The text of a cell, made harmless: what other stations send is not to be trusted, and a
    spreadsheet runs a cell that starts with `=`, `+`, `-` or `@`."""
    text = "" if cell is None else str(cell)
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def as_conversation_item(row: dict) -> dict:
    """A Message of the history as the page shows the Messages of the conversation."""
    detail, common = row["detail"], {"id": f"h{row['id']}", "at": row["at"], "text": row["text"]}
    if row["direction"] == "sent":
        return {
            "kind": "sent",
            **common,
            "status": row["state"],
            "fragments": detail.get("fragments", 1),
            "copies": detail.get("copies", 1),
            "frequency_hz": row["frequency_hz"],
            "airtime_seconds": detail.get("airtime_seconds", 0.0),
            "error": detail.get("error"),
        }
    heard = {"frequency_hz": row["frequency_hz"], "snr_db": row["snr_db"]}
    if row["state"] == "incomplete":
        return {
            "kind": "incomplete",
            "id": common["id"],
            "at": row["at"],
            "parts": detail.get("parts", []),
            "missing": detail.get("missing", []),
            "total": detail.get("total", 0),
            **heard,
        }
    return {"kind": "received", **common, **heard}

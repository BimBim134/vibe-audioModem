"""The conversation: what was sent and what was heard, in one line of time, for the page."""

from dataclasses import dataclass

from vibemodem.app.heard import Arriving, Heard, Undecoded


@dataclass
class SentEntry:
    """A Message sent: it changes as it is played (sending, then sent, cancelled or failed)."""

    id: int
    text: str
    at: float  # when it began to be played: epoch seconds
    status: str
    fragments: int
    copies: int
    frequency_hz: float  # of its lowest tone
    airtime_seconds: float
    error: str | None = None


def _sent(entry: SentEntry) -> dict:
    return {
        "kind": "sent",
        "id": f"s{entry.id}",
        "at": entry.at,
        "text": entry.text,
        "status": entry.status,
        "fragments": entry.fragments,
        "copies": entry.copies,
        "frequency_hz": entry.frequency_hz,
        "airtime_seconds": entry.airtime_seconds,
        "error": entry.error,
    }


def _heard(item: Heard) -> dict:
    common = {"at": item.heard_at, "frequency_hz": item.frequency_hz, "snr_db": item.snr_db}
    if item.complete:
        return {"kind": "received", "id": f"r{item.number}", "text": item.text, **common}
    return {
        "kind": "incomplete",
        "id": f"i{item.msg_id}-{item.total}",
        "parts": [[offset, text] for offset, text in item.parts],
        "missing": list(item.missing),
        "total": item.total,
        **common,
    }


def _lost(item: Undecoded) -> dict:
    return {
        "kind": "lost",
        "id": f"l{round(item.heard_at * 10)}-{round(item.frequency_hz)}",
        "at": item.heard_at,
        "frequency_hz": item.frequency_hz,
    }


def _arriving(item: Arriving) -> dict:
    return {
        "kind": "arriving",
        "id": f"a{round(item.frequency_hz / 25)}",  # one per place in the band, whatever the moment
        "at": item.heard_at,
        "frequency_hz": item.frequency_hz,
    }


def build_conversation(
    sent: list[SentEntry],
    heard: list[Heard],
    lost: list[Undecoded],
    arriving: list[Arriving] = (),
) -> list[dict]:
    """Everything, oldest first. Each item has a `kind` (sent, received, incomplete, lost or
    arriving), an `id` that stays the same while the item does, and the time `at` it began."""
    items = [_sent(e) for e in sent] + [_heard(h) for h in heard] + [_lost(u) for u in lost]
    items += [_arriving(a) for a in arriving]
    return sorted(items, key=lambda item: item["at"])

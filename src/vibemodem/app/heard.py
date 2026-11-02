"""What the application tells about what it heard: Messages, their quality, lost Signals."""

from dataclasses import dataclass

from vibemodem.core import mfsk, presets
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.mfsk import FIRST_TONE_HZ
from vibemodem.core.modem import Reception


@dataclass(frozen=True)
class Quality:
    """How one Fragment was received."""

    snr_db: float | None
    frequency_hz: float | None  # of the lowest tone
    sync_score: float | None
    at: float  # when the sound was heard: epoch seconds at the start of its Frame

    @classmethod
    def of(cls, reception: Reception, at: float) -> "Quality":
        offset = reception.frequency_offset_hz
        return cls(
            snr_db=reception.snr_db,
            frequency_hz=None if offset is None else FIRST_TONE_HZ + offset,
            sync_score=reception.sync_score,
            at=at,
        )


def summarize(parts: dict[int, Quality]) -> Quality:
    """How a Message was received, from its Fragments: the mean SNR, the frequency of the first
    Fragment (of the first one heard, if the very first is missing), the lowest synchronisation
    score (the weakest link) and when the last Fragment was heard."""
    known = [parts[index] for index in sorted(parts)]
    snrs = [q.snr_db for q in known if q.snr_db is not None]
    scores = [q.sync_score for q in known if q.sync_score is not None]
    frequencies = [q.frequency_hz for q in known if q.frequency_hz is not None]
    return Quality(
        snr_db=sum(snrs) / len(snrs) if snrs else None,
        frequency_hz=frequencies[0] if frequencies else None,
        sync_score=min(scores) if scores else None,
        at=max((q.at for q in known), default=0.0),
    )


@dataclass(frozen=True)
class Heard:
    """A Message heard: whole, or only in part (`text` is then None and `parts` shows what)."""

    number: int | None  # the order of arrival of a whole Message
    complete: bool
    msg_id: int
    total: int  # of Fragments
    text: str | None
    parts: list[tuple[int, str]]  # (offset in bytes, text) of each stretch heard of a part Message
    missing: tuple[int, ...]
    heard_at: float  # when the last Fragment was heard: epoch seconds, by the audio clock
    snr_db: float | None  # mean over the Fragments, in a 2,500 Hz reference bandwidth
    frequency_hz: float | None  # of the lowest tone, in the first Fragment heard
    offset_hz: float | None  # of that frequency from the default one
    sync_score: float | None  # the lowest of the Fragments'


@dataclass(frozen=True)
class Undecoded:
    """A Signal that was found whole in the audio but whose Message could not be read."""

    heard_at: float
    frequency_hz: float
    sync_score: float


@dataclass(frozen=True)
class SpectrumRows:
    """Rows of the spectrum of the sound heard, newest last, numbered from `first`."""

    first: int
    next: int  # the number to ask for to get only newer rows
    rows: list[list[int]]  # dB, rounded, one cell per bin


@dataclass(frozen=True)
class Tolerance:
    """How alike two sightings of one Signal are, in two passes of the window."""

    seconds: float  # two symbols
    hertz: float  # a tone spacing
    frame_seconds: float
    preamble_samples: int

    @classmethod
    def of(cls, preset: str, frame_samples: int) -> "Tolerance":
        symbol_ms = presets.profile(preset).symbol_ms
        return cls(
            seconds=2 * symbol_ms / 1000,
            hertz=1000 / symbol_ms,
            frame_seconds=frame_samples / SAMPLE_RATE,
            preamble_samples=round(mfsk.PREAMBLE_SYMBOLS * symbol_ms / 1000 * SAMPLE_RATE),
        )


def alike(at: float, hz: float, other_at: float, other_hz: float, tolerance: Tolerance) -> bool:
    """Whether two sightings, in two passes, are of one Signal."""
    return abs(at - other_at) <= tolerance.seconds and abs(hz - other_hz) <= tolerance.hertz

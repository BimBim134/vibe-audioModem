"""A Message as a Transmission of Frames, and the Messages in a recording.

The sender puts one Fragment in each Frame, one after the other, each with its own Preamble,
so a Frame can be found and decoded on its own. It can send the whole set of Fragments several
times (copies), each copy starting at another Fragment, so that a fade that hides some Frames
of one copy is unlikely to hide the same Fragments of the next. The receiver finds every Frame
in a recording and hands the Fragments to a `Reassembler`.
"""

from dataclasses import dataclass, field

import numpy as np

from vibemodem.core import presets
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import (
    FRAGMENT_CAPACITY,
    MAX_FRAGMENTS,
    MAX_MESSAGE_BYTES,
    Complete,
    Fragment,
    Incomplete,
    Reassembler,
    fragment_count,
    split,
)
from vibemodem.core.modem import Modem

MAX_COPIES = 8
MAX_TRANSMISSION_SECONDS = 30 * 60


class MessageTooLong(ValueError):
    """The Message would make a Transmission longer than the ceiling, or than 255 Fragments."""


@dataclass(frozen=True)
class Received:
    complete: list[Complete] = field(default_factory=list)
    incomplete: list[Incomplete] = field(default_factory=list)


def _sending_order(total: int, copy: int, copies: int) -> list[int]:
    start = round(copy * total / copies)
    return [(start + position) % total for position in range(total)]


def frame_seconds(modem: Modem, preset: str) -> float:
    """How long one Frame lasts in a Preset: they all last the same."""
    return modem.modulate(Fragment(0, 0, 1, b"").pack(), preset).size / SAMPLE_RATE


def airtime_seconds(message_length: int, seconds_per_frame: float, copies: int = 1) -> float:
    """How long the Transmission of a Message of `message_length` bytes lasts, with no silence."""
    return fragment_count(message_length) * copies * seconds_per_frame


def _fragments_allowed(samples_per_frame: int, copies: int) -> int:
    """The most Fragments a Message may have: the ceiling counted in whole samples, one rule
    for what `transmit` accepts and what `max_message_bytes` says."""
    in_the_ceiling = MAX_TRANSMISSION_SECONDS * SAMPLE_RATE // (copies * samples_per_frame)
    return min(MAX_FRAGMENTS, in_the_ceiling)


def max_message_bytes(seconds_per_frame: float, copies: int = 1) -> int:
    """The largest Message that fits in the ceiling (and in 255 Fragments), `copies` times over."""
    samples_per_frame = round(seconds_per_frame * SAMPLE_RATE)
    return _fragments_allowed(samples_per_frame, copies) * FRAGMENT_CAPACITY


def _faster_presets(preset: str, message_length: int, seconds_per_frame: float, copies: int):
    """The Presets with shorter symbols that would carry the Message, with their limits."""
    try:
        current_symbol_ms = presets.profile(preset).symbol_ms
    except ValueError:
        return []  # not one of the three Presets: nothing to compare with
    carriers = []
    for name, profile in presets.PRESETS.items():
        if profile.symbol_ms < current_symbol_ms:
            # A Frame is a number of symbols: its duration follows the symbol duration.
            scaled = seconds_per_frame * profile.symbol_ms / current_symbol_ms
            if message_length <= max_message_bytes(scaled, copies):
                carriers.append(f"{name} (up to {max_message_bytes(scaled, copies)} bytes)")
    return carriers


def _refusal(message_length: int, preset: str, copies: int, seconds_per_frame: float) -> str:
    airtime = airtime_seconds(message_length, seconds_per_frame, copies)
    advice = [
        f"at most {max_message_bytes(seconds_per_frame, copies)} bytes fit here; "
        "send a shorter Message"
    ]
    if copies > 1 and airtime / copies <= MAX_TRANSMISSION_SECONDS:
        advice.append("use fewer copies")
    if faster := _faster_presets(preset, message_length, seconds_per_frame, copies):
        advice.append("or use a faster Preset: " + ", ".join(faster))
    return (
        f"a Message of {message_length} bytes sent {copies} time(s) in the {preset!r} Preset "
        f"would take {airtime:.0f} s, over the ceiling of {MAX_TRANSMISSION_SECONDS / 60:g} "
        f"minutes: {'; '.join(advice)}."
    )


def check_copies(copies: int) -> None:
    if not isinstance(copies, int) or isinstance(copies, bool) or not 1 <= copies <= MAX_COPIES:
        raise ValueError(f"copies must be a whole number from 1 to {MAX_COPIES}")


def _too_many_fragments(message_length: int) -> str | None:
    count = fragment_count(message_length)
    if count <= MAX_FRAGMENTS:
        return None
    return (
        f"a Message of {message_length} bytes needs {count} Fragments, more than the "
        f"{MAX_FRAGMENTS} a Message may have: send a shorter Message "
        f"({MAX_MESSAGE_BYTES} bytes at most)"
    )


def explain_refusal(
    message_length: int, preset: str, copies: int, samples_per_frame: int
) -> str | None:
    """Why a Message may not be sent as asked, with what to do instead; None when it may."""
    if reason := _too_many_fragments(message_length):
        return reason
    if fragment_count(message_length) > _fragments_allowed(samples_per_frame, copies):
        return _refusal(message_length, preset, copies, samples_per_frame / SAMPLE_RATE)
    return None


def transmit(
    modem: Modem, message: bytes, preset: str, *, msg_id: int, copies: int = 1
) -> np.ndarray:
    """The audio of a Transmission that carries the Message `copies` times over."""
    check_copies(copies)
    if reason := _too_many_fragments(len(message)):
        raise MessageTooLong(reason)
    count = fragment_count(len(message))
    fragments = split(message, msg_id)
    # Every Frame lasts the same: the first one tells whether the Transmission fits, and the
    # rest are made only if it does. A copy sends the same Frames again.
    frames = [modem.modulate(fragments[0].pack(), preset)]
    if reason := explain_refusal(len(message), preset, copies, frames[0].size):
        raise MessageTooLong(reason)
    frames += [modem.modulate(fragment.pack(), preset) for fragment in fragments[1:]]
    order = [i for copy in range(copies) for i in _sending_order(count, copy, copies)]
    return np.concatenate([frames[index] for index in order])


def receive(modem: Modem, samples: np.ndarray, reassembler: Reassembler | None = None) -> Received:
    """The Messages in a recording: the complete ones and, if it is over, the incomplete ones.

    A Transmission longer than a recording is received in pieces by giving each recording the
    same `reassembler`; the Messages heard in part are then left in it, and `finish` reports
    them when the last recording is over.
    """
    ends_here = reassembler is None
    reassembler = reassembler or Reassembler()
    complete = []
    for reception in modem.demodulate(samples):
        fragment = Fragment.unpack(reception.message)
        if fragment and (done := reassembler.add(fragment)):
            complete.append(done)
    return Received(complete=complete, incomplete=reassembler.finish() if ends_here else [])

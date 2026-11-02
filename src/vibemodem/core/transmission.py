"""A Message as a Transmission of Frames, and the Messages in a recording.

The sender puts one Fragment in each Frame, one after the other, each with its own Preamble,
so a Frame can be found and decoded on its own. It can send the whole set of Fragments several
times (copies), each copy starting at another Fragment, so that a fade that hides some Frames
of one copy is unlikely to hide the same Fragments of the next. The receiver finds every Frame
in a recording and hands the Fragments to a `Reassembler`.
"""

from dataclasses import dataclass, field

import numpy as np

from vibemodem.core.message import Complete, Fragment, Incomplete, Reassembler, split
from vibemodem.core.modem import Modem

MAX_COPIES = 8


@dataclass(frozen=True)
class Received:
    complete: list[Complete] = field(default_factory=list)
    incomplete: list[Incomplete] = field(default_factory=list)


def _sending_order(total: int, copy: int, copies: int) -> list[int]:
    start = round(copy * total / copies)
    return [(start + position) % total for position in range(total)]


def transmit(
    modem: Modem, message: bytes, preset: str, *, msg_id: int, copies: int = 1
) -> np.ndarray:
    """The audio of a Transmission that carries the Message `copies` times over."""
    if not isinstance(copies, int) or isinstance(copies, bool) or not 1 <= copies <= MAX_COPIES:
        raise ValueError(f"copies must be a whole number from 1 to {MAX_COPIES}")
    fragments = split(message, msg_id)
    frames = [
        modem.modulate(fragments[index].pack(), preset)
        for copy in range(copies)
        for index in _sending_order(len(fragments), copy, copies)
    ]
    return np.concatenate(frames)


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

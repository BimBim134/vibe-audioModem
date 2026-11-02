"""The Message protocol: a Message split into Fragments, one Fragment per Frame.

A Fragment is sent as the body of a Frame: three header bytes (the Message identifier, the index
of the Fragment and the number of Fragments) and up to 17 bytes of the Message. The Frame
carries the length of its body and a CRC-32 over it, so a Fragment that arrives has been
checked, header included. The `Reassembler` puts Fragments back into Messages, delivers each
Message once however many copies are heard, and reports a Message with missing Fragments as
incomplete, never as a shorter Message.
"""

import random
from collections import OrderedDict, deque
from dataclasses import dataclass

from vibemodem.core import frame

HEADER_BYTES = 3
FRAGMENT_CAPACITY = frame.MESSAGE_CAPACITY - HEADER_BYTES
MAX_FRAGMENTS = 255
MAX_MESSAGE_BYTES = MAX_FRAGMENTS * FRAGMENT_CAPACITY
MEMORY = 64  # finished Messages remembered to ignore their copies, and Messages kept open


@dataclass(frozen=True)
class Fragment:
    msg_id: int
    index: int
    total: int
    payload: bytes

    def pack(self) -> bytes:
        """The body of the Frame that carries this Fragment."""
        return bytes([self.msg_id, self.index, self.total]) + self.payload

    @classmethod
    def unpack(cls, body: bytes) -> "Fragment | None":
        """The Fragment in a Frame's body, or None when the header does not make sense."""
        if len(body) < HEADER_BYTES:
            return None
        msg_id, index, total = body[0], body[1], body[2]
        payload = body[HEADER_BYTES:]
        if not 0 <= index < total or len(payload) > FRAGMENT_CAPACITY:
            return None
        if index < total - 1 and len(payload) != FRAGMENT_CAPACITY:
            return None  # only the last Fragment may be short
        if index == total - 1 and total > 1 and not payload:
            return None
        return cls(msg_id, index, total, payload)


@dataclass(frozen=True)
class Complete:
    msg_id: int
    message: bytes


@dataclass(frozen=True)
class Incomplete:
    """What was heard of a Message that was not heard in full: only Fragments that were checked."""

    msg_id: int
    total: int
    fragments: dict[int, bytes]

    @property
    def missing(self) -> tuple[int, ...]:
        return tuple(index for index in range(self.total) if index not in self.fragments)

    def runs(self) -> list[tuple[int, bytes]]:
        """(offset in the Message, bytes) for each stretch of consecutive Fragments received."""
        runs: list[tuple[int, bytes]] = []
        previous = None
        for index in sorted(self.fragments):
            if previous is not None and index == previous + 1:
                offset, data = runs[-1]
                runs[-1] = (offset, data + self.fragments[index])
            else:
                runs.append((index * FRAGMENT_CAPACITY, self.fragments[index]))
            previous = index
        return runs


def fragment_count(length: int) -> int:
    """How many Fragments a Message of `length` bytes needs (an empty Message needs one)."""
    return max(1, -(-length // FRAGMENT_CAPACITY))


def split(message: bytes, msg_id: int) -> list[Fragment]:
    """The Fragments of a Message (an empty Message is one empty Fragment)."""
    if len(message) > MAX_MESSAGE_BYTES:
        raise ValueError(
            f"a Message holds at most {MAX_MESSAGE_BYTES} bytes ({MAX_FRAGMENTS} Fragments of "
            f"{FRAGMENT_CAPACITY}), got {len(message)}"
        )
    if not 0 <= msg_id < 256:
        raise ValueError("a Message identifier is one byte, from 0 to 255")
    total = fragment_count(len(message))
    return [
        Fragment(msg_id, index, total, message[index * FRAGMENT_CAPACITY :][:FRAGMENT_CAPACITY])
        for index in range(total)
    ]


def random_message_id(previous: int | None = None, rng: random.Random | None = None) -> int:
    """A Message identifier different from the previous one."""
    rng = rng or random.SystemRandom()
    while True:
        msg_id = rng.randrange(256)
        if msg_id != previous:
            return msg_id


class Reassembler:
    """Puts Fragments back into Messages, in any order and however many times they arrive.

    A Message is known by its identifier and its number of Fragments. A Fragment whose index
    was already heard with other content starts a new Message in place of the one being built,
    which is then reported as incomplete.
    """

    def __init__(self, max_given_up: int | None = None):
        """`max_given_up` bounds the Messages given up on that are kept to be reported (the
        oldest are forgotten); by default none is forgotten, which suits a reception that ends
        with `finish`. A reception that never ends should bound them."""
        self._open: OrderedDict[tuple[int, int], dict[int, bytes]] = OrderedDict()
        self._done: OrderedDict[tuple[int, int], None] = OrderedDict()
        self._dropped: deque[Incomplete] = deque(maxlen=max_given_up)

    def add(self, fragment: Fragment) -> Complete | None:
        """The Message this Fragment completes, if it does and it was not delivered before."""
        key = (fragment.msg_id, fragment.total)
        if key in self._done:
            return None
        heard = self._open.setdefault(key, {})
        self._open.move_to_end(key)  # the Message that is least recently heard goes first
        if fragment.index in heard and heard[fragment.index] != fragment.payload:
            self._dropped.append(Incomplete(fragment.msg_id, fragment.total, heard))
            heard = self._open[key] = {}
        heard[fragment.index] = fragment.payload
        if len(heard) < fragment.total:
            self._bound_open()
            return None
        del self._open[key]
        self._done[key] = None
        if len(self._done) > MEMORY:
            self._done.popitem(last=False)
        message = b"".join(heard[index] for index in range(fragment.total))
        return Complete(fragment.msg_id, message)

    def _bound_open(self) -> None:
        while len(self._open) > MEMORY:
            (msg_id, total), heard = self._open.popitem(last=False)
            self._dropped.append(Incomplete(msg_id, total, heard))

    def pending(self) -> list[Incomplete]:
        """The Messages heard in part so far, without ending the reception."""
        incomplete = list(self._dropped)
        incomplete += [Incomplete(i, t, dict(heard)) for (i, t), heard in self._open.items()]
        return incomplete

    def finish(self) -> list[Incomplete]:
        """The Messages heard in part, once the reception is over; they are forgotten."""
        incomplete = list(self._dropped)
        incomplete += [Incomplete(i, t, heard) for (i, t), heard in self._open.items()]
        self._dropped.clear()
        self._open.clear()
        return incomplete

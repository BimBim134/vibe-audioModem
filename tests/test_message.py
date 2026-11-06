"""The Message protocol: a Message split into Fragments, and Fragments put back together."""

import random

import pytest

from vibemodem.core import frame
from vibemodem.core.message import (
    FRAGMENT_CAPACITY,
    MAX_FRAGMENTS,
    MAX_MESSAGE_BYTES,
    MEMORY,
    Complete,
    Fragment,
    Incomplete,
    Reassembler,
    random_message_id,
    split,
)


def message_of(size: int, seed: int = 0) -> bytes:
    return random.Random(seed).randbytes(size)


def deliver(reassembler: Reassembler, fragments) -> list[Complete]:
    return [done for fragment in fragments if (done := reassembler.add(fragment))]


def test_a_fragment_and_its_header_fit_in_one_frame():
    assert FRAGMENT_CAPACITY == 17
    assert FRAGMENT_CAPACITY + 3 == frame.MESSAGE_CAPACITY
    assert MAX_FRAGMENTS == 255 and MAX_MESSAGE_BYTES == 255 * 17 == 4335


@pytest.mark.parametrize(
    "size, fragments", [(0, 1), (1, 1), (17, 1), (18, 2), (255, 15), (4335, 255)]
)
def test_a_message_is_split_into_as_few_fragments_as_it_needs(size, fragments):
    parts = split(message_of(size), msg_id=7)
    assert len(parts) == fragments
    assert [p.index for p in parts] == list(range(fragments))
    assert {p.total for p in parts} == {fragments} and {p.msg_id for p in parts} == {7}


def test_a_message_too_long_for_255_fragments_is_refused():
    with pytest.raises(ValueError, match="4335"):
        split(message_of(MAX_MESSAGE_BYTES + 1), msg_id=0)


@pytest.mark.parametrize("size", [0, 1, 16, 17, 18, 30, 31, 32, 255, 1000, 4335])
def test_every_size_makes_the_round_trip_through_the_bytes_of_the_frames(size):
    message = message_of(size, seed=size)
    on_the_air = [part.pack() for part in split(message, msg_id=3)]
    assert all(len(sent) <= frame.MESSAGE_CAPACITY for sent in on_the_air)
    received = Reassembler()
    done = deliver(received, [Fragment.unpack(sent) for sent in on_the_air])
    assert done == [Complete(msg_id=3, message=message)]
    assert received.finish() == []


def test_the_header_is_the_identifier_the_index_and_the_total():
    first, second = split(b"x" * 20, msg_id=200)
    assert first.pack()[:3] == bytes([200, 0, 2]) and second.pack()[:3] == bytes([200, 1, 2])


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        bytes([1, 0]),  # no total
        bytes([1, 0, 0]),  # a Message of no Fragments
        bytes([1, 2, 2]) + b"x",  # index beyond the total
        bytes([1, 0, 2]) + b"x" * 16,  # a Fragment that is not the last must be full
        bytes([1, 0, 1]) + b"x" * 18,  # more than a Fragment holds
        bytes([1, 1, 2]),  # an empty last Fragment of a longer Message
    ],
)
def test_bytes_that_are_no_fragment_are_refused(bad):
    assert Fragment.unpack(bad) is None


def test_fragments_in_any_order_make_one_message():
    parts = split(message_of(100), msg_id=9)
    random.Random(1).shuffle(parts)
    assert [d.message for d in deliver(Reassembler(), parts)] == [message_of(100)]


def test_repeated_copies_of_a_message_are_delivered_once():
    parts = split(message_of(60), msg_id=9)
    received = Reassembler()
    assert len(deliver(received, parts + parts + parts)) == 1
    assert received.finish() == []


def test_a_copy_that_arrives_late_fills_the_gap_of_the_first():
    parts = split(message_of(60), msg_id=9)
    received = Reassembler()
    assert deliver(received, parts[:1] + parts[2:]) == []
    assert len(deliver(received, parts)) == 1


def test_a_missing_fragment_is_reported_as_an_incomplete_message_not_a_short_one():
    parts = split(message_of(60, seed=4), msg_id=9)
    received = Reassembler()
    assert deliver(received, [parts[0], parts[1], parts[3]]) == []
    (incomplete,) = received.finish()
    assert isinstance(incomplete, Incomplete)
    assert (incomplete.msg_id, incomplete.total, incomplete.missing) == (9, 4, (2,))
    assert incomplete.fragments == {0: parts[0].payload, 1: parts[1].payload, 3: parts[3].payload}
    assert not hasattr(incomplete, "message")
    assert received.finish() == []  # reported once


def test_what_was_received_of_an_incomplete_message_is_laid_out_with_its_gap():
    message = message_of(60, seed=4)
    parts = split(message, msg_id=9)
    received = Reassembler()
    deliver(received, [parts[0], parts[1], parts[3]])
    (incomplete,) = received.finish()
    assert incomplete.runs() == [(0, message[:34]), (51, message[51:])]


def test_a_message_with_nothing_missing_after_the_end_is_not_incomplete():
    received = Reassembler()
    deliver(received, split(b"short", msg_id=1))
    assert received.finish() == []


def test_the_same_identifier_with_other_content_is_another_message():
    old = split(message_of(40, seed=1), msg_id=5)
    new = split(message_of(40, seed=2), msg_id=5)
    received = Reassembler()
    deliver(received, old[:1])
    done = deliver(received, new)
    assert [d.message for d in done] == [message_of(40, seed=2)]
    (lost,) = received.finish()  # what was heard of the first one is not forgotten
    assert lost.msg_id == 5 and lost.missing == (1, 2)


def test_two_messages_in_flight_are_kept_apart_by_identifier_and_total():
    one, two = split(message_of(40, seed=1), msg_id=1), split(message_of(40, seed=2), msg_id=2)
    mixed = [one[0], two[0], one[1], two[1], one[2], two[2]]
    assert [d.msg_id for d in deliver(Reassembler(), mixed)] == [1, 2]


def test_a_finished_message_is_remembered_for_a_while_not_for_ever():
    received = Reassembler()
    first = split(b"first", msg_id=0)
    assert len(deliver(received, first)) == 1
    for msg_id in range(1, MEMORY + 1):  # MEMORY other messages push it out
        deliver(received, split(b"other", msg_id=msg_id))
    assert len(deliver(received, first)) == 1


def test_a_receiver_that_hears_unfinished_messages_for_ever_keeps_bounded_memory():
    received = Reassembler()
    for msg_id in range(256):
        for total in range(2, 10):
            received.add(Fragment(msg_id, 0, total, b"x" * FRAGMENT_CAPACITY))
    assert len(received.finish()) == 256 * 8  # none is forgotten without being reported


def test_the_message_that_is_still_being_heard_is_not_the_one_given_up_on():
    received = Reassembler()
    busy = Fragment(0, 0, 3, b"x" * FRAGMENT_CAPACITY)
    received.add(busy)
    for msg_id in range(1, MEMORY):  # fills the memory with the Messages heard after it
        received.add(Fragment(msg_id, 0, 3, b"y" * FRAGMENT_CAPACITY))
    received.add(Fragment(0, 1, 3, b"x" * FRAGMENT_CAPACITY))  # the first one is heard again
    received.add(Fragment(200, 0, 3, b"z" * FRAGMENT_CAPACITY))  # one too many: someone goes
    assert received.add(Fragment(0, 2, 3, b"end")) == Complete(0, b"x" * 34 + b"end")


def test_random_identifiers_differ_from_the_previous_one():
    rng = random.Random(0)
    ids = [random_message_id(previous=3, rng=rng) for _ in range(300)]
    assert 3 not in ids and all(0 <= i < 256 for i in ids) and len(set(ids)) > 100


def test_what_is_still_incomplete_can_be_looked_at_without_ending_the_reception():
    received = Reassembler()
    parts = split(message_of(60), msg_id=9)
    deliver(received, parts[:2])
    (pending,) = received.pending()
    assert pending.missing == (2, 3)
    assert received.pending()[0].missing == (2, 3)  # looking changed nothing
    deliver(received, parts[2:])  # the rest arrives: nothing is pending any more
    assert received.pending() == [] and received.finish() == []


def test_the_messages_given_up_on_can_be_bounded_for_a_reception_that_never_ends():
    received = Reassembler(max_given_up=2)
    for msg_id in range(5):  # each is replaced by a Message with other content, and given up
        received.add(Fragment(msg_id, 0, 2, b"a" * FRAGMENT_CAPACITY))
        received.add(Fragment(msg_id, 0, 2, b"b" * FRAGMENT_CAPACITY))
    given_up = [p for p in received.pending() if p.fragments[0].startswith(b"a")]
    assert len(given_up) == 2 and [p.msg_id for p in given_up] == [3, 4]


def test_a_new_message_that_reuses_the_identifier_of_one_delivered_is_delivered_too():
    received = Reassembler()
    assert len(deliver(received, split(b"first message", msg_id=7))) == 1
    done = deliver(received, split(b"another one!", msg_id=7))  # same identifier and size class
    assert [d.message for d in done] == [b"another one!"]


def test_the_copies_of_a_delivered_message_are_still_ignored_among_others_of_the_same_id():
    received = Reassembler()
    message = split(b"original", msg_id=7)
    deliver(received, message)
    deliver(received, split(b"newcomer!", msg_id=7))  # takes the identifier over
    assert deliver(received, split(b"newcomer!", msg_id=7)) == []  # its copy, not new
    assert [d.message for d in deliver(received, message)] == [b"original"]  # and back again


def test_a_message_that_differs_only_in_a_later_fragment_is_known_for_another_when_that_one_shows():
    received = Reassembler()
    first = split(b"A" * 17 + b"first end", msg_id=3)
    second = split(b"A" * 17 + b"other end", msg_id=3)
    deliver(received, first)
    assert received.add(second[0]) is None  # the same first Fragment: taken for a copy
    assert (
        received.add(second[1]) is None
    )  # the last differs: a new Message, still short of its first
    assert received.add(second[0]).message == b"A" * 17 + b"other end"  # which comes again

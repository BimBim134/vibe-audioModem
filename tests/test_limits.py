"""Airtime of a Transmission, and how large a Message a Preset may send in 30 minutes."""

import numpy as np
import pytest

from tests.fake_modems import RecordingModem
from vibemodem.core import transmission
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import MAX_FRAGMENTS, MAX_MESSAGE_BYTES
from vibemodem.core.transmission import (
    MAX_TRANSMISSION_SECONDS,
    MessageTooLong,
    airtime_seconds,
    frame_seconds,
    max_message_bytes,
    transmit,
)
from vibemodem.core.turbo_modem import TurboModem

PRESETS = ["max-range", "standard", "fast"]


class LongFrames(RecordingModem):
    """Frames of a given length of silence, to try the ceiling without minutes of real audio."""

    def __init__(self, seconds):
        super().__init__()
        self.samples = round(seconds * SAMPLE_RATE)

    def modulate(self, message, preset):
        self.messages.append(message)
        return np.zeros(self.samples)


def test_the_ceiling_is_thirty_minutes():
    assert MAX_TRANSMISSION_SECONDS == 1800


@pytest.mark.parametrize(
    "preset, seconds", [("max-range", 54.4), ("standard", 13.6), ("fast", 6.8)]
)
def test_a_frame_lasts_as_long_as_its_preamble_and_symbols(preset, seconds):
    assert frame_seconds(TurboModem(preset=preset), preset) == pytest.approx(seconds)


@pytest.mark.parametrize("copies", [1, 2])
@pytest.mark.parametrize("size", [0, 1, 17, 18, 40, 340])
@pytest.mark.parametrize("preset", PRESETS)
def test_the_estimate_is_the_duration_of_the_audio_that_is_generated(preset, size, copies):
    modem = TurboModem(preset=preset)
    one_frame = frame_seconds(modem, preset)
    if size > max_message_bytes(one_frame, copies):
        pytest.skip("this Message is over the ceiling in this Preset: see the refusal tests")
    audio = transmit(modem, bytes(size), preset, msg_id=1, copies=copies)
    estimate = airtime_seconds(size, one_frame, copies)
    assert estimate == pytest.approx(audio.size / SAMPLE_RATE, abs=0, rel=1e-12)  # to the sample


@pytest.mark.parametrize(
    "preset, copies, limit",
    [
        ("max-range", 1, 561),
        ("standard", 1, 2244),
        ("fast", 1, 4335),
        ("max-range", 2, 272),
        ("standard", 2, 1122),
        ("fast", 2, 2244),
        ("max-range", 8, 68),
        ("fast", 8, 561),
    ],
)
def test_the_largest_message_of_each_preset_is_recorded(preset, copies, limit):
    seconds = frame_seconds(TurboModem(preset=preset), preset)
    assert max_message_bytes(seconds, copies) == limit
    assert airtime_seconds(limit, seconds, copies) <= MAX_TRANSMISSION_SECONDS
    if limit < MAX_MESSAGE_BYTES:  # one Fragment more would pass the ceiling
        assert airtime_seconds(limit + 1, seconds, copies) > MAX_TRANSMISSION_SECONDS


def test_no_preset_may_send_more_than_255_fragments_even_if_time_remains():
    assert max_message_bytes(1.0, copies=1) == MAX_MESSAGE_BYTES == MAX_FRAGMENTS * 17


@pytest.fixture
def ceiling_of_ten_seconds(monkeypatch):
    monkeypatch.setattr(transmission, "MAX_TRANSMISSION_SECONDS", 10)


@pytest.mark.usefixtures("ceiling_of_ten_seconds")
def test_a_message_that_is_too_long_for_the_ceiling_is_refused_before_it_is_made():
    modem = LongFrames(seconds=1)  # 10 Fragments fill the ceiling: a 170-byte limit
    transmit(modem, bytes(170), "standard", msg_id=1)
    assert len(modem.messages) == 10
    modem = LongFrames(seconds=1)
    with pytest.raises(MessageTooLong):
        transmit(modem, bytes(171), "standard", msg_id=1)
    assert len(modem.messages) == 1  # only the first Frame was made, to learn its length


def test_the_refusal_says_why_and_what_to_do():
    with pytest.raises(MessageTooLong) as refusal:
        transmit(TurboModem(preset="max-range"), bytes(600), "max-range", msg_id=1)
    reason = str(refusal.value)
    assert "600 bytes" in reason and "'max-range'" in reason and "30 minutes" in reason
    assert "at most 561 bytes" in reason
    assert "shorter Message" in reason
    assert "standard" in reason and "fast" in reason  # Presets that would carry it


@pytest.mark.usefixtures("ceiling_of_ten_seconds")
def test_the_refusal_suggests_fewer_copies_when_that_is_enough():
    with pytest.raises(MessageTooLong, match="fewer copies"):
        transmit(LongFrames(seconds=1), bytes(100), "standard", msg_id=1, copies=2)


@pytest.mark.usefixtures("ceiling_of_ten_seconds")
def test_copies_count_towards_the_ceiling():
    transmit(LongFrames(seconds=1), bytes(100), "standard", msg_id=1, copies=1)  # 6 s
    with pytest.raises(MessageTooLong):
        transmit(LongFrames(seconds=1), bytes(100), "standard", msg_id=1, copies=2)  # 12 s


def test_a_message_beyond_255_fragments_is_refused_the_same_way():
    with pytest.raises(MessageTooLong, match="4335"):
        transmit(LongFrames(seconds=0.01), bytes(MAX_MESSAGE_BYTES + 1), "fast", msg_id=1)


def test_the_refusal_is_a_value_error():
    assert issubclass(MessageTooLong, ValueError)


def test_a_bad_number_of_copies_is_refused_before_the_size_is_looked_at():
    with pytest.raises(ValueError, match="copies") as refusal:
        transmit(LongFrames(seconds=0.01), bytes(MAX_MESSAGE_BYTES + 1), "fast", msg_id=1, copies=0)
    assert not isinstance(refusal.value, MessageTooLong)


@pytest.mark.usefixtures("ceiling_of_ten_seconds")
def test_a_modem_that_is_built_for_no_known_preset_is_refused_without_a_suggestion():
    modem = LongFrames(seconds=1)
    with pytest.raises(MessageTooLong) as refusal:
        transmit(modem, bytes(200), "custom", msg_id=1)
    assert "shorter Message" in str(refusal.value) and "faster Preset" not in str(refusal.value)


@pytest.mark.usefixtures("ceiling_of_ten_seconds")
def test_the_advertised_maximum_is_what_transmit_accepts():
    for copies in (1, 2, 3):
        longest = max_message_bytes(1.0, copies)
        transmit(LongFrames(seconds=1), bytes(longest), "standard", msg_id=1, copies=copies)
        with pytest.raises(MessageTooLong):
            transmit(LongFrames(seconds=1), bytes(longest + 1), "standard", msg_id=1, copies=copies)

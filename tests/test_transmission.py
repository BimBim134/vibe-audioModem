"""A Message sent as a Transmission of several Frames, and received from a recording."""

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from tests.fake_modems import RecordingModem
from vibemodem.core.baseline import BaselineModem
from vibemodem.core.message import FRAGMENT_CAPACITY, Complete, Fragment, Reassembler
from vibemodem.core.transmission import MAX_COPIES, receive, transmit

FS = 48_000
PRESET = "fast"


@pytest.fixture(scope="module")
def modem():
    return BaselineModem(preset=PRESET)


def message_of(size):
    return bytes(np.random.default_rng(size).integers(0, 256, size, dtype=np.uint8))


def frame_samples(modem):
    return modem.modulate(b"x", PRESET).size


def noisy(audio, snr_db, offset_hz=0.0, lead_in_s=2.0, seed=1):
    recording = np.concatenate([np.zeros(round(lead_in_s * FS)), audio, np.zeros(FS)])
    config = ChannelConfig(snr_db=snr_db, freq_offset_hz=offset_hz)
    return apply_channel(recording, config, seed, signal_power=float(np.mean(audio**2)))


@pytest.mark.parametrize("size", [0, 1, 16, 17, 18, 30, 31, 32, 34, 35, 255, 300])
def test_a_message_of_any_size_crosses_a_noiseless_channel_intact(modem, size):
    message = message_of(size)
    audio = transmit(modem, message, PRESET, msg_id=5)
    received = receive(modem, audio)
    assert received.complete == [Complete(msg_id=5, message=message)]
    assert received.incomplete == []


def test_a_transmission_longer_than_a_recording_is_received_in_pieces(modem):
    message = message_of(100)  # 6 Fragments
    audio = transmit(modem, message, PRESET, msg_id=8)
    cut = 3 * frame_samples(modem)
    reassembler = Reassembler()
    first = receive(modem, audio[:cut], reassembler)
    assert first.complete == [] and first.incomplete == []  # still being heard
    second = receive(modem, audio[cut:], reassembler)
    assert [c.message for c in second.complete] == [message]
    assert reassembler.finish() == []


def test_a_transmission_is_one_frame_per_fragment(modem):
    audio = transmit(modem, message_of(40), PRESET, msg_id=1)  # 3 Fragments
    assert audio.size == 3 * frame_samples(modem)


def test_a_multi_fragment_message_crosses_a_noisy_channel_at_any_start_and_frequency(modem):
    message = message_of(100)  # 6 Fragments
    audio = noisy(transmit(modem, message, PRESET, msg_id=9), snr_db=-6, offset_hz=-640)
    received = receive(modem, audio)
    assert [c.message for c in received.complete] == [message]


def test_a_lost_frame_is_reported_as_an_incomplete_message_with_what_was_received(modem):
    message = message_of(60)  # 4 Fragments
    audio = transmit(modem, message, PRESET, msg_id=4).copy()
    size = frame_samples(modem)
    audio[2 * size : 3 * size] = np.random.default_rng(3).normal(0, 1, size)  # noise, not a Frame
    received = receive(modem, audio)
    assert received.complete == []
    (incomplete,) = received.incomplete
    assert (incomplete.msg_id, incomplete.total, incomplete.missing) == (4, 4, (2,))
    assert incomplete.runs() == [(0, message[:34]), (51, message[51:])]


def test_a_second_copy_makes_up_for_a_frame_lost_in_the_first(modem):
    message = message_of(60)
    audio = transmit(modem, message, PRESET, msg_id=4, copies=2).copy()
    size = frame_samples(modem)
    audio[1 * size : 2 * size] = 0.0  # the second Frame of the first copy
    received = receive(modem, audio)
    assert [c.message for c in received.complete] == [message]
    assert received.incomplete == []


def test_copies_of_a_message_are_received_as_one_message(modem):
    audio = transmit(modem, message_of(40), PRESET, msg_id=2, copies=3)
    assert len(receive(modem, audio).complete) == 1


def test_later_copies_start_elsewhere_so_that_one_fade_does_not_hit_the_same_fragments():
    class OneValuePerFragment(RecordingModem):
        def modulate(self, message, preset):
            super().modulate(message, preset)
            return np.full(10, float(Fragment.unpack(message).index))

    audio = transmit(OneValuePerFragment(), message_of(60), "standard", msg_id=1, copies=2)
    assert audio[::10].tolist() == [0, 1, 2, 3, 2, 3, 0, 1]


def test_by_default_a_message_is_sent_once():
    modem = RecordingModem()
    transmit(modem, message_of(60), "standard", msg_id=1)
    assert len(modem.messages) == 4


@pytest.mark.parametrize("copies", [0, -1, MAX_COPIES + 1, 1.5, "2"])
def test_a_number_of_copies_that_makes_no_sense_is_refused(copies):
    with pytest.raises(ValueError, match="copies"):
        transmit(RecordingModem(), b"x", "standard", msg_id=1, copies=copies)


def test_a_recording_with_no_signal_gives_nothing(modem):
    noise = np.random.default_rng(0).normal(0, 0.1, 20 * FS)
    received = receive(modem, noise)
    assert received.complete == [] and received.incomplete == []


def test_a_fragment_is_never_larger_than_a_frame_can_carry():
    modem = RecordingModem()
    transmit(modem, message_of(500), "standard", msg_id=1)
    assert max(len(sent) for sent in modem.messages) == FRAGMENT_CAPACITY + 3


@pytest.mark.parametrize("preset", ["max-range", "standard", "fast"])
@pytest.mark.parametrize("size", [0, 5, 12, 16, 17])
def test_a_noiseless_frame_is_received_in_any_preset_with_or_without_silence_around(preset, size):
    # Without noise, the leakage of the signal into far frequencies once looked like a Preamble.
    modem = BaselineModem(preset=preset)
    sent = Fragment(3, 0, 1, message_of(size)[:size]).pack()
    audio = modem.modulate(sent, preset)
    for silence in (np.zeros(0), np.zeros(FS // 2)):
        heard = modem.demodulate(np.concatenate([silence, audio, silence]))
        assert [r.message for r in heard] == [sent]

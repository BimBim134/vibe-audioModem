"""The audio layer: devices, playing, recording, listening, and the fake that stands in."""

import numpy as np
import pytest

from tests.fake_sounddevice import FakeSounddevice
from vibemodem.core.transmission import receive, transmit
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io import audio
from vibemodem.io.audio import (
    AudioLibraryUnavailableError,
    DeviceInfo,
    FakeAudio,
    NoAudioDeviceError,
    SoundCard,
    UnsupportedAudioError,
    find_device,
)

FS = 48_000
DEVICES = [
    {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0,
     "default_samplerate": 44_100.0},
    {"name": "USB Audio CODEC", "max_input_channels": 1, "max_output_channels": 2,
     "default_samplerate": 48_000.0},
    {"name": "Built-in Output", "max_input_channels": 0, "max_output_channels": 2,
     "default_samplerate": 44_100.0},
    {"name": "USB Headset", "max_input_channels": 1, "max_output_channels": 2,
     "default_samplerate": 48_000.0},
]  # fmt: skip


@pytest.fixture
def sd():
    return FakeSounddevice(DEVICES)


@pytest.fixture
def card(sd):
    return SoundCard(load=lambda: sd)


def tone(seconds=0.25, level=0.5):
    return level * np.sin(2 * np.pi * 1000 * np.arange(round(seconds * FS)) / FS)


# Devices ------------------------------------------------------------------------------------


def test_devices_are_listed_with_what_they_can_do(card):
    devices = card.list_devices()
    assert devices[1] == DeviceInfo(1, "USB Audio CODEC", inputs=1, outputs=2, rate_hz=48_000.0)
    assert [d.index for d in devices if d.inputs] == [0, 1, 3]
    assert [d.index for d in devices if d.outputs] == [1, 2, 3]


@pytest.mark.parametrize(
    "wanted, direction, index",
    [(None, "input", None), (3, "input", 3), ("codec", "input", 1), ("built-in out", "output", 2)],
)
def test_a_device_is_chosen_by_number_or_by_part_of_its_name(card, wanted, direction, index):
    assert find_device(card.list_devices(), wanted, direction) == index


def test_a_name_that_fits_several_devices_is_refused_and_they_are_listed(card):
    with pytest.raises(NoAudioDeviceError, match="USB Audio CODEC.*USB Headset"):
        find_device(card.list_devices(), "usb", "output")


def test_a_name_that_fits_no_device_of_that_direction_is_refused(card):
    with pytest.raises(NoAudioDeviceError, match="no output device"):
        find_device(card.list_devices(), "microphone", "output")  # it only records


def test_a_number_that_is_no_device_of_that_direction_is_refused(card):
    with pytest.raises(NoAudioDeviceError, match="no input device"):
        find_device(card.list_devices(), 2, "input")


def test_a_missing_audio_library_is_reported_apart_from_a_missing_device():
    def missing():
        raise OSError("PortAudio library not found")

    with pytest.raises(AudioLibraryUnavailableError, match="PortAudio"):
        SoundCard(load=missing).list_devices()


# Playing and recording ----------------------------------------------------------------------


def test_samples_are_played_to_the_chosen_output_as_float32_at_48_khz(card, sd):
    card.play(tone(), device="codec")
    (played,) = sd.played
    assert played["device"] == 1 and played["rate"] == FS and played["data"].dtype == np.float32
    assert np.allclose(played["data"], tone(), atol=1e-6)


@pytest.mark.parametrize("bad", [np.array([0.0, 1.5]), np.zeros((4, 2)), np.array([np.nan])])
def test_audio_that_would_clip_or_is_no_audio_is_not_played(card, sd, bad):
    with pytest.raises(ValueError):
        card.play(bad)
    assert sd.played == []


def test_a_recording_is_mono_float32_of_the_asked_length(sd):
    sd = FakeSounddevice(DEVICES, recording=tone(1.0))
    samples = SoundCard(load=lambda: sd).record(0.5, device="headset")
    assert samples.shape == (FS // 2,) and samples.dtype == np.float32
    assert sd.recordings == [{"frames": FS // 2, "device": 3, "channels": 1}]


def test_a_device_that_cannot_work_at_48_khz_is_refused_with_its_own_rate():
    sd = FakeSounddevice(DEVICES, rates=(44_100,))
    card = SoundCard(load=lambda: sd)
    with pytest.raises(UnsupportedAudioError, match="48000 Hz.*44100 Hz"):
        card.record(1.0, device=0)
    with pytest.raises(UnsupportedAudioError, match="48000 Hz"):
        card.play(tone(), device=2)


# Listening ----------------------------------------------------------------------------------


def test_listening_hands_over_the_blocks_in_order_until_it_is_stopped(card, sd):
    with card.listen(device="codec", block_seconds=0.1) as heard:
        (stream,) = sd.streams
        assert stream.running and stream.device == 1 and stream.blocksize == FS // 10
        for value in (1, 2, 3):
            stream.hear(np.full(FS // 10, value / 10))
    assert not stream.running and stream.closed
    blocks = list(heard)  # what was queued before the stop is still handed over
    assert [round(float(b[0]) * 10) for b in blocks] == [1, 2, 3]
    assert all(b.dtype == np.float32 and b.ndim == 1 for b in blocks)


def test_a_listener_that_is_too_slow_loses_the_oldest_blocks_and_counts_them(card, sd):
    heard = card.listen(block_seconds=0.1, capacity=3)
    stream = sd.streams[0]
    for value in range(1, 7):
        stream.hear(np.full(8, value / 10))
    heard.close()
    assert heard.dropped == 3
    assert [round(float(b[0]) * 10) for b in heard] == [4, 5, 6]


def test_a_sound_card_overflow_is_counted_as_lost_audio(card, sd):
    heard = card.listen()
    sd.streams[0].hear(np.zeros(8), overflow=True)
    assert heard.dropped == 1
    heard.close()


def test_a_listener_blocks_until_audio_arrives():
    import threading

    heard = audio.InputBlocks()
    received = []
    thread = threading.Thread(target=lambda: received.extend(heard))
    thread.start()
    heard.push(np.ones(4, dtype=np.float32))
    heard.close()
    thread.join(timeout=5)
    assert not thread.is_alive() and len(received) == 1


# The fake -----------------------------------------------------------------------------------


def test_the_fake_lists_the_devices_it_was_given_and_selects_like_the_real_one():
    fake = FakeAudio(devices=[DeviceInfo(0, "Fake cable", 1, 1, 48_000.0)])
    assert fake.list_devices()[0].name == "Fake cable"
    with pytest.raises(NoAudioDeviceError):
        fake.record(0.1, device="nothing like it")


def test_what_the_fake_plays_it_hears_when_looped_back():
    fake = FakeAudio(loopback=True)
    fake.play(tone())
    heard = fake.record(0.25)
    assert heard.dtype == np.float32 and np.allclose(heard, tone(), atol=1e-6)


def test_the_fake_serves_scripted_input_then_silence():
    fake = FakeAudio(input_samples=tone(0.1))
    first = fake.record(0.2)
    assert np.allclose(first[: FS // 10], tone(0.1), atol=1e-6) and not first[FS // 10 :].any()


def test_the_fake_remembers_what_was_played():
    fake = FakeAudio()
    fake.play(tone())
    assert len(fake.played) == 1 and fake.played[0].size == round(0.25 * FS)


def test_the_fake_listens_to_scripted_input_in_blocks_and_then_ends():
    fake = FakeAudio(input_samples=tone(0.5))
    with fake.listen(block_seconds=0.1) as heard:
        blocks = list(heard)
    assert [b.size for b in blocks] == [FS // 10] * 5


def test_a_message_goes_through_the_fake_cable_from_modem_to_receiver():
    modem = TurboModem(preset="fast")
    fake = FakeAudio(loopback=True)
    fake.play(transmit(modem, b"over the cable", "fast", msg_id=2))
    received = receive(modem, fake.record(8.0))
    assert [c.message for c in received.complete] == [b"over the cable"]


# Review fixes --------------------------------------------------------------------------------


@pytest.mark.parametrize("wanted", [True, "", 1.5, b"usb"])
def test_something_that_is_no_device_number_or_name_is_refused(card, wanted):
    with pytest.raises(NoAudioDeviceError, match="neither a device number nor part of a name"):
        find_device(card.list_devices(), wanted, "input")


def test_an_exact_name_wins_over_a_longer_name_that_contains_it():
    devices = [DeviceInfo(0, "USB", 1, 1, 48_000.0), DeviceInfo(1, "USB Audio 2", 1, 1, 48_000.0)]
    assert find_device(devices, "usb", "input") == 0
    assert find_device(devices, "usb audio", "input") == 1


def test_a_stream_that_cannot_start_is_closed_not_leaked(card, sd):
    sd.fail_to_start = True
    with pytest.raises(NoAudioDeviceError, match="cannot start"):
        card.listen()
    assert sd.streams[0].closed


def test_a_stream_that_cannot_stop_is_closed_all_the_same(card, sd):
    heard = card.listen()
    sd.fail_to_stop = True
    with pytest.raises(Exception, match="cannot stop"):
        heard.close()
    assert sd.streams[0].closed


def test_closing_twice_stops_the_stream_once():
    stops = []
    heard = audio.InputBlocks(on_close=lambda: stops.append(1))
    heard.close()
    heard.close()
    assert stops == [1]


def test_closing_from_another_thread_ends_the_iteration_that_is_waiting():
    import threading

    heard = audio.InputBlocks()
    done = threading.Event()

    def consume():
        list(heard)
        done.set()

    threading.Thread(target=consume, daemon=True).start()
    heard.close()
    assert done.wait(timeout=5)


def test_the_fake_refuses_a_block_of_no_duration():
    with pytest.raises(ValueError, match="positive"):
        FakeAudio(input_samples=tone()).listen(block_seconds=0)


def test_the_fake_drops_the_oldest_blocks_like_the_real_thing():
    fake = FakeAudio(input_samples=tone(0.5))
    heard = fake.listen(block_seconds=0.1, capacity=2)
    assert heard.dropped == 3 and len(list(heard)) == 2


# Stopping, and the cable between two fakes ------------------------------------------------------


def test_the_sound_card_stops_what_it_is_playing(card, sd):
    card.stop()
    assert sd.stopped == 1


def test_a_stop_while_the_fake_plays_cuts_the_sound_where_it_is():
    import threading

    sender, listener = FakeAudio(play_seconds=5.0), FakeAudio()
    sender.connect_to(listener)
    done = threading.Thread(target=sender.play, args=(tone(1.0),))
    done.start()
    while not sender.playing:
        pass
    sender.stop()
    done.join(timeout=5)
    assert not done.is_alive()
    heard = listener.record(1.0)
    assert 0 <= np.count_nonzero(heard) < 0.5 * FS  # a small part, if any, got through


def test_what_a_fake_plays_arrives_at_the_fake_it_is_connected_to():
    sender, receiver = FakeAudio(), FakeAudio()
    sender.connect_to(receiver)
    sender.play(tone())
    assert np.allclose(receiver.record(0.25), tone(), atol=1e-6)


def test_a_fake_that_is_connected_serves_a_listener_that_was_already_listening():
    sender, receiver = FakeAudio(), FakeAudio()
    sender.connect_to(receiver)
    heard = receiver.listen(block_seconds=0.05)
    sender.play(tone())
    heard.close()
    assert np.allclose(np.concatenate(list(heard)), tone(), atol=1e-6)


def test_a_fake_knows_how_many_listeners_are_still_open():
    fake = FakeAudio(loopback=True)
    first, second = fake.listen(), fake.listen()
    assert fake.open_listeners == 2
    first.close()
    second.close()
    assert fake.open_listeners == 0

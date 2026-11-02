"""The application's service: settings, sending, cancelling and listening, with fake sound cards."""

import threading
import time

import numpy as np
import pytest

from vibemodem.app.receiver import Tolerance
from vibemodem.app.service import BusyError, Cancelled, ModemService, SettingsError
from vibemodem.core.message import FRAGMENT_CAPACITY, Fragment
from vibemodem.core.modem import Reception, Report
from vibemodem.core.transmission import MessageTooLong
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import DeviceInfo, FakeAudio

TOLERANCE = Tolerance(seconds=0.16, hertz=25.0, frame_seconds=6.8, preamble_samples=61_440)
HEARD = Reception(b"", snr_db=-10.0, frequency_offset_hz=0.0, sync_score=20.0, start_sample=0)
DEVICES = [
    DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0),
    DeviceInfo(1, "Laptop microphone", 1, 0, 48_000.0),
]


def wait_until(condition, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def services():
    made = []

    def make(audio=None, **options):
        service = ModemService(audio or FakeAudio(devices=DEVICES), **options)
        made.append(service)
        return service

    yield make
    for service in made:
        service.close()


@pytest.fixture
def pair(services):
    """Two instances of the application with a cable from the first one's output to the
    second one's input, and both on the fast Preset."""
    sender_audio, listener_audio = FakeAudio(), FakeAudio()
    sender_audio.connect_to(listener_audio)
    sender, listener = services(sender_audio), services(listener_audio)
    sender.apply_settings(preset="fast")
    listener.apply_settings(preset="fast")
    return sender, listener


def send_and_wait(sender, text, **options):
    sent = sender.send(text, **options)
    assert wait_until(lambda: not sender.status()["sending"])
    return sent


# Settings -----------------------------------------------------------------------------------


def test_the_application_starts_idle_on_the_standard_preset(services):
    status = services().status()
    assert status["sending"] is False and status["listening"] is False
    assert status["settings"] == {
        "preset": "standard", "input_device": None, "output_device": None
    }  # fmt: skip


def test_settings_are_applied_together_and_reported(services):
    service = services()
    service.apply_settings(preset="max-range", input_device="laptop", output_device=0)
    assert service.settings.preset == "max-range"
    assert service.settings.input_device == "laptop" and service.settings.output_device == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"preset": "turbo-boost"},
        {"input_device": "no such card"},
        {"output_device": "laptop"},  # it only records
        {"colour": "red"},
    ],
)
def test_a_setting_that_is_invalid_changes_nothing_not_even_the_valid_ones(services, bad):
    service = services()
    before = service.settings
    with pytest.raises(SettingsError):
        service.apply_settings(**{"preset": "fast", "output_device": "radio", **bad})
    assert service.settings == before


def test_every_problem_with_the_settings_is_reported_at_once(services):
    with pytest.raises(SettingsError) as refusal:
        services().apply_settings(preset="nope", input_device="nothing")
    assert "preset" in str(refusal.value) and "input" in str(refusal.value)


def test_settings_cannot_change_while_listening_or_sending(services):
    service = services(FakeAudio(devices=DEVICES, loopback=True))
    service.start_listening()
    with pytest.raises(BusyError):
        service.apply_settings(preset="fast")
    service.stop_listening()
    service.apply_settings(preset="fast")  # fine again


# Sending and cancelling ---------------------------------------------------------------------


def test_a_message_is_played_and_its_airtime_reported(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="fast")
    sent = send_and_wait(service, "bonjour")
    assert (sent.fragments, sent.copies) == (1, 1) and sent.airtime_seconds == pytest.approx(6.8)
    assert len(audio.played) == 1 and audio.played[0].size / 48_000 == pytest.approx(6.8)


def test_a_message_that_is_too_long_is_refused_with_the_reason_and_nothing_is_played(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="max-range")
    with pytest.raises(MessageTooLong, match="shorter Message"):
        service.send("x" * 600)
    assert audio.played == [] and service.status()["sending"] is False


@pytest.mark.parametrize("copies", [0, 9, 1.5])
def test_copies_out_of_range_are_refused(services, copies):
    with pytest.raises(ValueError, match="copies"):
        services().send("hi", copies=copies)


def test_the_second_send_while_one_is_playing_is_refused(services):
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service = services(audio)
    service.apply_settings(preset="fast")
    service.send("first")
    assert wait_until(lambda: audio.playing)
    with pytest.raises(BusyError):
        service.send("second")
    assert service.cancel()


def test_cancelling_stops_the_sound_and_frees_the_service(services):
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service = services(audio)
    service.apply_settings(preset="fast")
    service.send("to be cancelled")
    assert wait_until(lambda: audio.playing)
    assert service.cancel() is True
    assert service.status()["sending"] is False and not audio.playing
    assert service.cancel() is False  # nothing left to cancel
    service.send("again")  # free to send again
    service.cancel()


def test_an_error_of_the_sound_card_while_playing_is_reported_not_lost(services):
    class Broken(FakeAudio):
        def play(self, samples, device=None):
            raise RuntimeError("the output was unplugged")

    service = services(Broken(devices=DEVICES))
    service.apply_settings(preset="fast")
    service.send("hello")
    assert wait_until(lambda: not service.status()["sending"])
    assert "unplugged" in service.status()["last_error"]


def test_a_message_that_is_not_text_is_sent_as_it_is(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="fast")
    assert send_and_wait(service, bytes([0, 255, 128])).fragments == 1


# Two instances ------------------------------------------------------------------------------


def test_a_message_sent_on_one_instance_arrives_intact_on_the_other(pair):
    sender, listener = pair
    listener.start_listening()
    send_and_wait(sender, "Bonjour, ça marche ? 73")
    listener.stop_listening()
    (heard,) = listener.received()
    assert heard.complete and heard.text == "Bonjour, ça marche ? 73"


def test_a_message_of_several_fragments_arrives_whole(pair):
    sender, listener = pair
    text = "CQ CQ CQ de F4XYZ " * 3  # 54 bytes: 4 Fragments
    listener.start_listening()
    send_and_wait(sender, text)
    listener.stop_listening()
    (heard,) = listener.received()
    assert heard.complete and heard.text == text and heard.total == 4


def test_copies_of_a_message_are_listed_once(pair):
    sender, listener = pair
    listener.start_listening()
    send_and_wait(sender, "twice", copies=2)
    listener.stop_listening()
    assert [r.text for r in listener.received()] == ["twice"]


def test_a_transmission_cut_short_shows_as_incomplete_with_what_arrived():
    sender_audio = FakeAudio(play_seconds=1.0)  # 1 s of real time for the whole sound
    listener_audio = FakeAudio()
    sender_audio.connect_to(listener_audio)
    sender, listener = ModemService(sender_audio), ModemService(listener_audio)
    try:
        for service in (sender, listener):
            service.apply_settings(preset="fast")
        listener.start_listening()
        sender.send("A" * 40)  # 3 Fragments, 20 s of sound
        assert wait_until(lambda: sender_audio.playing)
        time.sleep(0.5)  # half of it: the first Frame is whole, the second is cut
        sender.cancel()
        listener.stop_listening()
        (heard,) = listener.received()
        assert not heard.complete and heard.text is None
        assert heard.parts == [(0, "A" * FRAGMENT_CAPACITY)]
        assert heard.missing == (1, 2) and heard.total == 3
    finally:
        sender.close()
        listener.close()


def test_the_list_of_received_messages_is_bounded(services):
    sender_audio, listener_audio = FakeAudio(), FakeAudio()
    sender_audio.connect_to(listener_audio)
    sender = services(sender_audio)
    listener = services(listener_audio, max_received=3)
    sender.apply_settings(preset="fast")
    listener.apply_settings(preset="fast")
    listener.start_listening()
    for number in range(5):
        send_and_wait(sender, f"message {number}")
    listener.stop_listening()
    assert [r.text for r in listener.received()] == ["message 2", "message 3", "message 4"]


def test_a_listener_decodes_while_it_is_still_listening(services):
    sender_audio, listener_audio = FakeAudio(), FakeAudio()
    sender_audio.connect_to(listener_audio)
    sender = services(sender_audio)
    listener = services(listener_audio, decode_every_seconds=3.0)
    sender.apply_settings(preset="fast")
    listener.apply_settings(preset="fast")
    listener.start_listening()
    send_and_wait(sender, "no need to stop")
    sender_audio.play(np.zeros(4 * 48_000))  # a microphone goes on hearing the room
    assert wait_until(lambda: [r.text for r in listener.received()] == ["no need to stop"])
    assert listener.status()["listening"] is True


# Starting and stopping ------------------------------------------------------------------------


def test_listening_twice_is_refused_and_stopping_when_not_listening_is_harmless(services):
    service = services(FakeAudio(devices=DEVICES, loopback=True))
    assert service.stop_listening() is False
    service.start_listening()
    with pytest.raises(BusyError):
        service.start_listening()
    assert service.stop_listening() is True


def test_starting_and_stopping_again_and_again_leaks_nothing(services):
    audio = FakeAudio(devices=DEVICES, loopback=True)
    service = services(audio)
    threads_before = threading.active_count()
    for _ in range(20):
        service.start_listening()
        service.stop_listening()
    assert audio.open_listeners == 0
    assert threading.active_count() == threads_before


def test_sending_and_cancelling_again_and_again_leaks_nothing(services):
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service = services(audio)
    service.apply_settings(preset="fast")
    threads_before = threading.active_count()
    for _ in range(10):
        service.send("x")
        assert wait_until(lambda: audio.playing)
        service.cancel()
    assert threading.active_count() == threads_before


def test_closing_stops_everything_and_can_be_repeated(services):
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0, loopback=True)
    service = services(audio)
    service.apply_settings(preset="fast")
    threads_before = threading.active_count()
    service.start_listening()
    service.send("closing")
    assert wait_until(lambda: audio.playing)
    service.close()
    service.close()
    assert audio.open_listeners == 0 and threading.active_count() <= threads_before
    with pytest.raises(BusyError, match="closed"):
        service.send("too late")


def test_a_failing_sound_card_when_listening_is_reported_and_leaves_the_service_usable(services):
    class NoInput(FakeAudio):
        def listen(self, device=None, block_seconds=0.5, capacity=64):
            raise RuntimeError("the microphone is unplugged")

    service = services(NoInput(devices=DEVICES))
    with pytest.raises(RuntimeError, match="unplugged"):
        service.start_listening()
    assert service.status()["listening"] is False
    service.apply_settings(preset="fast")  # still usable


def test_what_was_heard_before_is_still_there_after_stopping_and_starting_again(pair):
    sender, listener = pair
    listener.start_listening()
    send_and_wait(sender, "first")
    listener.stop_listening()
    listener.start_listening()
    send_and_wait(sender, "second")
    listener.stop_listening()
    assert [r.text for r in listener.received()] == ["first", "second"]


def test_noise_alone_gives_nothing(services):
    noise = np.random.default_rng(0).normal(0, 0.05, 48_000 * 12)
    listener = services(FakeAudio(devices=DEVICES, input_samples=noise))
    listener.apply_settings(preset="fast")
    listener.start_listening()
    listener.stop_listening()
    assert listener.received() == []


# Review fixes: cancelling while the sound is still being made, closing meanwhile, failures ----


class GatedModem(TurboModem):
    """A modem whose first Frame waits for the test, to cancel or close in the middle of it."""

    def __init__(self, gate, **options):
        super().__init__(**options)
        self.gate = gate

    def modulate(self, message, preset):
        self.gate["entered"].set()
        self.gate["release"].wait(timeout=30)
        return super().modulate(message, preset)


def gated_service(services, audio):
    gate = {"entered": threading.Event(), "release": threading.Event()}
    service = services(audio, make_modem=lambda preset: GatedModem(gate, preset=preset))
    service.apply_settings(preset="fast")
    outcome = {}

    def send():
        try:
            outcome["sent"] = service.send("hello")
        except Exception as error:
            outcome["error"] = error

    thread = threading.Thread(target=send)
    thread.start()
    assert gate["entered"].wait(timeout=10)
    return service, gate, thread, outcome


def test_cancelling_while_the_sound_is_being_made_means_it_is_never_played(services):
    audio = FakeAudio(devices=DEVICES)
    service, gate, thread, outcome = gated_service(services, audio)
    assert service.cancel() is True
    gate["release"].set()
    thread.join(timeout=10)
    assert isinstance(outcome["error"], Cancelled)
    assert audio.played == [] and service.status()["sending"] is False


def test_closing_while_the_sound_is_being_made_leaves_no_thread_and_plays_nothing(services):
    audio = FakeAudio(devices=DEVICES)
    before = threading.active_count()
    service, gate, thread, outcome = gated_service(services, audio)
    service.close()
    gate["release"].set()
    thread.join(timeout=10)
    assert isinstance(outcome["error"], BusyError)
    assert audio.played == [] and threading.active_count() <= before


def test_a_decoding_that_fails_is_reported_and_the_listening_goes_on(services):
    class Failing(TurboModem):
        def demodulate_report(self, samples):
            raise RuntimeError("the decoder broke")

    audio = FakeAudio(devices=DEVICES, loopback=True)
    service = services(audio, make_modem=lambda preset: Failing(preset=preset))
    service.start_listening()
    audio.play(tone_burst())
    service.stop_listening()
    assert "decoder broke" in service.status()["last_error"]
    assert audio.open_listeners == 0


def tone_burst():
    return 0.1 * np.sin(2 * np.pi * 1000 * np.arange(48_000) / 48_000)


def test_a_listening_that_ended_on_its_own_can_be_started_again(services):
    audio = FakeAudio(devices=DEVICES, input_samples=tone_burst())
    service = services(audio)
    service.start_listening()  # the scripted input ends: so does the loop
    assert wait_until(lambda: not service.status()["listening"])
    service.start_listening()
    assert service.stop_listening() in (True, False)
    service.close()


def test_what_was_given_up_on_is_bounded_in_a_service_that_never_ends(services):
    service = services(max_received=3)
    for msg_id in range(10):  # the same Message twice with other content: given up each time
        service._receiver._take(
            Fragment(msg_id, 0, 2, b"a" * FRAGMENT_CAPACITY), HEARD, 0.0, TOLERANCE
        )
        service._receiver._take(
            Fragment(msg_id, 0, 2, b"b" * FRAGMENT_CAPACITY), HEARD, 0.0, TOLERANCE
        )
    given_up = [r for r in service.received() if r.parts and r.parts[0][1].startswith("a")]
    assert len(given_up) == 3  # the newest three; the ten being heard are bounded by the memory


# The frequency of a Signal and the estimate before sending -------------------------------------


def centre_frequency(sound):
    """The power-weighted mean frequency: the middle of the 8 tones of the fast Preset."""
    power = np.abs(np.fft.rfft(sound)) ** 2
    return float((np.fft.rfftfreq(sound.size, 1 / 48_000) * power).sum() / power.sum())


FAST_CENTRE_OFFSET_HZ = 3.5 * 25  # from the lowest tone to the middle of 8 tones 25 Hz apart


def test_a_message_is_sent_at_the_frequency_asked_for(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="fast")
    send_and_wait(service, "low", frequency_hz=700.0)
    send_and_wait(service, "high", frequency_hz=2000.0)
    low, high = (centre_frequency(sound) - FAST_CENTRE_OFFSET_HZ for sound in audio.played)
    assert low == pytest.approx(700.0, abs=15) and high == pytest.approx(2000.0, abs=15)


def test_the_default_frequency_is_1450_hz(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="fast")
    send_and_wait(service, "default")
    assert centre_frequency(audio.played[0]) - FAST_CENTRE_OFFSET_HZ == pytest.approx(1450, abs=15)


@pytest.mark.parametrize("frequency", [100.0, 349.0, 2476.0, 5000.0, float("nan"), "1450", True])
def test_a_frequency_outside_the_range_of_the_preset_is_refused_with_the_range(services, frequency):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="fast")
    with pytest.raises(ValueError, match="350 and 2475"):
        service.send("x", frequency_hz=frequency)
    assert audio.played == [] and service.status()["sending"] is False


def test_a_message_sent_at_another_frequency_is_received_by_a_listener_that_is_not_told(pair):
    sender, listener = pair
    listener.start_listening()
    send_and_wait(sender, "somewhere else in the band", frequency_hz=2200.0)
    listener.stop_listening()
    assert [r.text for r in listener.received()] == ["somewhere else in the band"]


def test_the_estimate_gives_the_airtime_without_playing_anything(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    service.apply_settings(preset="fast")
    estimate = service.estimate("x" * 40, copies=2)  # 3 Fragments twice
    assert estimate.fits and estimate.reason is None and estimate.fragments == 3
    assert estimate.airtime_seconds == pytest.approx(6 * 6.8)
    assert estimate.max_bytes == 2244 and audio.played == []
    assert estimate.frequency_range_hz == (350.0, 2475.0) and estimate.frequency_problem is None
    assert estimate.signal_width_hz == 175.0


def test_the_estimate_of_a_message_that_is_too_long_carries_the_refusal_of_send(services):
    service = services()
    service.apply_settings(preset="max-range")
    estimate = service.estimate("x" * 600)
    assert not estimate.fits and "at most 561 bytes" in estimate.reason
    with pytest.raises(MessageTooLong) as refusal:
        service.send("x" * 600)
    assert str(refusal.value) == estimate.reason


def test_the_estimate_tells_when_the_frequency_is_wrong(services):
    estimate = services().estimate("hello", frequency_hz=50.0)
    assert estimate.fits and "between" in estimate.frequency_problem


def test_the_estimate_follows_the_preset_and_can_be_asked_while_sending(services):
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service = services(audio)
    service.apply_settings(preset="fast")
    service.send("busy")
    assert wait_until(lambda: audio.playing)
    assert service.estimate("hello").airtime_seconds == pytest.approx(6.8)
    service.cancel()
    service.apply_settings(preset="standard")
    assert service.estimate("hello").airtime_seconds == pytest.approx(13.6)


def test_the_estimate_is_the_length_of_the_audio_that_send_plays(services):
    audio = FakeAudio(devices=DEVICES)
    service = services(audio)
    for preset in ("fast", "standard"):
        service.apply_settings(preset=preset)
        for text, copies, frequency in [("", 1, None), ("a" * 40, 2, 1000.0), ("b" * 18, 1, 500.0)]:
            estimate = service.estimate(text, copies, frequency)
            send_and_wait(service, text, copies=copies, frequency_hz=frequency)
            assert estimate.airtime_seconds == audio.played[-1].size / 48_000


@pytest.mark.parametrize("copies", [0, 9, True, 1.5])
def test_the_estimate_refuses_copies_that_send_would_refuse(services, copies):
    with pytest.raises(ValueError, match="copies"):
        services().estimate("hello", copies=copies)


def test_the_modems_kept_for_sending_are_few_however_many_frequencies_are_tried(services):
    service = services(FakeAudio(devices=DEVICES))
    service.apply_settings(preset="fast")
    for frequency in range(400, 400 + 40):
        send_and_wait(service, "x", frequency_hz=float(frequency))
    assert len(service._sending_modems) <= 8


def test_a_refused_frequency_does_not_leave_the_service_busy(services):
    service = services(FakeAudio(devices=DEVICES))
    with pytest.raises(ValueError):
        service.send("x", frequency_hz=1.0)
    assert service.status()["sending"] is False
    service.apply_settings(preset="fast")  # not stuck "busy"


class ReverseOrder(TurboModem):
    """Gives what it receives backwards in time, as a receiver sorting by score may do."""

    def demodulate_report(self, samples):
        report = super().demodulate_report(samples)
        return Report(sorted(report.receptions, key=lambda r: -r.start_sample), report.undecoded)


def test_messages_heard_in_one_pass_are_listed_in_the_order_they_were_sent(services):
    sender_audio, listener_audio = FakeAudio(), FakeAudio()
    sender_audio.connect_to(listener_audio)
    sender = services(sender_audio)
    listener = services(
        listener_audio,
        make_modem=lambda preset: ReverseOrder(preset=preset),
        decode_every_seconds=1000,  # one decode, when the listening stops
        max_received=10,
    )
    sender.apply_settings(preset="fast")
    listener.apply_settings(preset="fast")
    listener.start_listening()
    for number in range(4):
        send_and_wait(sender, f"message {number}")
    listener.stop_listening()
    assert [r.text for r in listener.received()] == [f"message {n}" for n in range(4)]


# Quality, losses and the spectrum ----------------------------------------------------------------


def test_a_message_heard_carries_how_it_was_received(pair):
    sender, listener = pair
    listener.start_listening()
    send_and_wait(sender, "quality", frequency_hz=1800.0)
    listener.stop_listening()
    (heard,) = listener.received()
    assert heard.frequency_hz == pytest.approx(1800.0, abs=3)
    assert heard.offset_hz == pytest.approx(350.0, abs=3)
    assert heard.sync_score > 7 and heard.snr_db is not None and np.isfinite(heard.snr_db)


def test_a_message_of_several_fragments_is_summed_up_by_its_weakest_link(services):
    service = services()
    parts = [Fragment(5, 0, 3, b"a" * 17), Fragment(5, 1, 3, b"b" * 17), Fragment(5, 2, 3, b"c")]
    for fragment, (snr, hz, score) in zip(
        parts, [(-10.0, 1500.0, 30.0), (-14.0, 1500.5, 9.0), (-12.0, 1499.5, 20.0)], strict=True
    ):
        service._receiver._take(
            fragment,
            Reception(b"", snr_db=snr, frequency_offset_hz=hz - 1450.0, sync_score=score),
            100.0,
            TOLERANCE,
        )
    (heard,) = service.received()
    assert heard.snr_db == pytest.approx(-12.0) and heard.sync_score == 9.0
    assert heard.frequency_hz == pytest.approx(1500.0) and heard.heard_at == 100.0


def test_a_message_heard_in_part_says_how_the_part_was_received(services):
    service = services()
    service._receiver._take(
        Fragment(5, 0, 3, b"a" * 17), Reception(b"", -9.0, 100.0, 15.0), 100.0, TOLERANCE
    )
    (heard,) = service.received()
    assert not heard.complete and heard.snr_db == -9.0 and heard.sync_score == 15.0
    assert heard.frequency_hz == pytest.approx(1550.0)


def test_a_signal_whose_message_cannot_be_read_is_listed_once_however_many_passes(services):
    modem = TurboModem(preset="fast")
    size = modem.waveform.samples_per_symbol
    first = modem.modulate(Fragment(1, 0, 1, b"first").pack(), "fast")
    second = modem.modulate(Fragment(2, 0, 1, b"second").pack(), "fast").copy()
    third = modem.modulate(Fragment(3, 0, 1, b"third").pack(), "fast")
    start = mfsk_preamble() * size
    second[start : start + 100 * size] = (
        np.random.default_rng(1).normal(0, 0.3, 100 * size).clip(-1, 1)
    )
    recording = np.concatenate([first, second, third, np.zeros(48_000 * 4)])
    listener = services(
        FakeAudio(devices=DEVICES, input_samples=recording), decode_every_seconds=3.0
    )
    listener.apply_settings(preset="fast")
    listener.start_listening()
    assert wait_until(lambda: not listener.status()["listening"])
    listener.stop_listening()
    assert [r.text for r in listener.received()] == ["first", "third"]
    (lost,) = listener.undecoded()  # decoded in many passes of the window, listed once
    assert lost.frequency_hz == pytest.approx(1450.0, abs=3) and lost.sync_score > 7


def mfsk_preamble():
    from vibemodem.core import mfsk

    return mfsk.PREAMBLE_SYMBOLS


def test_the_spectrum_shows_the_tone_that_is_heard(services):
    tone = 0.3 * np.sin(2 * np.pi * 1000 * np.arange(48_000 * 3) / 48_000)
    service = services(FakeAudio(devices=DEVICES, input_samples=tone))
    service.start_listening()
    assert wait_until(lambda: not service.status()["listening"])
    rows = service.spectrum(0)
    assert rows.first == 0 and rows.next == 6 and len(rows.rows) == 6  # 3 s in blocks of 0.5 s
    assert all(len(row) == 480 for row in rows.rows)
    assert 300 + 5 * int(np.argmax(rows.rows[2])) == pytest.approx(1000, abs=10)


def test_only_the_rows_after_the_last_one_asked_for_are_given(services):
    sound = np.zeros(48_000 * 4)
    service = services(FakeAudio(devices=DEVICES, input_samples=sound))
    service.start_listening()
    assert wait_until(lambda: not service.status()["listening"])
    assert service.spectrum(5).first == 5 and len(service.spectrum(5).rows) == 3
    assert service.spectrum(8).rows == [] and service.spectrum(100).next == 8


def test_the_spectrum_history_is_bounded_to_a_minute(services):
    service = services(FakeAudio(devices=DEVICES, input_samples=np.zeros(48_000 * 100)))
    service.start_listening()
    assert wait_until(lambda: not service.status()["listening"])
    rows = service.spectrum(0)
    assert len(rows.rows) == 120 and rows.next == 200 and rows.first == 80


# The Receiver, after the reviews ---------------------------------------------------------------


class ScriptedModem:
    """A modem that reports what it is told to, whatever the sound."""

    def __init__(self, receptions=(), undecoded=()):
        self.report = Report(list(receptions), list(undecoded))

    def demodulate_report(self, samples):
        return self.report


def receiver_of(services):
    return services()._receiver


def window_of_silence():
    from collections import deque

    return deque([np.zeros(48_000)])


def test_a_signal_lost_in_one_pass_and_read_in_a_later_one_is_no_longer_listed_as_lost(services):
    receiver = receiver_of(services)
    receiver._note_lost(100.0, 1450.0, 20.0, TOLERANCE)
    assert len(receiver.undecoded()) == 1
    reception = Reception(b"", -10.0, 0.0, 30.0, start_sample=0)  # at 1450 Hz
    receiver._take(Fragment(1, 0, 1, b"found"), reception, 100.05, TOLERANCE)
    assert receiver.undecoded() == []


def test_a_signal_next_to_a_frame_that_was_read_at_the_same_frequency_is_a_side_peak(services):
    receiver = receiver_of(services)
    reception = Reception(b"", -10.0, 0.0, 30.0, start_sample=0)
    receiver._take(Fragment(1, 0, 1, b"read"), reception, 100.0, TOLERANCE)
    receiver._note_lost(101.5, 1450.0, 20.0, TOLERANCE)  # inside the 6.8 s of that Frame
    assert receiver.undecoded() == []
    receiver._note_lost(106.8, 1450.0, 20.0, TOLERANCE)  # the next Frame: a real loss
    receiver._note_lost(101.5, 1900.0, 20.0, TOLERANCE)  # another frequency: another Signal
    assert len(receiver.undecoded()) == 2


def test_two_sightings_of_one_signal_are_one_and_two_signals_that_differ_are_two(services):
    receiver = receiver_of(services)
    receiver._note_lost(100.0, 1450.0, 20.0, TOLERANCE)
    receiver._note_lost(100.1, 1451.0, 22.0, TOLERANCE)  # within 2 symbols and a tone spacing
    assert len(receiver.undecoded()) == 1
    receiver._note_lost(100.5, 1450.0, 20.0, TOLERANCE)  # later than 2 symbols: another Frame
    receiver._note_lost(100.1, 1500.0, 20.0, TOLERANCE)  # farther than a tone spacing
    assert len(receiver.undecoded()) == 3


def test_a_frame_cut_by_the_start_of_the_window_is_not_reported_as_lost(services):
    from vibemodem.core.modem import Detection

    receiver = receiver_of(services)
    modem = ScriptedModem(
        undecoded=[Detection(start_sample=10_000, frequency_hz=1450.0, sync_score=15.0)]
    )
    receiver._decode(window_of_silence(), modem, TOLERANCE, 1000.0, window_start=480_000)
    assert receiver.undecoded() == []  # near the edge of a window that is not the first
    receiver._decode(window_of_silence(), modem, TOLERANCE, 1000.0, window_start=0)
    assert len(receiver.undecoded()) == 1  # but at the very start of the listening it is judged


def test_the_clearest_sighting_of_a_fragment_is_the_one_that_counts(services):
    receiver = receiver_of(services)
    fragment = Fragment(4, 0, 2, b"x" * FRAGMENT_CAPACITY)
    receiver._take(fragment, Reception(b"", -20.0, 0.0, 9.0), 10.0, TOLERANCE)
    receiver._take(fragment, Reception(b"", -8.0, 0.0, 40.0), 20.0, TOLERANCE)
    receiver._take(fragment, Reception(b"", -15.0, 0.0, 12.0), 30.0, TOLERANCE)
    (heard,) = receiver.received()
    assert heard.snr_db == -8.0 and heard.sync_score == 40.0 and heard.heard_at == 20.0


def test_a_new_listening_starts_a_new_waterfall(services):
    service = services(FakeAudio(devices=DEVICES, input_samples=np.zeros(48_000 * 2)))
    service.start_listening()
    assert wait_until(lambda: not service.status()["listening"])
    first = service.spectrum(0)
    assert first.next == 4
    service._receiver._audio = FakeAudio(devices=DEVICES, input_samples=np.zeros(48_000))
    service.start_listening()
    assert wait_until(lambda: not service.status()["listening"])
    second = service.spectrum(0)
    assert second.first == 4 and second.next == 6 and len(second.rows) == 2


def test_the_time_of_a_message_heard_is_the_time_of_its_sound(pair):
    import time as clock

    sender, listener = pair
    before = clock.time()
    listener.start_listening()
    send_and_wait(sender, "timed")
    listener.stop_listening()
    (heard,) = listener.received()
    assert before - 1 <= heard.heard_at <= before + 10  # the sound began as the listening did

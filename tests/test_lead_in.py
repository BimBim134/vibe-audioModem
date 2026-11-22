"""The Lead-in: an optional tone before the Preamble, off by default."""

import time

import numpy as np
import pytest

from vibemodem.app.service import BusyError, ModemService, SettingsError
from vibemodem.app.settings_file import SettingsFile
from vibemodem.core import mfsk
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import Fragment
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


def peak_hz(samples: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
    return float(np.argmax(spectrum) * SAMPLE_RATE / samples.size)


@pytest.fixture
def service(tmp_path):
    made = []

    def make(audio=None):
        made.append(
            ModemService(
                audio or FakeAudio(devices=DEVICES),
                settings_file=SettingsFile(tmp_path / "s.json"),
            )
        )
        return made[-1]

    yield make
    for each in made:
        each.close()


def played_sound(audio: FakeAudio, app: ModemService) -> np.ndarray:
    deadline = time.monotonic() + 30
    while app.status()["sending"] and time.monotonic() < deadline:
        time.sleep(0.01)
    return audio.played[-1]


def test_there_is_no_lead_in_unless_asked_for(service):
    audio = FakeAudio(devices=DEVICES)
    app = service(audio)
    app.apply_settings(preset="fast")
    sent = app.send("hello")
    assert played_sound(audio, app).size / SAMPLE_RATE == pytest.approx(sent.airtime_seconds)
    assert app.settings.lead_in_ms == 0


def test_the_sound_starts_with_the_lead_in_at_the_lowest_tone_then_the_preamble(service):
    audio = FakeAudio(devices=DEVICES)
    app = service(audio)
    app.apply_settings(preset="fast")
    without = app.send("hello")
    bare = played_sound(audio, app)
    app.apply_settings(lead_in_ms=500)
    with_lead_in = app.send("hello", frequency_hz=1000.0)
    sound = played_sound(audio, app)
    assert sound.size == bare.size + round(0.5 * SAMPLE_RATE)
    assert with_lead_in.airtime_seconds == pytest.approx(without.airtime_seconds + 0.5)
    lead = sound[: round(0.5 * SAMPLE_RATE)]
    assert peak_hz(lead) == pytest.approx(1000.0, abs=5.0)
    assert np.abs(lead).max() == pytest.approx(np.abs(sound).max(), rel=0.01)
    assert lead[0] == 0.0  # no click when the transmitter opens


def test_the_estimate_counts_the_lead_in(service):
    app = service()
    plain = app.estimate("hello").airtime_seconds
    app.apply_settings(lead_in_ms=300)
    assert app.estimate("hello").airtime_seconds == pytest.approx(plain + 0.3)


def test_a_message_is_received_with_a_lead_in(service):
    sender_audio, listener_audio = FakeAudio(devices=DEVICES), FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    sender, listener = service(sender_audio), service(listener_audio)
    for each in (sender, listener):
        each.apply_settings(preset="fast")
    sender.apply_settings(lead_in_ms=800)
    listener.start_listening()
    sender.send("hello")
    played_sound(sender_audio, sender)
    listener.stop_listening()
    assert [m.text for m in listener.received()] == ["hello"]


def test_a_message_is_received_when_the_first_200_ms_of_the_lead_in_are_missed(service):
    audio = FakeAudio(devices=DEVICES)
    app = service(audio)
    app.apply_settings(preset="fast", lead_in_ms=600)
    app.send("hello")
    sound = played_sound(audio, app)[round(0.2 * SAMPLE_RATE) :]
    modem = TurboModem(preset="fast")
    padded = np.concatenate(
        [np.zeros(SAMPLE_RATE, np.float32), sound, np.zeros(SAMPLE_RATE, np.float32)]
    )
    assert Fragment.unpack(modem.demodulate(padded)[0].message).payload == b"hello"


@pytest.mark.parametrize("bad", [-1, 5001, 1.5, "100", True])
def test_a_lead_in_that_makes_no_sense_is_refused_and_nothing_changes(service, bad):
    app = service()
    with pytest.raises(SettingsError):
        app.apply_settings(copies=2, lead_in_ms=bad)
    assert app.settings.lead_in_ms == 0 and app.settings.copies == 1


def test_the_lead_in_is_kept_between_sessions_and_changes_while_listening(service):
    app = service(FakeAudio(devices=DEVICES, loopback=True))
    app.start_listening()
    assert app.apply_settings(lead_in_ms=400).lead_in_ms == 400
    with pytest.raises(BusyError):
        app.apply_settings(preset="fast")
    assert service().settings.lead_in_ms == 400
    assert app.status()["settings"]["lead_in_ms"] == 400


def test_the_default_first_tone_is_the_lead_in_frequency_when_none_is_chosen(service):
    audio = FakeAudio(devices=DEVICES)
    app = service(audio)
    app.apply_settings(preset="fast", lead_in_ms=500)
    app.send("hi")
    lead = played_sound(audio, app)[: round(0.5 * SAMPLE_RATE)]
    assert peak_hz(lead) == pytest.approx(mfsk.FIRST_TONE_HZ, abs=5.0)

"""The busy warning: the status says when a Signal is arriving, so the page can warn before a
Message is sent over it. It only warns: sending is never refused."""

import time

import pytest

from vibemodem.app.service import ModemService
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


def wait_until(condition, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def stations():
    """A station that sends, a cable from its output, and one that listens to it."""
    sender_audio = FakeAudio(devices=DEVICES, real_time=True)
    listener_audio = FakeAudio(devices=DEVICES, real_time=True)
    sender_audio.connect_to(listener_audio)
    sender, listener = ModemService(sender_audio), ModemService(listener_audio)
    for each in (sender, listener):
        each.apply_settings(preset="fast")
    yield sender, listener
    sender.close()
    listener.close()


def test_nothing_is_arriving_when_nothing_is_heard(stations):
    _, listener = stations
    assert listener.status()["arriving"] == []
    listener.start_listening()
    assert listener.status()["arriving"] == []


def test_the_status_tells_the_frequency_of_a_signal_that_is_arriving_then_nothing(stations):
    sender, listener = stations
    listener.start_listening()
    sender.send("hello", frequency_hz=1450.0)
    assert wait_until(lambda: listener.status()["arriving"])
    (hz,) = listener.status()["arriving"]
    assert hz == pytest.approx(1450.0, abs=50.0)
    assert wait_until(lambda: not sender.status()["sending"])
    listener.stop_listening()  # the end of the listening: nothing is coming any more
    assert listener.status()["arriving"] == []


def test_a_signal_outside_the_listening_band_is_not_arriving(stations):
    sender, listener = stations
    listener.set_search_band(2200.0, 2600.0)
    listener.start_listening()
    sender.send("hello", frequency_hz=1000.0)
    assert wait_until(lambda: not sender.status()["sending"])
    assert listener.status()["arriving"] == []


def test_sending_is_never_refused_while_a_signal_arrives(stations):
    sender, listener = stations
    listener.start_listening()
    sender.send("first")
    assert wait_until(lambda: listener.status()["arriving"])
    sent = listener.send("over it")  # warned by the page, but the service lets it through
    assert sent.fragments == 1

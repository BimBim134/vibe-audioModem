"""The manual sound-card check, run against the fake device."""

import pytest

from bench.audio_check import main, print_devices, print_level, send_through
from vibemodem.io.audio import FakeAudio


def test_a_message_sent_through_a_looped_back_fake_is_received(capsys):
    ok = send_through(
        FakeAudio(loopback=True), output=None, input=None, preset="fast", message=b"bonjour",
        tail_seconds=0.0,
    )  # fmt: skip
    assert ok and "RECEIVED: b'bonjour'" in capsys.readouterr().out


def test_nothing_heard_is_reported_not_hidden(capsys):
    ok = send_through(
        FakeAudio(), output=None, input=None, preset="fast", message=b"bonjour", tail_seconds=0.0
    )
    assert not ok and "nothing was received" in capsys.readouterr().out


def test_the_devices_are_listed_with_their_direction(capsys):
    print_devices(FakeAudio())
    assert "Fake audio device" in capsys.readouterr().out


def test_the_level_of_silence_is_reported_as_too_low(capsys):
    print_level(FakeAudio(), None, 0.5)
    assert "too low" in capsys.readouterr().out


def test_a_device_that_does_not_exist_is_a_clean_error(capsys):
    # Whether this machine has PortAudio or not, the answer is an error message, not a traceback.
    with pytest.raises(SystemExit) as stop:
        main(["--level", "1", "--input", "no such card at all"])
    assert stop.value.code == 2 and capsys.readouterr().err

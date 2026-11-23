"""TX blanking: the station does not hear its own Transmission back as a received Message."""

import time

import numpy as np
import pytest

from vibemodem.app.blanking import Blanking
from vibemodem.app.service import BusyError, ModemService, SettingsError
from vibemodem.app.settings_file import SettingsFile
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


def wait_until(condition, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def ones(seconds: float) -> np.ndarray:
    return np.ones(round(seconds * SAMPLE_RATE), dtype=np.float32)


# The pure part: which samples of a block of input are silenced ------------------------------


def test_nothing_is_silenced_when_nothing_was_sent():
    block = ones(1.0)
    assert Blanking().silence(block, 100.0) is block


def test_the_sound_of_a_transmission_is_silenced_until_its_end():
    blanking = Blanking()
    blanking.start(10.0)
    blanking.end(12.0)
    block = blanking.silence(ones(4.0), 9.0)  # covers 9 s to 13 s
    heard = block.reshape(4, -1)  # one second each
    assert [row.max() for row in heard] == [1.0, 0.0, 0.0, 1.0]


def test_while_playing_everything_from_the_start_of_playback_is_silenced():
    blanking = Blanking()
    blanking.start(10.0)
    assert blanking.silence(ones(2.0), 11.0).max() == 0.0
    assert blanking.silence(ones(2.0), 9.0).reshape(2, -1).max(axis=1).tolist() == [1.0, 0.0]


def test_the_end_of_the_blanking_is_where_the_caller_puts_it():
    blanking = Blanking()
    blanking.start(10.0)
    blanking.end(12.25)  # end of playback, output latency and margin, added up by the caller
    block = blanking.silence(ones(1.0), 12.0)
    assert block[: round(0.25 * SAMPLE_RATE)].max() == 0.0
    assert block[round(0.25 * SAMPLE_RATE) :].min() == 1.0


def test_two_transmissions_are_both_silenced():
    blanking = Blanking()
    for begin in (10.0, 20.0):
        blanking.start(begin)
        blanking.end(begin + 1.0)
    rows = blanking.silence(ones(12.0), 10.0).reshape(12, -1).max(axis=1)
    assert rows.tolist() == [0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0]


def test_the_block_given_is_not_changed():
    blanking = Blanking()
    blanking.start(0.0)
    block = ones(1.0)
    blanking.silence(block, 0.0)
    assert block.min() == 1.0


# The station and its echo ---------------------------------------------------------------------


def test_the_echo_of_the_station_is_not_received_but_another_station_receives_it():
    # A cable from the station's output to its own input, with a delay and a weaker level,
    # and another station that listens to the same Transmission.
    own = FakeAudio(
        devices=DEVICES,
        loopback=True,
        real_time=True,
        echo_delay_seconds=0.1,
        echo_gain=0.5,
        output_latency_seconds=0.1,
    )
    other = FakeAudio(devices=DEVICES, real_time=True)
    own.connect_to(other)
    station, neighbour = ModemService(own), ModemService(other)
    try:
        for each in (station, neighbour):
            each.apply_settings(preset="fast")
        station.start_listening()
        neighbour.start_listening()
        station.send("hello")
        assert wait_until(lambda: station.status()["sending"] is False)
        time.sleep(1.0)  # the echo is all heard by now
        station.stop_listening()  # the last pass decodes what was heard
        neighbour.stop_listening()
        assert [m.text for m in neighbour.received()] == ["hello"]
        assert station.received() == []
        assert station.undecoded() == []
        assert [e["text"] for e in station.conversation()] == ["hello"]
        assert station.conversation()[0]["kind"] == "sent"
    finally:
        station.close()
        neighbour.close()


# The margin -----------------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path):
    made = []

    def make():
        made.append(
            ModemService(
                FakeAudio(devices=DEVICES, loopback=True),
                settings_file=SettingsFile(tmp_path / "s.json"),
            )
        )
        return made[-1]

    yield make
    for each in made:
        each.close()


def test_the_margin_is_a_quarter_of_a_second_unless_told_otherwise(service):
    app = service()
    assert app.settings.tx_margin_ms == 250
    assert app.status()["settings"]["tx_margin_ms"] == 250


def test_the_margin_can_be_changed_even_while_listening(service):
    app = service()
    app.start_listening()
    assert app.apply_settings(tx_margin_ms=400).tx_margin_ms == 400
    with pytest.raises(BusyError):
        app.apply_settings(preset="fast")


def test_the_margin_is_kept_between_sessions(service):
    service().apply_settings(tx_margin_ms=600)
    assert service().settings.tx_margin_ms == 600


@pytest.mark.parametrize("bad", [-1, 10_001, 1.5, "250", True])
def test_a_margin_that_makes_no_sense_is_refused_and_nothing_changes(service, bad):
    app = service()
    with pytest.raises(SettingsError):
        app.apply_settings(copies=2, tx_margin_ms=bad)
    assert app.settings.tx_margin_ms == 250 and app.settings.copies == 1

"""Push to talk through Hamlib's `rigctld`, tried against a fake one on the local network."""

import socketserver
import threading
import time

import pytest

from vibemodem.app.ptt import PttError, RigctldPtt
from vibemodem.app.service import BusyError, ModemService, SettingsError
from vibemodem.app.settings_file import SettingsFile
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


class FakeRigctld:
    """Answers like rigctld and notes what it is told, with the time, in a list shared with the
    fake sound card so that the order of the two can be checked."""

    def __init__(self, events: list, reply: str = "RPRT 0"):
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    events.append((line.decode().strip(), time.monotonic()))
                    self.wfile.write(f"{outer.reply}\n".encode())

        self.reply = reply
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class NotedAudio(FakeAudio):
    def __init__(self, events: list, fail: bool = False, **options):
        super().__init__(devices=DEVICES, **options)
        self.events, self.fail = events, fail

    def play(self, samples, device=None):
        self.events.append(("play", time.monotonic()))
        if self.fail:
            raise OSError("the sound card is gone")
        super().play(samples, device)
        self.events.append(("played", time.monotonic()))


@pytest.fixture
def events():
    return []


@pytest.fixture
def rig(events):
    made = FakeRigctld(events)
    yield made
    made.close()


@pytest.fixture
def make(tmp_path, events):
    made = []

    def build(audio=None, **settings):
        service = ModemService(
            audio or NotedAudio(events), settings_file=SettingsFile(tmp_path / "s.json")
        )
        made.append(service)
        service.apply_settings(preset="fast", **settings)
        return service

    yield build
    for service in made:
        service.close()


def wait_sent(service, timeout=30.0):
    deadline = time.monotonic() + timeout
    while service.status()["sending"] and time.monotonic() < deadline:
        time.sleep(0.01)
    return service.conversation()[-1]


def names(events):
    return [name for name, _ in events]


def test_the_ptt_is_keyed_before_the_sound_and_released_after_it(make, rig, events):
    app = make(ptt=True, ptt_port=rig.port, ptt_before_ms=150, ptt_after_ms=100)
    app.send("hello")
    assert wait_sent(app)["status"] == "sent"
    assert names(events) == ["T 1", "play", "played", "T 0"]
    when = dict(events)
    assert when["play"] - when["T 1"] >= 0.15
    assert when["T 0"] - when["played"] >= 0.10


def test_nothing_is_sent_to_rigctld_while_the_ptt_is_off(make, rig, events):
    app = make(ptt_port=rig.port)  # off by default
    app.send("hello")
    assert wait_sent(app)["status"] == "sent"
    assert names(events) == ["play", "played"]


def test_the_ptt_is_before_the_lead_in(make, rig, events):
    audio = NotedAudio(events)
    app = make(audio, ptt=True, ptt_port=rig.port, ptt_before_ms=0, ptt_after_ms=0, lead_in_ms=300)
    sent = app.send("hello")
    wait_sent(app)
    assert names(events)[:2] == ["T 1", "play"]  # the sound played starts with the Lead-in
    assert audio.played[-1].size / 48_000 == pytest.approx(sent.airtime_seconds)


def test_without_a_rigctld_to_talk_to_nothing_is_played_and_the_reason_is_shown(make, events):
    unused = FakeRigctld([])
    port = unused.port
    unused.close()
    app = make(ptt=True, ptt_port=port)
    app.send("hello")
    entry = wait_sent(app)
    assert entry["status"] == "failed"
    assert "rigctld" in entry["error"] and str(port) in entry["error"]
    assert "play" not in names(events)
    assert not app.status()["sending"]


def test_a_refusal_of_rigctld_is_a_failure_too(make, events):
    refusing = FakeRigctld(events, reply="RPRT -11")
    try:
        app = make(ptt=True, ptt_port=refusing.port)
        app.send("hello")
        entry = wait_sent(app)
        assert entry["status"] == "failed" and "RPRT -11" in entry["error"]
        assert "play" not in names(events)
    finally:
        refusing.close()


def test_the_ptt_is_released_when_the_sound_card_fails(make, rig, events):
    app = make(NotedAudio(events, fail=True), ptt=True, ptt_port=rig.port, ptt_after_ms=0)
    app.send("hello")
    assert wait_sent(app)["status"] == "failed"
    assert names(events) == ["T 1", "play", "T 0"]


def test_the_ptt_is_released_when_the_transmission_is_cancelled(make, rig, events):
    app = make(NotedAudio(events, play_seconds=30.0), ptt=True, ptt_port=rig.port, ptt_after_ms=0)
    app.send("hello")
    deadline = time.monotonic() + 10
    while "play" not in names(events) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert app.cancel()
    assert wait_sent(app)["status"] == "cancelled"
    assert names(events)[-1] == "T 0"


def test_the_checker_of_the_connection_says_what_is_wrong(rig):
    assert RigctldPtt("127.0.0.1", rig.port).key(True) is None
    unused = FakeRigctld([])
    port = unused.port
    unused.close()
    with pytest.raises(PttError, match="rigctld"):
        RigctldPtt("127.0.0.1", port).key(True)


# The settings --------------------------------------------------------------------------------


def test_the_defaults_are_off_on_the_usual_port_of_rigctld(make):
    app = make()
    s = app.settings
    assert (s.ptt, s.ptt_host, s.ptt_port, s.ptt_before_ms, s.ptt_after_ms) == (
        False,
        "127.0.0.1",
        4532,
        100,
        100,
    )
    assert app.status()["settings"]["ptt"] is False


def test_the_ptt_settings_are_kept_between_sessions_and_change_while_listening(make, tmp_path):
    app = make(NotedAudio([], loopback=True))
    app.start_listening()
    app.apply_settings(ptt=True, ptt_host="shack.local", ptt_port=4540, ptt_after_ms=300)
    with pytest.raises(BusyError):
        app.apply_settings(preset="standard")
    again = make()
    assert again.settings.ptt and again.settings.ptt_host == "shack.local"
    assert again.settings.ptt_port == 4540 and again.settings.ptt_after_ms == 300


@pytest.mark.parametrize(
    "bad",
    [
        {"ptt": 1},
        {"ptt_host": ""},
        {"ptt_host": "two words"},
        {"ptt_host": 5},
        {"ptt_port": 0},
        {"ptt_port": 70_000},
        {"ptt_port": True},
        {"ptt_before_ms": -1},
        {"ptt_after_ms": 5001},
    ],
)
def test_a_ptt_setting_that_makes_no_sense_is_refused_and_nothing_changes(make, bad):
    app = make()
    with pytest.raises(SettingsError):
        app.apply_settings(copies=2, **bad)
    assert app.settings.copies == 1

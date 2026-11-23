"""The Callsign: a setting written in front of the text of each Message the station sends."""

import pytest

from vibemodem.app.callsign import callsign_of
from vibemodem.app.service import BusyError, ModemService, SettingsError
from vibemodem.app.settings_file import SettingsFile
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


@pytest.fixture
def service(tmp_path):
    made = []

    def make(**audio_options):
        made.append(
            ModemService(
                FakeAudio(devices=DEVICES, **audio_options),
                settings_file=SettingsFile(tmp_path / "s.json"),
            )
        )
        return made[-1]

    yield make
    for each in made:
        each.close()


def sent_text(app):
    return app.conversation()[-1]["text"]


def test_a_sent_message_starts_with_the_callsign(service):
    app = service()
    app.apply_settings(callsign="F4JBO")
    app.send("hello")
    assert sent_text(app) == "F4JBO: hello"


def test_the_callsign_is_written_in_capitals_and_a_portable_one_is_accepted(service):
    app = service()
    assert app.apply_settings(callsign=" f4jbo/p ").callsign == "F4JBO/P"
    app.send("hi")
    assert sent_text(app) == "F4JBO/P: hi"


def test_without_a_callsign_nothing_is_added(service):
    app = service()
    app.send("hello")
    assert sent_text(app) == "hello"


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_the_callsign_can_be_taken_off(service, empty):
    app = service()
    app.apply_settings(callsign="F4JBO")
    assert app.apply_settings(callsign=empty).callsign is None
    app.send("hello")
    assert sent_text(app) == "hello"


@pytest.mark.parametrize(
    "bad",
    ["AB", "F4 JBO", "F4JBO//P", "/F4JBO", "F4JBO/", "F4JBO:", "É4JBO", "ß4JB", "F4JBO" * 3, 7],
)
def test_a_callsign_that_cannot_be_one_is_refused_and_nothing_changes(service, bad):
    app = service()
    app.apply_settings(callsign="F4JBO")
    with pytest.raises(SettingsError):
        app.apply_settings(preset="fast", callsign=bad)
    assert app.settings.callsign == "F4JBO" and app.settings.preset == "standard"


def test_the_estimate_and_the_fragments_count_the_prefix(service):
    app = service()
    twelve = "hello world!"  # 12 bytes: one Fragment of 17 on its own
    assert app.estimate(twelve).fragments == 1
    app.apply_settings(callsign="F4JBO")  # "F4JBO: " is 7 bytes more: 19 in all
    assert app.estimate(twelve).fragments == 2
    assert app.send(twelve).fragments == 2


def test_the_callsign_changes_while_listening_but_the_rest_does_not(service):
    app = service(loopback=True)
    app.start_listening()
    assert app.apply_settings(callsign="F4JBO").callsign == "F4JBO"
    with pytest.raises(BusyError):
        app.apply_settings(preset="fast")


def test_the_callsign_is_kept_between_sessions_and_shown_in_the_status(service):
    service().apply_settings(callsign="F4JBO")
    again = service()
    assert again.settings.callsign == "F4JBO"
    assert again.status()["settings"]["callsign"] == "F4JBO"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("F4JBO: hello", "F4JBO"),
        ("F4JBO/P: hello: there", "F4JBO/P"),
        ("F4JBO: ", "F4JBO"),
        ("hello", None),
        ("F4JBO:hello", None),
        ("f4jbo: hello", None),
        ("AB: hello", None),
        ("F4JBO hello: there", None),
        (": hello", None),
        ("", None),
    ],
)
def test_the_callsign_of_a_received_text(text, expected):
    assert callsign_of(text) == expected

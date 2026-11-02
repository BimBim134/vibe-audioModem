"""The local API, through HTTP, with fake sound cards and WAV files."""

import socket
import threading
import time
import urllib.request

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vibemodem.app.api import create_app
from vibemodem.app.main import free_port, make_server
from vibemodem.app.service import ModemService
from vibemodem.core.transmission import transmit
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import AudioLibraryUnavailableError, DeviceInfo, FakeAudio
from vibemodem.io.wav import read_wav, write_wav

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
def made():
    services = []

    def make(audio=None, **options):
        service = ModemService(audio or FakeAudio(devices=DEVICES), **options)
        services.append(service)
        return service, TestClient(create_app(service), base_url="http://127.0.0.1")

    yield make
    for service in services:
        service.close()


@pytest.fixture
def audio():
    return FakeAudio(devices=DEVICES)


@pytest.fixture
def client(made, audio):
    return made(audio)[1]


def idle(client):
    return wait_until(lambda: not client.get("/api/status").json()["sending"])


def test_the_page_is_served_and_names_the_application(client):
    page = client.get("/").text
    assert "Vibe AudioModem" in page and 'id="send"' in page and 'id="listen"' in page


def test_the_application_reports_it_is_idle(client):
    body = client.get("/api/status").json()
    assert body["sending"] is False and body["listening"] is False
    assert body["settings"]["preset"] == "standard"


def test_devices_are_listed_and_the_audio_library_reported(client):
    body = client.get("/api/devices").json()
    assert [d["name"] for d in body["devices"]] == ["Radio sound card", "Laptop microphone"]
    assert body["audio_library"] == "ok"


def test_a_missing_audio_library_is_reported_apart_from_missing_devices(made):
    class NoLibrary(FakeAudio):
        def list_devices(self):
            raise AudioLibraryUnavailableError("PortAudio not found")

    body = made(NoLibrary())[1].get("/api/devices").json()
    assert body["devices"] == [] and body["audio_library"].startswith("unavailable")


def test_the_settings_are_read_and_changed_as_a_whole(client):
    changed = client.post("/api/settings", json={"preset": "fast", "output_device": "radio"})
    assert changed.json() == {"preset": "fast", "input_device": None, "output_device": "radio"}
    assert client.get("/api/settings").json()["preset"] == "fast"


def test_a_device_can_be_set_back_to_the_default(client):
    client.post("/api/settings", json={"input_device": "laptop"})
    again = client.post("/api/settings", json={"input_device": None})
    assert again.json()["input_device"] is None


@pytest.mark.parametrize(
    "bad",
    [{"preset": "turbo-boost"}, {"input_device": "nothing"}, {"colour": "red"}, {"preset": 7}],
)
def test_invalid_settings_are_rejected_and_nothing_changes(client, bad):
    before = client.get("/api/settings").json()
    response = client.post("/api/settings", json={"output_device": "radio", **bad})
    assert response.status_code == 422 and response.json()["detail"]
    assert client.get("/api/settings").json() == before


def test_a_message_is_sent_and_the_airtime_returned(client, audio):
    client.post("/api/settings", json={"preset": "fast"})
    response = client.post("/api/send", json={"text": "bonjour"})
    assert response.status_code == 200
    body = response.json()
    assert body["fragments"] == 1 and body["airtime_seconds"] == pytest.approx(6.8)
    assert idle(client) and len(audio.played) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"text": "x", "copies": 0},
        {"text": "x", "copies": 9},
        {"text": 5},
        {"text": "x", "x": 1},
    ],
)
def test_a_send_with_invalid_fields_is_rejected_whole(client, audio, bad):
    assert client.post("/api/send", json=bad).status_code == 422
    assert audio.played == []


def test_a_message_that_is_too_long_is_refused_with_the_reason(client, audio):
    client.post("/api/settings", json={"preset": "max-range"})
    response = client.post("/api/send", json={"text": "x" * 600})
    assert response.status_code == 422
    assert "shorter Message" in response.json()["detail"] and audio.played == []


def test_sending_while_sending_is_a_conflict_and_cancel_frees_the_application(made):
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service, client = made(audio)
    client.post("/api/settings", json={"preset": "fast"})
    assert client.post("/api/send", json={"text": "one"}).status_code == 200
    assert wait_until(lambda: audio.playing)
    assert client.post("/api/send", json={"text": "two"}).status_code == 409
    assert client.post("/api/settings", json={"preset": "standard"}).status_code == 409
    assert client.post("/api/cancel").json() == {"cancelled": True}
    assert client.get("/api/status").json()["sending"] is False
    assert client.post("/api/cancel").json() == {"cancelled": False}


def test_listening_is_started_and_stopped_from_the_api(made):
    audio = FakeAudio(devices=DEVICES, loopback=True)
    service, client = made(audio)
    assert client.post("/api/listen/start").json() == {"listening": True}
    assert client.get("/api/status").json()["listening"] is True
    assert client.post("/api/listen/start").status_code == 409
    assert client.post("/api/listen/stop").json()["was_listening"] is True
    assert client.get("/api/status").json()["listening"] is False
    assert audio.open_listeners == 0


def test_a_message_goes_from_one_instance_to_the_other_through_the_api(made):
    sender_audio, listener_audio = FakeAudio(devices=DEVICES), FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    _, sender = made(sender_audio)
    _, listener = made(listener_audio)
    for client in (sender, listener):
        client.post("/api/settings", json={"preset": "fast"})
    listener.post("/api/listen/start")
    sender.post("/api/send", json={"text": "73 de F4XYZ"})
    assert idle(sender)
    listener.post("/api/listen/stop")
    (heard,) = listener.get("/api/received").json()["received"]
    assert heard["complete"] and heard["text"] == "73 de F4XYZ"


def test_a_recording_in_a_wav_file_is_received_through_the_api(made, tmp_path):
    modem = TurboModem(preset="fast")
    sound = transmit(modem, b"from a WAV file", "fast", msg_id=4)
    recording = np.concatenate([np.zeros(24_000), sound, np.zeros(24_000)])
    write_wav(tmp_path / "heard.wav", recording * 0.9)
    _, client = made(FakeAudio(devices=DEVICES, input_samples=read_wav(tmp_path / "heard.wav")))
    client.post("/api/settings", json={"preset": "fast"})
    client.post("/api/listen/start")
    assert wait_until(lambda: not client.get("/api/status").json()["listening"])  # input ends
    client.post("/api/listen/stop")
    (heard,) = client.get("/api/received").json()["received"]
    assert heard["text"] == "from a WAV file"


def test_the_selftest_runs_the_modem_against_itself(client):
    assert client.get("/api/selftest").json() == {"roundtrip_ok": True}


# Only this computer -----------------------------------------------------------------------------


def test_a_request_for_another_host_name_is_refused(client):
    response = client.get("/api/status", headers={"host": "evil.example.com"})
    assert response.status_code == 421


def test_a_request_from_a_page_of_another_site_is_refused(client, audio):
    response = client.post(
        "/api/send",
        json={"text": "hi"},
        headers={"origin": "http://evil.example.com", "host": "127.0.0.1:8765"},
    )
    assert response.status_code == 403 and audio.played == []


def test_the_applications_own_page_may_call_it(client):
    response = client.get(
        "/api/status", headers={"origin": "http://127.0.0.1:8765", "host": "127.0.0.1:8765"}
    )
    assert response.status_code == 200


# A real server ------------------------------------------------------------------------------


def get(port, path, method="GET"):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


def test_a_real_server_starts_serves_and_stops_leaving_nothing_behind():
    audio = FakeAudio(devices=DEVICES, loopback=True)
    service = ModemService(audio)
    threads_before = threading.active_count()
    port = free_port()
    server = make_server(service, port)
    thread = threading.Thread(target=server.run)
    thread.start()
    assert wait_until(lambda: server.started)
    assert get(port, "/api/health") == 200
    get(port, "/api/listen/start", method="POST")
    get(port, "/api/quit", method="POST")  # the page's Quit button
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert audio.open_listeners == 0  # closing the server closed the listening
    assert threading.active_count() <= threads_before
    with socket.socket() as probe:  # nobody listens on the port any more
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_the_server_listens_on_the_loopback_interface_only():
    server = make_server(ModemService(FakeAudio()), 0)
    assert server.config.host == "127.0.0.1"


def test_a_send_cancelled_before_it_played_is_a_conflict(made):
    from tests.test_service import GatedModem

    gate = {"entered": threading.Event(), "release": threading.Event()}
    audio = FakeAudio(devices=DEVICES)
    service = ModemService(audio, make_modem=lambda preset: GatedModem(gate, preset=preset))
    client = TestClient(create_app(service), base_url="http://127.0.0.1")
    client.post("/api/settings", json={"preset": "fast"})
    answer = {}
    thread = threading.Thread(
        target=lambda: answer.update(r=client.post("/api/send", json={"text": "x"}))
    )
    thread.start()
    assert gate["entered"].wait(timeout=10)
    assert client.post("/api/cancel").json() == {"cancelled": True}
    gate["release"].set()
    thread.join(timeout=10)
    assert answer["r"].status_code == 409 and audio.played == []
    service.close()


def test_a_device_listing_that_fails_for_another_reason_is_not_hidden(made):
    from vibemodem.io.audio import NoAudioDeviceError

    class Broken(FakeAudio):
        def list_devices(self):
            raise NoAudioDeviceError("cannot query the devices")

    body = made(Broken())[1].get("/api/devices").json()
    assert body["devices"] == [] and "cannot query" in body["error"]


def test_the_estimate_is_returned_without_any_sound(client, audio):
    client.post("/api/settings", json={"preset": "fast"})
    body = client.post("/api/estimate", json={"text": "bonjour", "copies": 2}).json()
    assert body["fits"] is True and body["fragments"] == 1
    assert body["airtime_seconds"] == pytest.approx(13.6)
    assert body["frequency_range_hz"] == [350.0, 2475.0] and body["default_frequency_hz"] == 1450.0
    assert audio.played == []


def test_the_estimate_of_a_message_that_is_too_long_says_why(client):
    client.post("/api/settings", json={"preset": "max-range"})
    body = client.post("/api/estimate", json={"text": "x" * 600}).json()
    assert body["fits"] is False and "shorter Message" in body["reason"]


@pytest.mark.parametrize("bad", [{"text": "x", "copies": 0}, {"copies": 1}, {"text": "x", "x": 1}])
def test_an_estimate_with_invalid_fields_is_rejected(client, bad):
    assert client.post("/api/estimate", json=bad).status_code == 422


def test_a_message_is_sent_at_the_frequency_asked_for_through_the_api(client, audio):
    client.post("/api/settings", json={"preset": "fast"})
    assert client.post("/api/send", json={"text": "hi", "frequency_hz": 900}).status_code == 200
    assert idle(client)
    sound = audio.played[0]
    power = np.abs(np.fft.rfft(sound)) ** 2
    centre = (np.fft.rfftfreq(sound.size, 1 / 48_000) * power).sum() / power.sum()
    assert centre - 87.5 == pytest.approx(900, abs=15)  # the middle of the 8 tones, less 3.5 x 25


def test_a_frequency_out_of_range_is_rejected_with_the_range(client, audio):
    client.post("/api/settings", json={"preset": "fast"})
    response = client.post("/api/send", json={"text": "hi", "frequency_hz": 100})
    assert response.status_code == 422 and "350 and 2475" in response.json()["detail"]
    assert audio.played == []


def test_the_page_is_the_html_file_next_to_the_module(client):
    from pathlib import Path

    import vibemodem.app

    html = (Path(vibemodem.app.__file__).parent / "page.html").read_text(encoding="utf-8")
    assert client.get("/").text == html and html.startswith("<!doctype html>")


def test_the_page_file_is_shipped_with_the_package_and_the_packaged_application():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    package_data = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["setuptools"]
    assert "page.html" in package_data["package-data"]["vibemodem.app"]
    assert "page.html" in (root / "packaging" / "vibemodem.spec").read_text()


def test_the_received_messages_come_with_how_they_were_received(made):
    sender_audio, listener_audio = FakeAudio(devices=DEVICES), FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    _, sender = made(sender_audio)
    _, listener = made(listener_audio)
    for client in (sender, listener):
        client.post("/api/settings", json={"preset": "fast"})
    listener.post("/api/listen/start")
    sender.post("/api/send", json={"text": "with quality", "frequency_hz": 1700})
    assert idle(sender)
    listener.post("/api/listen/stop")
    body = listener.get("/api/received").json()
    (heard,) = body["received"]
    assert heard["frequency_hz"] == pytest.approx(1700, abs=3) and heard["sync_score"] > 7
    assert heard["offset_hz"] == pytest.approx(250, abs=3) and heard["snr_db"] is not None
    assert body["undecoded"] == []


def test_the_spectrum_is_served_from_the_row_asked_for(made):
    tone = 0.3 * np.sin(2 * np.pi * 1500 * np.arange(48_000 * 2) / 48_000)
    audio = FakeAudio(devices=DEVICES, input_samples=tone)
    service, client = made(audio)
    client.post("/api/listen/start")
    assert wait_until(lambda: not client.get("/api/status").json()["listening"])
    body = client.get("/api/spectrum").json()
    assert (body["first"], body["next"], body["low_hz"], body["bin_hz"]) == (0, 4, 300.0, 5.0)
    assert len(body["rows"]) == 4 and all(len(row) == 480 for row in body["rows"])
    assert client.get("/api/spectrum", params={"since": 3}).json()["rows"] == body["rows"][3:]
    assert client.get("/api/spectrum", params={"since": 4}).json()["rows"] == []


@pytest.mark.parametrize("since", ["-1", "abc"])
def test_a_spectrum_request_with_a_bad_row_number_is_rejected(client, since):
    assert client.get("/api/spectrum", params={"since": since}).status_code == 422

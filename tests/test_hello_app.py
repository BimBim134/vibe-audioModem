"""The packaging-spike application, exercised through its local HTTP API with a fake device."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vibemodem.app.hello import create_app
from vibemodem.io.recorder import AudioLibraryUnavailableError, NoInputDeviceError


def make_client(record=None, devices=None, quits=None):
    def fake_record(seconds, device=None):
        return np.full(int(48_000 * seconds), 0.5, dtype=np.float32)

    def fake_devices():
        return [{"index": 3, "name": "Fake microphone", "max_input_channels": 1}]

    app = create_app(
        record=record or fake_record,
        list_devices=devices or fake_devices,
        on_quit=(lambda: quits.append(True)) if quits is not None else (lambda: None),
    )
    return TestClient(app)


def test_page_is_served_with_a_record_button():
    response = make_client().get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Record 5 seconds" in response.text


def test_health_reports_ok():
    assert make_client().get("/api/health").json() == {"status": "ok"}


def test_devices_are_listed():
    devices = make_client().get("/api/devices").json()["devices"]
    assert [d["name"] for d in devices] == ["Fake microphone"]


def test_devices_report_that_the_audio_library_works():
    assert make_client().get("/api/devices").json()["audio_library"] == "ok"


def test_devices_report_when_the_audio_library_itself_is_missing():
    def missing():
        raise AudioLibraryUnavailableError("PortAudio not found")

    body = make_client(devices=missing).get("/api/devices").json()
    assert body["devices"] == []
    assert body["audio_library"].startswith("unavailable")


def test_devices_list_is_empty_when_no_audio_is_available():
    def broken():
        raise NoInputDeviceError("no portaudio")

    body = make_client(devices=broken).get("/api/devices").json()
    assert body == {"devices": [], "audio_library": "ok"}


def test_record_reports_length_and_level_of_the_captured_audio():
    body = make_client().post("/api/record", json={"seconds": 5}).json()
    assert body["samples"] == 240_000
    assert body["rms"] == pytest.approx(0.5)
    assert body["peak"] == pytest.approx(0.5)


def test_record_without_an_input_device_is_a_clear_error():
    def no_device(seconds, device=None):
        raise NoInputDeviceError("Error querying device -1")

    response = make_client(record=no_device).post("/api/record", json={"seconds": 5})
    assert response.status_code == 503
    assert "No usable audio input" in response.json()["detail"]


@pytest.mark.parametrize("seconds", [0, -1, 31])
def test_record_rejects_a_duration_out_of_range(seconds):
    assert make_client().post("/api/record", json={"seconds": seconds}).status_code == 422


def test_selftest_finds_the_generated_tone():
    body = make_client().get("/api/selftest").json()
    assert body["tone_hz"] == 1000
    assert body["detected_hz"] == pytest.approx(1000, abs=1)


def test_quit_asks_the_application_to_stop():
    quits = []
    assert make_client(quits=quits).post("/api/quit").status_code == 200
    assert quits == [True]

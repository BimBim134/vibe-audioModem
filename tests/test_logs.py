"""The log file: what the application did and what went wrong, to find the cause of a bug."""

import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from vibemodem import version as version_module
from vibemodem.app import logs
from vibemodem.app.api import create_app
from vibemodem.app.service import ModemService
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


@pytest.fixture
def log_file(tmp_path):
    path = logs.setup(tmp_path)
    yield path
    logs.teardown()


def written(path) -> str:
    for handler in logging.getLogger("vibemodem").handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def wait_idle(service):
    deadline = time.monotonic() + 30
    while service.status()["sending"] and time.monotonic() < deadline:
        time.sleep(0.01)


# The file and its start-up lines ---------------------------------------------------------------


def test_the_log_starts_with_what_is_needed_to_understand_a_report(log_file):
    logs.banner(["--port", "0"])
    text = written(log_file)
    assert f"Vibe AudioModem {version_module.version()}" in text
    for word in ("Python ", "system:", "sounddevice", "arguments: --port 0"):
        assert word in text, word


def test_each_line_has_a_time_a_level_and_the_part_that_wrote_it(log_file):
    logging.getLogger("vibemodem.audio").warning("something odd")
    (line,) = [x for x in written(log_file).splitlines() if "something odd" in x]
    assert line[4] == "-" and "WARNING" in line and "vibemodem.audio" in line


def test_the_log_is_cut_into_a_few_files_of_bounded_size(tmp_path):
    path = logs.setup(tmp_path, max_bytes=2_000, backups=2)
    try:
        for number in range(500):
            logging.getLogger("vibemodem").info("line number %d %s", number, "x" * 60)
        names = sorted(p.name for p in tmp_path.glob("vibemodem.log*"))
        assert names == ["vibemodem.log", "vibemodem.log.1", "vibemodem.log.2"]
        assert path.stat().st_size <= 2_500
    finally:
        logs.teardown()


def test_setting_up_twice_does_not_write_each_line_twice(tmp_path):
    logs.setup(tmp_path)
    path = logs.setup(tmp_path)
    try:
        logging.getLogger("vibemodem").info("once")
        assert written(path).count("once") == 1
    finally:
        logs.teardown()


def test_a_folder_that_cannot_be_written_does_not_stop_the_application(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    try:
        assert logs.setup(blocked / "sub") is None
        logging.getLogger("vibemodem").info("goes nowhere, harmlessly")
    finally:
        logs.teardown()


def test_the_level_can_be_made_more_detailed(tmp_path):
    path = logs.setup(tmp_path, level="DEBUG")
    try:
        logging.getLogger("vibemodem.x").debug("fine detail")
        assert "fine detail" in written(path)
    finally:
        logs.teardown()
    path = logs.setup(tmp_path, level="INFO")
    try:
        logging.getLogger("vibemodem.x").debug("fine detail again")
        assert "fine detail again" not in written(path)
    finally:
        logs.teardown()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_an_error_that_nobody_caught_is_in_the_log_with_its_trace(log_file):
    def fail():
        raise RuntimeError("boom in a thread")

    thread = threading.Thread(target=fail)
    thread.start()
    thread.join()
    text = written(log_file)
    assert "boom in a thread" in text and "Traceback" in text


# What the application writes -------------------------------------------------------------------


def test_a_send_is_logged_without_the_text_of_the_message(log_file):
    service = ModemService(FakeAudio(devices=DEVICES))
    try:
        service.apply_settings(preset="fast")
        service.send("a private sentence")
        wait_idle(service)
    finally:
        service.close()
    text = written(log_file)
    assert "a private sentence" not in text
    assert "sending" in text and "fast" in text and "sent" in text


def test_a_sound_card_that_fails_is_logged_as_an_error(log_file):
    class Broken(FakeAudio):
        def play(self, samples, device=None):
            raise OSError("the sound card is gone")

    service = ModemService(Broken(devices=DEVICES))
    try:
        service.send("x")
        wait_idle(service)
    finally:
        service.close()
    assert "ERROR" in written(log_file) and "the sound card is gone" in written(log_file)


def test_settings_that_change_are_logged(log_file):
    service = ModemService(FakeAudio(devices=DEVICES))
    try:
        service.apply_settings(preset="fast", copies=2)
    finally:
        service.close()
    assert "preset" in written(log_file) and "fast" in written(log_file)


# The version, and the way to get the log -----------------------------------------------------


def test_the_version_is_known_and_so_is_the_git_state_of_a_checkout():
    assert version_module.version() not in ("", None)
    info = version_module.describe()
    assert info["version"] == version_module.version()
    assert info["git"] is None or isinstance(info["git"], str)


def test_without_git_the_version_is_still_given(monkeypatch):
    def no_git(*_args, **_options):
        raise FileNotFoundError("git")

    monkeypatch.setattr(version_module.subprocess, "run", no_git)
    assert version_module.git_description() is None
    assert version_module.describe()["version"]


def test_the_log_and_the_version_are_served(log_file):
    service = ModemService(FakeAudio(devices=DEVICES))
    try:
        client = TestClient(create_app(service), base_url="http://127.0.0.1")
        logs.banner([])
        answer = client.get("/api/log")
        assert answer.status_code == 200 and answer.headers["content-type"].startswith("text/plain")
        assert "attachment" in answer.headers["content-disposition"]
        assert "Vibe AudioModem" in answer.text
        about = client.get("/api/about").json()
        assert about["version"] == version_module.version()
    finally:
        service.close()


def test_without_a_log_file_the_download_says_so():
    service = ModemService(FakeAudio(devices=DEVICES))
    try:
        client = TestClient(create_app(service), base_url="http://127.0.0.1")
        assert client.get("/api/log").status_code == 404
    finally:
        service.close()

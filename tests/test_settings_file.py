"""The settings kept between sessions: what the service remembers across a restart."""

import json

import pytest

from vibemodem.app.service import MEGABYTE, BusyError, ModemService
from vibemodem.app.settings_file import SettingsFile
from vibemodem.app.store import ReceptionStore
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [
    DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0),
    DeviceInfo(1, "Laptop microphone", 1, 0, 48_000.0),
]


@pytest.fixture
def start(tmp_path):
    """Start the application again and again on the same folder, as a user restarting it."""
    made = []

    def make(devices=DEVICES, **audio_options):
        store = ReceptionStore(tmp_path, 200 * MEGABYTE)
        service = ModemService(
            FakeAudio(devices=devices, **audio_options),
            store=store,
            settings_file=SettingsFile(tmp_path / "s.json"),
        )
        made.append(service)
        return service

    yield make
    for service in made:
        service.close()


def test_the_settings_survive_a_restart(start):
    first = start()
    first.apply_settings(preset="fast", input_device="Laptop microphone", output_device=0)
    first.apply_settings(copies=3)
    first.set_storage(keep=True, limit_mb=300)
    first.close()

    again = start()
    assert again.settings.preset == "fast"
    assert again.settings.input_device == "Laptop microphone"
    assert again.settings.output_device == 0
    assert again.settings.copies == 3
    assert again.storage()["keep"] is True and again.storage()["limit_mb"] == 300


def test_without_a_settings_file_the_defaults_are_used(start):
    service = start()
    assert service.settings.preset == "standard" and service.settings.copies == 1
    assert service.settings.input_device is None and service.storage()["keep"] is False


@pytest.mark.parametrize("content", ["", "not json at all", "[1, 2]", '{"preset": ', "null"])
def test_a_damaged_settings_file_falls_back_to_the_defaults(start, tmp_path, content):
    (tmp_path / "s.json").write_text(content)
    service = start()
    assert service.settings.preset == "standard"
    service.apply_settings(preset="fast")  # and the application goes on working
    assert start().settings.preset == "fast"


def test_a_bad_value_is_ignored_and_the_good_ones_are_kept(start, tmp_path):
    (tmp_path / "s.json").write_text(
        json.dumps({"preset": "warp", "copies": 99, "limit_mb": 5, "keep": "yes", "unknown": 1})
    )
    service = start()
    assert service.settings.preset == "standard" and service.settings.copies == 1
    assert service.storage()["limit_mb"] == 200 and service.storage()["keep"] is False
    (tmp_path / "s.json").write_text(json.dumps({"preset": "fast", "copies": 99}))
    kept = start()
    assert kept.settings.preset == "fast" and kept.settings.copies == 1


def test_the_listening_band_is_not_kept(start, tmp_path):
    first = start()
    first.set_search_band(1000.0, 2000.0)
    first.apply_settings(preset="fast")
    assert "band" not in (tmp_path / "s.json").read_text()
    assert start().search_band() is None


def test_a_device_that_is_not_there_is_ignored_but_remembered(start, tmp_path):
    start().apply_settings(input_device="Laptop microphone")
    unplugged = start(devices=[DEVICES[0]])
    assert unplugged.settings.input_device is None
    unplugged.apply_settings(preset="fast")  # another change does not forget the device
    assert json.loads((tmp_path / "s.json").read_text())["input_device"] == "Laptop microphone"
    assert start().settings.input_device == "Laptop microphone"


def test_the_number_of_copies_can_change_while_listening_but_not_the_rest(start):
    service = start(loopback=True)  # the sound card keeps listening
    service.start_listening()
    assert service.apply_settings(copies=2).copies == 2
    with pytest.raises(BusyError):
        service.apply_settings(preset="fast")
    assert service.settings.preset == "standard"


def test_a_settings_file_that_cannot_be_written_does_not_stop_the_application(start, tmp_path):
    service = start()
    (tmp_path / "s.json").mkdir()  # a folder where the file should be
    service.apply_settings(preset="fast")
    assert service.settings.preset == "fast"


def test_the_folder_is_made_when_the_first_setting_is_written(tmp_path):
    file = SettingsFile(tmp_path / "new" / "folder" / "s.json")
    assert file.read() == {}
    file.update(preset="fast")
    assert file.read() == {"preset": "fast"}

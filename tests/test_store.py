"""The reception store: audio and indicators on disk, bounded, deleted on request."""

import json

import numpy as np
import pytest

from vibemodem.app.store import ReceptionStore, default_directory
from vibemodem.io.wav import read_wav

FS = 48_000


def sound(seconds=1.0, level=0.3):
    return level * np.sin(2 * np.pi * 1000 * np.arange(round(seconds * FS)) / FS)


def indicators(**more):
    return {"decoded": True, "snr_db": -8.0, **more}


@pytest.fixture
def store(tmp_path):
    return ReceptionStore(tmp_path / "receptions", max_bytes=10_000_000)


def test_a_reception_is_one_wav_and_one_json_side_by_side(store):
    path = store.save(sound(), indicators(preset="fast"))
    assert path.suffix == ".wav" and path.with_suffix(".json").exists()
    assert np.allclose(read_wav(path), sound(), atol=1e-4)
    saved = json.loads(path.with_suffix(".json").read_text())
    assert saved["snr_db"] == -8.0 and saved["preset"] == "fast" and saved["schema_version"] == 1
    assert saved["wav"] == path.name


def test_the_directory_is_made_when_the_first_reception_is_kept(tmp_path):
    ReceptionStore(tmp_path / "a" / "b", max_bytes=1_000_000).save(sound(0.1), indicators())
    assert (tmp_path / "a" / "b").is_dir()


def test_nothing_is_made_on_disk_before_a_reception_is_kept(tmp_path):
    store = ReceptionStore(tmp_path / "never", max_bytes=1_000_000)
    assert store.usage() == (0, 0) and not (tmp_path / "never").exists()


def test_usage_counts_the_receptions_and_their_bytes(store):
    store.save(sound(1.0), indicators())
    store.save(sound(2.0), indicators())
    count, used = store.usage()
    assert count == 2 and 280_000 < used < 330_000  # 3 s of 16-bit sound, and two small JSON


def test_the_oldest_receptions_go_first_when_the_bound_is_passed(tmp_path):
    store = ReceptionStore(tmp_path, max_bytes=250_000)  # room for about two seconds
    first = store.save(sound(1.0), indicators(number=1))
    second = store.save(sound(1.0), indicators(number=2))
    third = store.save(sound(1.0), indicators(number=3))
    names = sorted(p.name for p in tmp_path.glob("*.wav"))
    assert names == sorted([second.name, third.name]) and not first.exists()
    assert not first.with_suffix(".json").exists()  # both files of a reception go together
    assert store.usage()[1] <= 250_000


def test_a_reception_that_alone_passes_the_bound_is_not_kept_and_says_so(tmp_path):
    store = ReceptionStore(tmp_path, max_bytes=50_000)
    with pytest.raises(ValueError, match="bound"):
        store.save(sound(2.0), indicators())
    assert list(tmp_path.glob("*")) == []


def test_the_bound_can_be_changed_and_applies_at_once(store):
    for number in range(4):
        store.save(sound(1.0), indicators(number=number))
    store.set_max_bytes(200_000)
    assert store.usage()[0] == 2 and store.usage()[1] <= 200_000


def test_everything_can_be_deleted_and_nothing_else_is_touched(store, tmp_path):
    store.save(sound(0.2), indicators())
    (tmp_path / "receptions" / "notes.txt").write_text("mine")
    assert store.clear() == 1
    assert store.usage() == (0, 0)
    assert (tmp_path / "receptions" / "notes.txt").read_text() == "mine"


def test_receptions_are_listed_oldest_first_with_their_indicators(store):
    for number in range(3):
        store.save(sound(0.1), indicators(number=number))
    assert [saved["number"] for _, saved in store.receptions()] == [0, 1, 2]


def test_two_receptions_in_the_same_millisecond_do_not_overwrite_each_other(store):
    paths = {store.save(sound(0.05), indicators()) for _ in range(20)}
    assert len(paths) == 20 and store.usage()[0] == 20


def test_the_default_directory_is_the_one_of_the_platform(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_directory() == tmp_path / "xdg" / "vibemodem" / "receptions"
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_directory() == tmp_path / ".local" / "share" / "vibemodem" / "receptions"
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert default_directory() == tmp_path / "local" / "VibeModem" / "receptions"
    monkeypatch.setattr("sys.platform", "darwin")
    assert default_directory() == (
        tmp_path / "Library" / "Application Support" / "VibeModem" / "receptions"
    )


def test_a_bound_that_makes_no_sense_is_refused(tmp_path):
    for bad in (0, -5, 1.5, True):
        with pytest.raises(ValueError, match="bound"):
            ReceptionStore(tmp_path, max_bytes=bad)


# After the reviews -------------------------------------------------------------------------


def test_a_reception_that_is_bigger_than_the_bound_with_its_json_is_refused(tmp_path):
    store = ReceptionStore(
        tmp_path, max_bytes=96_100
    )  # the sound fits (96,044), the JSON on top not
    with pytest.raises(ValueError, match="bound"):
        store.save(sound(1.0), indicators())
    assert store.usage() == (0, 0)


def test_a_json_that_is_damaged_does_not_break_the_list(store):
    good = store.save(sound(0.1), indicators(number=1))
    bad = store.save(sound(0.1), indicators(number=2))
    bad.with_suffix(".json").write_text("{ truncated")
    third = store.save(sound(0.1), indicators(number=3))
    third.with_suffix(".json").write_text("[1, 2]")  # valid JSON, but not a reception
    assert [saved["number"] for _, saved in store.receptions()] == [1]
    assert good.exists()


def test_a_wav_without_its_json_is_not_a_reception_and_is_cleaned_away(store, tmp_path):
    orphan = store.directory / "20260101-000000-000-0000.wav"
    store.directory.mkdir(parents=True)
    orphan.write_bytes(b"RIFF")
    assert store.usage()[0] == 0 and store.receptions() == []
    store.save(sound(0.1), indicators())
    assert not orphan.exists()  # cleaned at the next save


def test_a_write_that_fails_leaves_nothing_behind(store, monkeypatch):
    def broken(self, text, encoding=None):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.write_text", broken)
    with pytest.raises(OSError, match="no space"):
        store.save(sound(0.1), indicators())
    assert [p.name for p in store.directory.iterdir()] == []


def test_names_that_are_not_ours_and_links_are_never_counted_read_or_deleted(store, tmp_path):
    store.save(sound(0.1), indicators())
    odd = store.directory / "20260101-000000-000-0000.wav\n"
    odd.write_bytes(b"x" * 500)
    link = store.directory / "20260101-000000-001-0000.json"
    link.symlink_to(tmp_path)
    assert store.clear() == 1
    assert odd.exists() and link.is_symlink()


def test_the_order_is_the_order_of_time_in_utc(store):
    import re

    names = [store.save(sound(0.05), indicators()).name for _ in range(3)]
    assert names == sorted(names) and all(
        re.fullmatch(r"\d{8}-\d{6}-\d{3}-\d{4}\.wav", n) for n in names
    )


def test_numbers_that_json_does_not_know_are_written_as_numbers_or_nothing(store):
    path = store.save(
        sound(0.05),
        indicators(
            a=np.float32(1.5), b=np.int64(3), c=float("nan"), d=float("inf"), e=[np.float64(2)]
        ),
    )
    saved = json.loads(path.with_suffix(".json").read_text())
    assert saved["a"] == 1.5 and saved["b"] == 3 and saved["c"] is None and saved["d"] is None
    assert saved["e"] == [2.0]


def test_saving_listing_and_deleting_at_once_from_several_threads_stays_consistent(store):
    import threading

    errors = []

    def writer():
        try:
            for _ in range(15):
                store.save(sound(0.05), indicators())
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    def reader():
        try:
            for _ in range(40):
                store.usage()
                store.receptions()
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    def cleaner():
        try:
            for _ in range(10):
                store.clear()
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=f) for f in (writer, writer, reader, reader, cleaner)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert errors == []

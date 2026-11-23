"""The history: each Message sent or received is kept in a SQLite file and shown again when the
application starts. Sound is never kept in it."""

import csv
import io
import sqlite3
import time

import pytest

from vibemodem.app.history import History
from vibemodem.app.service import ModemService
from vibemodem.io.audio import DeviceInfo, FakeAudio

DEVICES = [DeviceInfo(0, "Radio sound card", 1, 1, 48_000.0)]


def wait_until(condition, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def path(tmp_path):
    return tmp_path / "history.sqlite3"


@pytest.fixture
def make(path):
    made = []

    def build(audio=None, **options):
        service = ModemService(
            audio or FakeAudio(devices=DEVICES), history=History(path), **options
        )
        made.append(service)
        return service

    yield build
    for service in made:
        service.close()


def send_and_wait(service, text):
    service.send(text)
    assert wait_until(lambda: not service.status()["sending"])


def rows(path):
    return History(path).rows()


def parsed(path):
    text = History(path).export_csv().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))


# What is written -------------------------------------------------------------------------------


def test_a_sent_message_is_in_the_history_with_its_figures(make, path):
    app = make()
    app.apply_settings(preset="fast", callsign="f4jbo")
    send_and_wait(app, "hello")
    (row,) = rows(path)
    assert (row["direction"], row["state"], row["preset"]) == ("sent", "sent", "fast")
    assert (row["text"], row["callsign"]) == ("F4JBO: hello", "F4JBO")
    assert row["frequency_hz"] == 1450.0 and row["snr_db"] is None


def test_a_cancelled_or_failed_message_says_so(make, path):
    class Broken(FakeAudio):
        def play(self, samples, device=None):
            raise OSError("the sound card is gone")

    app = make(Broken(devices=DEVICES))
    send_and_wait(app, "lost")
    assert [r["state"] for r in rows(path)] == ["failed"]
    assert rows(path)[0]["detail"]["error"] == "the sound card is gone"


def test_a_received_message_is_in_the_history_with_its_figures(make, path):
    sender_audio, listener_audio = FakeAudio(devices=DEVICES), FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    sender, listener = make(sender_audio), make(listener_audio)
    sender.apply_settings(preset="fast", callsign="F4JBO")
    listener.apply_settings(preset="fast")
    listener.start_listening()
    send_and_wait(sender, "hello")
    listener.stop_listening()
    received = [r for r in rows(path) if r["direction"] == "received"]
    (row,) = received
    assert (row["text"], row["callsign"], row["state"], row["preset"]) == (
        "F4JBO: hello",
        "F4JBO",
        "complete",
        "fast",
    )
    assert row["snr_db"] is not None and row["frequency_hz"] == pytest.approx(1450.0, abs=30.0)


def test_a_message_heard_in_part_is_written_when_the_listening_stops(make, path):
    sender_audio = FakeAudio(devices=DEVICES, play_seconds=1.0)
    listener_audio = FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    sender, listener = make(sender_audio), make(listener_audio)
    for each in (sender, listener):
        each.apply_settings(preset="fast")
    listener.start_listening()
    sender.send("A" * 40)  # 3 Fragments
    assert wait_until(lambda: sender_audio.playing)
    time.sleep(0.5)
    sender.cancel()
    listener.stop_listening()
    (row,) = [r for r in rows(path) if r["direction"] == "received"]
    assert row["state"] == "incomplete" and row["detail"]["total"] == 3
    listener.stop_listening()  # again: not written twice
    assert len([r for r in rows(path) if r["direction"] == "received"]) == 1


def test_the_file_is_made_with_the_first_message_and_not_before(make, path):
    make()
    assert not path.exists()


def test_a_history_that_cannot_be_written_is_told_and_does_not_stop_sending(make, tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    app = ModemService(FakeAudio(devices=DEVICES), history=History(blocked / "history.sqlite3"))
    try:
        send_and_wait(app, "still sent")
        assert app.conversation()[-1]["status"] == "sent"
        assert "history" in app.status()["last_error"]
    finally:
        app.close()


# What is shown again ---------------------------------------------------------------------------


def test_the_conversation_is_shown_again_when_the_application_starts(make, path):
    sender_audio, listener_audio = FakeAudio(devices=DEVICES), FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    first_sender, first_listener = make(sender_audio), make(listener_audio)
    for each in (first_sender, first_listener):
        each.apply_settings(preset="fast")
    first_listener.start_listening()
    send_and_wait(first_sender, "hello")
    first_listener.stop_listening()
    for each in (first_sender, first_listener):
        each.close()

    again = make()
    items = again.conversation()
    assert [(i["kind"], i["text"]) for i in items] == [
        ("sent", "hello"),
        ("received", "hello"),
    ] or [(i["kind"], i["text"]) for i in items] == [("received", "hello"), ("sent", "hello")]
    sent = next(i for i in items if i["kind"] == "sent")
    assert sent["status"] == "sent" and sent["id"].startswith("h")
    assert next(i for i in items if i["kind"] == "received")["snr_db"] is not None


def test_a_message_heard_in_part_is_shown_again_as_such(make, path):
    History(path).add(
        at=1000.0, direction="received", text="AAAA", frequency_hz=1450.0, snr_db=-12.0,
        preset="fast", state="incomplete",
        detail={"parts": [[0, "AAAA"]], "missing": [1, 2], "total": 3},
    )  # fmt: skip
    (item,) = make().conversation()
    assert item["kind"] == "incomplete" and item["parts"] == [[0, "AAAA"]]
    assert item["missing"] == [1, 2] and item["total"] == 3


def test_the_history_is_in_order_with_what_happens_now(make, path):
    History(path).add(
        at=1000.0, direction="received", text="old", frequency_hz=None, snr_db=None,
        preset="fast", state="complete",
    )  # fmt: skip
    app = make()
    send_and_wait(app, "new")
    assert [i["text"] for i in app.conversation()] == ["old", "new"]


def test_only_the_latest_messages_are_shown_again(make, path):
    history = History(path)
    for number in range(1_050):
        history.add(
            at=float(number), direction="received", text=str(number), frequency_hz=None,
            snr_db=None, preset="fast", state="complete",
        )  # fmt: skip
    items = make().conversation()
    assert len(items) == 1_000 and items[0]["text"] == "50" and items[-1]["text"] == "1049"
    assert len(rows(path)) == 1_050  # all of them are still kept and exported


# Clearing --------------------------------------------------------------------------------------


def test_clearing_the_history_empties_the_page_and_the_file(make, path):
    app = make()
    send_and_wait(app, "one")
    assert app.clear_history() == 1
    assert app.conversation() == [] and rows(path) == []
    send_and_wait(app, "two")
    assert [i["text"] for i in make().conversation()] == ["two"]


def test_clearing_an_empty_history_is_nothing(make):
    assert make().clear_history() == 0


# The CSV export --------------------------------------------------------------------------------


def test_the_csv_opens_in_a_french_spreadsheet(make, path):
    app = make()
    app.apply_settings(preset="fast", callsign="F4JBO")
    send_and_wait(app, 'héllo; "world"\nsecond line')
    data = History(path).export_csv()
    assert data.startswith(b"\xef\xbb\xbf")  # byte order mark
    header, row = parsed(path)
    assert header == [
        "time", "direction", "callsign", "text", "frequency_hz", "snr_db", "preset", "state"
    ]  # fmt: skip
    assert row[1:4] == ["sent", "F4JBO", 'F4JBO: héllo; "world"\nsecond line']
    assert row[4] == "1450.0" and row[5] == "" and row[6:] == ["fast", "sent"]
    assert len(row[0]) == 19 and row[0][4] == "-"  # 2026-11-23 08:30:00, UTC


def test_a_text_that_a_spreadsheet_would_run_is_made_harmless(path):
    for text in ("=1+1", "+cmd", "-2", "@SUM(A1)"):
        History(path).add(
            at=1.0, direction="received", text=text, frequency_hz=1450.0, snr_db=-12.5,
            preset="fast", state="complete",
        )  # fmt: skip
    cells = [row[3] for row in parsed(path)[1:]]
    assert cells == ["'=1+1", "'+cmd", "'-2", "'@SUM(A1)"]
    assert parsed(path)[1][5] == "-12.5"  # a negative SNR stays a number


def test_an_empty_history_exports_the_header_only(path):
    assert len(parsed(path)) == 1


def test_a_damaged_file_is_an_empty_history(make, path):
    path.write_bytes(b"this is not a database at all" * 100)
    assert make().conversation() == []
    assert History(path).rows() == []


def test_sound_is_never_kept(make, path):
    send_and_wait(make(), "hello")
    with sqlite3.connect(path) as link:
        columns = [c[1] for c in link.execute("PRAGMA table_info(messages)")]
    assert not any("audio" in c or "sound" in c or "samples" in c for c in columns)

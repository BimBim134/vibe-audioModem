"""The conversation: what was sent and what was heard, in one line of time."""

import time

import pytest
from fastapi.testclient import TestClient

from vibemodem.app.api import create_app
from vibemodem.app.conversation import SentEntry, build_conversation
from vibemodem.app.heard import Heard, Undecoded
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


def heard(at, text="hello", complete=True, **more):
    fields = dict(
        number=1 if complete else None, complete=complete, msg_id=3, total=1,
        text=text if complete else None, parts=[] if complete else [(0, "he")],
        missing=() if complete else (1,), heard_at=at, snr_db=-8.0,
        frequency_hz=1700.0, offset_hz=250.0, sync_score=40.0,
    )  # fmt: skip
    return Heard(**{**fields, **more})


def test_everything_is_put_in_the_order_of_its_time():
    sent = SentEntry(id=1, text="out", at=200.0, status="sent", fragments=1, copies=1,
                     frequency_hz=1450.0, airtime_seconds=7.0)  # fmt: skip
    items = build_conversation(
        [sent], [heard(300.0, "late"), heard(100.0, "early")], [Undecoded(250.0, 1450.0, 20.0)]
    )
    assert [i["kind"] for i in items] == ["received", "sent", "lost", "received"]
    assert [i["at"] for i in items] == [100.0, 200.0, 250.0, 300.0]


def test_a_sent_message_carries_what_the_page_shows_of_it():
    sent = SentEntry(id=4, text="out", at=1.0, status="sending", fragments=3, copies=2,
                     frequency_hz=900.0, airtime_seconds=40.0)  # fmt: skip
    (item,) = build_conversation([sent], [], [])
    assert item == {
        "kind": "sent", "id": "s4", "at": 1.0, "text": "out", "status": "sending",
        "fragments": 3, "copies": 2, "frequency_hz": 900.0, "airtime_seconds": 40.0,
        "error": None,
    }  # fmt: skip


def test_a_message_received_says_how_it_was_received_and_a_partial_one_what_is_missing():
    whole, part = build_conversation([], [heard(1.0), heard(2.0, complete=False)], [])
    assert whole["kind"] == "received" and whole["text"] == "hello"
    assert (whole["frequency_hz"], whole["snr_db"]) == (1700.0, -8.0)
    assert part["kind"] == "incomplete" and part["parts"] == [[0, "he"]] and part["missing"] == [1]
    assert part["total"] == 1 and part["id"] != whole["id"]


def test_a_lost_signal_is_a_line_with_its_frequency():
    (item,) = build_conversation([], [], [Undecoded(5.0, 1480.0, 22.0)])
    assert item["kind"] == "lost" and item["frequency_hz"] == 1480.0 and item["at"] == 5.0


def test_the_same_things_keep_the_same_identifiers_from_one_call_to_the_next():
    def again():
        lost = [Undecoded(3.0, 1450.0, 20.0)]
        return build_conversation([], [heard(1.0), heard(2.0, complete=False)], lost)

    assert [i["id"] for i in again()] == [i["id"] for i in again()]


# The service keeps what it sends -------------------------------------------------------------


def service_with(audio=None, **options):
    service = ModemService(audio or FakeAudio(devices=DEVICES), **options)
    service.apply_settings(preset="fast")
    return service


def test_a_message_sent_is_in_the_conversation_from_the_moment_it_starts_to_play():
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service = service_with(audio)
    try:
        service.send("hello there", copies=2, frequency_hz=900.0)
        (item,) = service.conversation()
        assert item["kind"] == "sent" and item["text"] == "hello there"
        assert item["status"] == "sending" and item["copies"] == 2 and item["frequency_hz"] == 900.0
        assert item["airtime_seconds"] == pytest.approx(13.6)
    finally:
        service.close()


def test_it_is_sent_once_the_sound_has_been_played():
    service = service_with()
    try:
        service.send("done")
        assert wait_until(lambda: not service.status()["sending"])
        assert [i["status"] for i in service.conversation()] == ["sent"]
    finally:
        service.close()


def test_it_is_cancelled_when_it_was_cut_short():
    audio = FakeAudio(devices=DEVICES, play_seconds=30.0)
    service = service_with(audio)
    try:
        service.send("cut")
        assert wait_until(lambda: audio.playing)
        service.cancel()
        assert [i["status"] for i in service.conversation()] == ["cancelled"]
    finally:
        service.close()


def test_it_failed_when_the_sound_card_failed_and_says_why():
    class Broken(FakeAudio):
        def play(self, samples, device=None):
            raise RuntimeError("the output was unplugged")

    service = service_with(Broken(devices=DEVICES))
    try:
        service.send("lost")
        assert wait_until(lambda: not service.status()["sending"])
        (item,) = service.conversation()
        assert item["status"] == "failed" and "unplugged" in item["error"]
    finally:
        service.close()


def test_a_message_that_was_refused_is_not_in_the_conversation():
    service = service_with()
    try:
        with pytest.raises(ValueError):
            service.send("x", frequency_hz=1.0)
        assert service.conversation() == []
    finally:
        service.close()


def test_only_the_last_hundred_sent_are_kept():
    service = service_with(max_received=100)
    try:
        for number in range(105):
            service._sent_log.append(
                SentEntry(number, "m", float(number), "sent", 1, 1, 1450.0, 7.0)
            )
        assert len(service.conversation()) == 100
    finally:
        service.close()


def test_what_was_sent_and_what_was_heard_come_in_one_list():
    sender_audio, listener_audio = FakeAudio(devices=DEVICES), FakeAudio(devices=DEVICES)
    sender_audio.connect_to(listener_audio)
    sender, listener = service_with(sender_audio), service_with(listener_audio)
    try:
        listener.start_listening()
        sender.send("ping")
        assert wait_until(lambda: not sender.status()["sending"])
        listener.stop_listening()
        assert [i["kind"] for i in sender.conversation()] == ["sent"]
        (item,) = listener.conversation()
        assert item["kind"] == "received" and item["text"] == "ping"
    finally:
        sender.close()
        listener.close()


def test_the_conversation_is_served_by_the_api():
    service = service_with()
    client = TestClient(create_app(service), base_url="http://127.0.0.1")
    try:
        client.post("/api/send", json={"text": "over the API"})
        assert wait_until(lambda: not client.get("/api/status").json()["sending"])
        body = client.get("/api/conversation").json()
        assert [(i["kind"], i["text"], i["status"]) for i in body["items"]] == [
            ("sent", "over the API", "sent")
        ]
    finally:
        service.close()


def test_a_cancel_that_came_when_all_was_played_cut_nothing_and_the_message_was_sent():
    service = service_with()
    try:
        service._cancel_asked = True
        entry = SentEntry(1, "all of it", 0.0, "sending", 1, 1, 1450.0, airtime_seconds=0.0)
        service._sent_log.append(entry)
        service._sending = True
        service._play(__import__("numpy").zeros(4800), None, entry)
        assert entry.status == "sent"
        entry = SentEntry(2, "cut", 0.0, "sending", 1, 1, 1450.0, airtime_seconds=30.0)
        service._sending = True
        service._play(__import__("numpy").zeros(4800), None, entry)
        assert entry.status == "cancelled"  # it was meant to last 30 s and ended at once
    finally:
        service.close()

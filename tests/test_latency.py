"""How soon what is heard shows: a Message appears shortly after its end, not at the end of the
listening, whatever the Preset, without decoding again and again what was decoded."""

import random
import threading
import time

import numpy as np
import pytest

from vibemodem.app.heard import Tolerance
from vibemodem.app.receiver import Receiver
from vibemodem.core.message import Fragment
from vibemodem.core.transmission import transmit
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import FakeAudio, InputBlocks

FS = 48_000
BLOCK = 24_000  # half a second


def wait_until(condition, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def live(preset, **options):
    """A receiver listening to a stream we feed ourselves, block by block."""
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), **options)
    modem = TurboModem(preset=preset)
    blocks = InputBlocks(capacity=100_000)
    thread = threading.Thread(
        target=receiver._listen,
        args=(blocks, modem, Tolerance.of(preset, modem.frame_samples())),
        daemon=True,
    )
    thread.start()

    def feed(samples):
        for start in range(0, samples.size, BLOCK):
            blocks.push(samples[start : start + BLOCK].astype(np.float32))

    def finish():
        blocks.close()
        thread.join(timeout=120)

    return receiver, feed, finish


@pytest.mark.parametrize("preset", ["fast", "standard"])
def test_a_message_shows_within_a_couple_of_seconds_of_its_end_not_when_listening_stops(preset):
    modem = TurboModem(preset=preset)
    sound = modem.modulate(Fragment(1, 0, 1, b"quick").pack(), preset)
    receiver, feed, finish = live(preset, decode_every_seconds=2.0)
    try:
        feed(np.concatenate([np.zeros(5 * FS), sound, np.zeros(3 * FS)]))  # 3 s after its end
        assert wait_until(lambda: [h.text for h in receiver.received()] == ["quick"])
    finally:
        finish()


def test_the_fragments_of_a_message_show_as_they_arrive_and_the_message_when_whole():
    modem = TurboModem(preset="fast")
    receiver, feed, finish = live("fast", decode_every_seconds=2.0)
    try:
        frames = transmit(modem, b"A" * 17 + b"B" * 17 + b"end", "fast", msg_id=4)  # 3 Frames
        one = modem.frame_samples()
        feed(np.concatenate([np.zeros(2 * FS), frames[:one], np.zeros(3 * FS)]))
        assert wait_until(lambda: receiver.counts == (0, 1))  # one Fragment of three, heard in part
        feed(np.concatenate([frames[one:], np.zeros(3 * FS)]))
        assert wait_until(
            lambda: [h.text for h in receiver.received()] == ["A" * 17 + "B" * 17 + "end"]
        )
    finally:
        finish()


def test_no_pass_decodes_more_than_a_frame_and_a_few_seconds():
    sizes = []

    class Measuring(TurboModem):
        def demodulate_report(self, samples):
            sizes.append(samples.size)
            return super().demodulate_report(samples)

    receiver = Receiver(
        FakeAudio(), lambda preset: Measuring(preset=preset), decode_every_seconds=2.0
    )
    modem = Measuring(preset="fast")
    sound = modem.modulate(Fragment(1, 0, 1, b"middle").pack(), "fast")
    heard = np.concatenate([np.zeros(60 * FS), sound, np.zeros(60 * FS)])  # two minutes and more
    blocks = InputBlocks(capacity=100_000)
    for start in range(0, heard.size, BLOCK):
        blocks.push(heard[start : start + BLOCK].astype(np.float32))
    blocks.close()
    receiver._listen(blocks, modem, Tolerance.of("fast", modem.frame_samples()))
    assert [h.text for h in receiver.received()] == ["middle"]
    assert len(sizes) > 40 and max(sizes) <= modem.frame_samples() + 13 * FS  # not 150 s each time


def test_a_frame_is_never_missed_because_a_pass_cut_it():
    # Frames at any time, passes every 2 s: each is whole in some slice, whatever the offset.
    rng = random.Random(3)
    modem = TurboModem(preset="fast")
    pieces, texts = [], []
    for number in range(8):
        pieces.append(np.zeros(round(rng.uniform(1.0, 9.0) * FS)))
        text = f"m{number}".encode()
        pieces.append(modem.modulate(Fragment(number, 0, 1, text).pack(), "fast"))
        texts.append(text.decode())
    receiver, feed, finish = live("fast", decode_every_seconds=2.0)
    try:
        feed(np.concatenate([*pieces, np.zeros(4 * FS)]))
        assert wait_until(lambda: len(receiver.received()) == 8)
        assert sorted(h.text for h in receiver.received()) == sorted(texts)
    finally:
        finish()


def test_a_frame_of_the_slowest_preset_is_found_in_a_slice_that_holds_it_whole():
    modem = TurboModem(preset="max-range")
    sound = modem.modulate(Fragment(1, 0, 1, b"slow").pack(), "max-range")  # 54 s
    receiver, feed, finish = live("max-range", decode_every_seconds=6.0)
    try:
        feed(np.concatenate([np.zeros(7 * FS), sound, np.zeros(8 * FS)]))
        assert wait_until(lambda: [h.text for h in receiver.received()] == ["slow"], timeout=120)
    finally:
        finish()


# A Signal still arriving ---------------------------------------------------------------------


def test_a_signal_is_shown_as_arriving_once_its_preamble_is_heard_and_gone_when_it_is_read():
    modem = TurboModem(preset="fast")
    sound = modem.modulate(Fragment(1, 0, 1, b"coming").pack(), "fast")  # 6.8 s
    receiver, feed, finish = live("fast", decode_every_seconds=2.0)
    try:
        feed(np.concatenate([np.zeros(3 * FS), sound[: 4 * FS]]))  # 1.28 s of Preamble, 2.7 of data
        feed(sound[4 * FS : 6 * FS])  # more of it, in a later pass: now it is seen twice
        assert wait_until(lambda: len(receiver.arriving()) == 1)
        (coming,) = receiver.arriving()
        assert abs(coming.frequency_hz - 1450.0) < 3
        assert receiver.received() == []  # nothing to read yet
        feed(np.concatenate([sound[6 * FS :], np.zeros(3 * FS)]))
        assert wait_until(lambda: [h.text for h in receiver.received()] == ["coming"])
        assert wait_until(lambda: receiver.arriving() == [])
    finally:
        finish()


def test_what_looks_like_a_preamble_for_one_pass_only_is_not_shown():
    from vibemodem.app.heard import Arriving
    from vibemodem.core.modem import Detection, Report

    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset))
    tolerance = Tolerance(
        seconds=0.08, hertz=25.0, width_hz=200.0, frame_seconds=6.8, preamble_samples=61_440
    )

    def pass_with(*detections, final=False):
        report = Report([], [], arriving=list(detections))
        receiver._note_arriving(report, tolerance, lambda start: start / FS, 0, final)
        return receiver.arriving()

    seen = Detection(96_000, 1450.0, 400.0)
    assert pass_with(seen) == []  # once is a chance
    assert pass_with(seen) == [Arriving(2.0, 1450.0)]  # twice at the same place is a Signal
    assert pass_with(Detection(96_000, 1550.0, 400.0)) == []  # another place: not the same one
    assert pass_with(Detection(96_000, 1550.0, 400.0)) == [Arriving(2.0, 1550.0)]
    assert pass_with(Detection(96_000, 1550.0, 400.0), final=True) == []  # the listening ended


def test_the_conversation_shows_a_signal_that_is_arriving_and_replaces_it_by_the_message():
    from vibemodem.app.service import ModemService

    modem = TurboModem(preset="fast")
    sound = modem.modulate(Fragment(2, 0, 1, b"later").pack(), "fast")
    service = ModemService(FakeAudio(), decode_every_seconds=2.0)
    receiver = service._receiver
    modem2 = TurboModem(preset="fast")
    blocks = InputBlocks(capacity=100_000)
    service.apply_settings(preset="fast")
    thread = threading.Thread(
        target=receiver._listen,
        args=(blocks, modem2, Tolerance.of("fast", modem2.frame_samples())),
        daemon=True,
    )
    thread.start()
    try:
        heard = np.concatenate([np.zeros(3 * FS), sound[: 6 * FS]])
        for start in range(0, heard.size, BLOCK):
            blocks.push(heard[start : start + BLOCK].astype(np.float32))
        assert wait_until(lambda: [i["kind"] for i in service.conversation()] == ["arriving"])
        (item,) = service.conversation()
        assert abs(item["frequency_hz"] - 1450.0) < 3
        rest = np.concatenate([sound[6 * FS :], np.zeros(3 * FS)])
        for start in range(0, rest.size, BLOCK):
            blocks.push(rest[start : start + BLOCK].astype(np.float32))
        assert wait_until(lambda: [i["kind"] for i in service.conversation()] == ["received"])
    finally:
        blocks.close()
        thread.join(timeout=60)
        service.close()

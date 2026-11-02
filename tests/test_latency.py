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

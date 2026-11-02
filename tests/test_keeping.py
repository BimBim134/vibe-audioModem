"""The receiver keeps the audio and the indicators of what it reads and of what it loses."""

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from vibemodem.app.receiver import Receiver
from vibemodem.app.store import ReceptionStore
from vibemodem.core import mfsk
from vibemodem.core.message import Fragment
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import FakeAudio, InputBlocks

FS = 48_000
PRESET = "fast"


def recording(wreck_second=True, snr=None):
    """Silence, two Messages, one Frame whose data is lost, silence."""
    modem = TurboModem(preset=PRESET)
    size = modem.waveform.samples_per_symbol
    first = modem.modulate(Fragment(1, 0, 1, b"first").pack(), PRESET)
    second = modem.modulate(Fragment(2, 0, 1, b"second").pack(), PRESET).copy()
    third = modem.modulate(Fragment(3, 0, 1, b"third").pack(), PRESET)
    if wreck_second:
        start = mfsk.PREAMBLE_SYMBOLS * size
        noise = np.random.default_rng(1).normal(0, 0.3, 100 * size).clip(-1, 1)
        second[start : start + 100 * size] = noise
    quiet = np.zeros(4 * FS)
    heard = np.concatenate([quiet, first, quiet, second, quiet, third, quiet])
    if snr is not None:
        heard = apply_channel(heard, ChannelConfig(snr_db=snr), 5, signal_power=0.125)
    return heard


def listen(receiver, heard, preset=PRESET):
    receiver.set_keeping(True) if receiver.store else None
    heard = np.clip(heard, -1.0, 1.0)  # what a sound card gives: nothing beyond full scale
    blocks = InputBlocks(capacity=100_000)
    for start in range(0, heard.size, 24_000):
        blocks.push(heard[start : start + 24_000].astype(np.float32))
    blocks.close()
    modem = TurboModem(preset=preset)
    from vibemodem.app.receiver import Tolerance

    receiver._listen(blocks, modem, Tolerance.of(preset, modem.frame_samples()))


@pytest.fixture
def made(tmp_path):
    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    return Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store), store


def test_the_frames_read_and_the_signal_lost_are_all_kept(made):
    receiver, store = made
    listen(receiver, recording())
    kept = [saved for _, saved in store.receptions()]
    assert sorted(k["decoded"] for k in kept) == [False, True, True]
    assert sorted(k["msg_id"] for k in kept if k["decoded"]) == [1, 3]


def test_what_is_kept_says_how_it_was_received_and_what_to_replay_it_with(made):
    receiver, store = made
    listen(receiver, recording())
    saved = next(s for _, s in store.receptions() if s["decoded"] and s["msg_id"] == 1)
    assert saved["preset"] == PRESET and saved["modem"] == "vibemodem.core.turbo_modem:TurboModem"
    assert saved["index"] == 0 and saved["total"] == 1
    assert bytes.fromhex(saved["body_hex"]) == Fragment(1, 0, 1, b"first").pack()
    assert saved["snr_db"] is not None and saved["sync_score"] > 7
    assert saved["frequency_hz"] == pytest.approx(1450.0, abs=3)
    assert saved["frame_samples"] == TurboModem(preset=PRESET).frame_samples()
    assert saved["started_at"] > 0


def test_a_lost_signal_is_kept_without_a_message(made):
    receiver, store = made
    listen(receiver, recording())
    (lost,) = [s for _, s in store.receptions() if not s["decoded"]]
    assert lost["frequency_hz"] == pytest.approx(1450.0, abs=3) and "body_hex" not in lost
    assert lost["sync_score"] > 7


def test_each_keeps_its_frame_with_three_seconds_of_sound_around_it(made):
    from vibemodem.io.wav import read_wav

    receiver, store = made
    listen(receiver, recording())
    frame = TurboModem(preset=PRESET).frame_samples()
    for wav, saved in store.receptions():
        audio = read_wav(wav)
        assert audio.size == saved["frame_start_sample"] + frame + 3 * FS  # a margin of 3 s after
        step = TurboModem(preset=PRESET).search_step_samples()
        assert 3 * FS <= saved["frame_start_sample"] < 3 * FS + step  # at least 3 s before


def test_a_frame_that_is_read_again_in_every_pass_is_kept_once(tmp_path):
    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    receiver = Receiver(
        FakeAudio(), lambda preset: TurboModem(preset=preset), decode_every_seconds=2.0, store=store
    )
    listen(receiver, recording())
    assert store.usage()[0] == 3


def test_nothing_is_kept_unless_it_was_asked_for(tmp_path):
    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store)
    heard = recording()
    blocks = InputBlocks(capacity=100_000)
    for start in range(0, heard.size, 24_000):
        blocks.push(heard[start : start + 24_000].astype(np.float32))
    blocks.close()
    modem = TurboModem(preset=PRESET)
    from vibemodem.app.receiver import Tolerance

    receiver._listen(blocks, modem, Tolerance.of(PRESET, modem.frame_samples()))
    assert store.usage() == (0, 0) and len(receiver.received()) == 2  # but it still heard them


def test_a_disk_that_fails_is_reported_and_the_listening_goes_on(tmp_path):
    class FullDisk(ReceptionStore):
        def save(self, audio, indicators):
            raise OSError("no space left on device")

    receiver = Receiver(
        FakeAudio(),
        lambda preset: TurboModem(preset=preset),
        store=FullDisk(tmp_path / "x", max_bytes=1_000_000),
    )
    listen(receiver, recording())
    assert "no space" in receiver.last_error and len(receiver.received()) == 2


# After the reviews: what the first tests did not try -----------------------------


def long_recording(seconds_between=30, count=4, first_tone_hz=1450.0, text=b"x" * 40):
    """Several Transmissions of three Frames, far apart, at a frequency of our choice."""
    modem = TurboModem(preset=PRESET, first_tone_hz=first_tone_hz)
    from vibemodem.core.transmission import transmit

    pieces = [np.zeros(4 * FS)]
    for number in range(count):
        pieces += [transmit(modem, text, PRESET, msg_id=number), np.zeros(seconds_between * FS)]
    return np.concatenate(pieces)


def test_a_message_of_three_frames_at_another_frequency_is_kept_and_replayed(tmp_path):
    from bench.replay import replay_directory

    store = ReceptionStore(tmp_path / "kept", max_bytes=2_000_000_000)
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store)
    listen(receiver, long_recording(count=1, first_tone_hz=1900.0))
    kept = [saved for _, saved in store.receptions()]
    assert sorted(k["index"] for k in kept) == [0, 1, 2] and {k["total"] for k in kept} == {3}
    assert all(abs(k["frequency_hz"] - 1900.0) < 3 for k in kept)
    results = replay_directory(store.directory)
    assert len(results) == 3 and all(r.matches for r in results)
    assert all(abs(r.frequency_hz - 1900.0) < 3 for r in results)


def test_receptions_cut_from_a_window_that_has_slid_are_replayed_as_well(tmp_path):
    from bench.replay import replay_directory

    store = ReceptionStore(tmp_path / "kept", max_bytes=2_000_000_000)
    receiver = Receiver(
        FakeAudio(),
        lambda preset: TurboModem(preset=preset),
        window_seconds=45.0,  # shorter than the recording: the window starts later and later
        decode_every_seconds=10.0,
        store=store,
    )
    listen(receiver, long_recording(seconds_between=25, count=4))
    results = replay_directory(store.directory)
    assert len(results) == 12 and all(r.matches for r in results)  # 4 Messages of 3 Frames


def test_a_frame_at_the_very_end_is_kept_with_what_little_follows_it(tmp_path):
    from bench.replay import replay_directory

    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store)
    modem = TurboModem(preset=PRESET)
    sound = modem.modulate(Fragment(1, 0, 1, b"last").pack(), PRESET)
    listen(receiver, np.concatenate([np.zeros(5 * FS), sound, np.zeros(FS)]))  # 1 s after it
    ((wav, saved),) = store.receptions()
    from vibemodem.io.wav import read_wav

    assert read_wav(wav).size == saved["frame_start_sample"] + sound.size + FS
    assert all(r.matches for r in replay_directory(store.directory))


def test_a_reception_too_big_for_the_store_is_given_up_once_and_the_listening_goes_on(tmp_path):
    class Counting(ReceptionStore):
        tries = 0

        def save(self, audio, indicators):
            Counting.tries += 1
            return super().save(audio, indicators)

    store = Counting(tmp_path / "kept", max_bytes=300_000)  # a Frame with its margins is 1.2 MB
    receiver = Receiver(
        FakeAudio(),
        lambda preset: TurboModem(preset=preset),
        decode_every_seconds=2.0,  # many passes over the same Frames
        store=store,
    )
    listen(receiver, recording())
    assert Counting.tries == 3  # each tried once, not once per pass
    assert "not kept" in receiver.last_error and len(receiver.received()) == 2


def test_a_new_listening_forgets_what_it_kept_so_the_same_time_is_kept_again(tmp_path):
    from vibemodem.app.keeper import Keeper

    keeper = Keeper(ReceptionStore(tmp_path / "kept", max_bytes=1_000_000))
    keeper._kept.append((100.0, 1450.0))
    keeper.start()
    assert not keeper._kept

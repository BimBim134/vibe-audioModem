"""A stored reception is replayed through the bench's decoder and gives what it gave live."""

import json

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from bench.replay import main, replay_directory
from tests.test_keeping import PRESET, listen, recording
from vibemodem.app.receiver import Receiver
from vibemodem.app.store import ReceptionStore
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import FakeAudio

FS = 48_000


def receive_and_keep(tmp_path, heard, preset=PRESET):
    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store)
    listen(receiver, heard, preset)
    return store


def test_every_reception_kept_gives_the_same_result_when_replayed(tmp_path):
    store = receive_and_keep(tmp_path, recording())
    results = replay_directory(store.directory)
    assert len(results) == 3 and all(r.matches for r in results)
    assert sorted(r.decoded for r in results) == [False, True, True]


def test_a_reception_replayed_gives_its_message_its_frequency_and_its_snr(tmp_path):
    store = receive_and_keep(tmp_path, recording(snr=-3.0))
    results = [r for r in replay_directory(store.directory) if r.decoded]
    assert results and all(r.matches for r in results)
    for result in results:
        assert abs(result.snr_db - result.stored_snr_db) <= 1.0
        assert abs(result.frequency_hz - result.stored_frequency_hz) <= 1.0


def test_a_reception_that_no_longer_gives_its_message_is_a_mismatch(tmp_path):
    store = receive_and_keep(tmp_path, recording())
    wav, saved = next((w, s) for w, s in store.receptions() if s["decoded"])
    saved["body_hex"] = "00ff00"  # as if the decoder had read another Message
    wav.with_suffix(".json").write_text(json.dumps(saved))
    results = replay_directory(store.directory)
    assert sum(not r.matches for r in results) == 1


def test_a_lost_signal_must_still_be_lost_when_replayed(tmp_path):
    store = receive_and_keep(tmp_path, recording())
    wav, saved = next((w, s) for w, s in store.receptions() if not s["decoded"])
    clean = TurboModem(preset=PRESET).modulate(b"\x01\x00\x01clean", PRESET)
    from vibemodem.io.wav import write_wav

    write_wav(wav, np.concatenate([np.zeros(3 * FS), clean, np.zeros(3 * FS)]) * 0.9)
    (lost,) = [r for r in replay_directory(store.directory) if r.name == wav.name]
    assert not lost.matches  # it now reads: the decoder changed since


def test_weak_receptions_are_replayed_as_they_were_read_live(tmp_path):
    # The Frames are kept with 3 s of sound around them, not with the 150 s they were heard in:
    # near the threshold the segment must still read.
    modem = TurboModem(preset="standard")
    pieces = [np.zeros(5 * FS)]
    for number in range(8):
        sound = modem.modulate(bytes([number, 0, 1]) + b"weak", "standard")
        pieces += [sound, np.zeros(5 * FS)]
    heard = apply_channel(
        np.concatenate(pieces), ChannelConfig(snr_db=-14.0), 11, signal_power=0.125
    )
    store = receive_and_keep(tmp_path, heard, preset="standard")
    results = replay_directory(store.directory)
    assert len(results) >= 5  # most are read at -14 dB
    assert all(r.matches for r in results if r.decoded)


def test_the_command_prints_a_summary_and_fails_on_a_mismatch(tmp_path, capsys):
    store = receive_and_keep(tmp_path, recording())
    main([str(store.directory)])
    assert "3 of 3 give the same result" in capsys.readouterr().out
    wav, saved = next((w, s) for w, s in store.receptions() if s["decoded"])
    saved["body_hex"] = "00ff00"
    wav.with_suffix(".json").write_text(json.dumps(saved))
    with pytest.raises(SystemExit) as stop:
        main([str(store.directory)])
    assert stop.value.code == 1 and "MISMATCH" in capsys.readouterr().out


def test_a_directory_with_no_receptions_is_said_so(tmp_path, capsys):
    main([str(tmp_path)])
    assert "no receptions" in capsys.readouterr().out

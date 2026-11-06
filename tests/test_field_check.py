"""The field check compares what was sent with what a receiver kept, per Preset."""

import numpy as np

from bench.field_check import check_directory, main, read_sent
from tests.test_keeping import FS, PRESET, listen
from vibemodem.app.receiver import Receiver
from vibemodem.app.store import ReceptionStore
from vibemodem.core import mfsk
from vibemodem.core.transmission import transmit
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import FakeAudio

LONG = "x" * 40  # three Fragments
HALF = "y" * 40


def on_the_air(wreck_middle_of_half=False):
    """A short Message, a long one, one cut short, and a Message nobody listed."""
    modem = TurboModem(preset=PRESET)
    size = modem.waveform.samples_per_symbol
    pieces = [
        transmit(modem, b"short", PRESET, msg_id=1),
        transmit(modem, LONG.encode(), PRESET, msg_id=2),
        transmit(modem, b"stranger", PRESET, msg_id=4),
    ]
    half = transmit(modem, HALF.encode(), PRESET, msg_id=3).copy()
    if wreck_middle_of_half:
        frame = modem.frame_samples()
        noise = np.random.default_rng(1).normal(0, 0.3, 100 * size).clip(-1, 1)
        start = frame + mfsk.PREAMBLE_SYMBOLS * size
        half[start : start + 100 * size] = noise
    pieces.insert(2, half)
    quiet = np.zeros(4 * FS)
    return np.concatenate([quiet] + [p for piece in pieces for p in (piece, quiet)])


def kept(tmp_path, heard):
    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store)
    listen(receiver, heard)
    return store.directory


def sent_file(tmp_path, lines):
    path = tmp_path / "sent.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_sent_file_is_one_message_per_line_without_blank_lines(tmp_path):
    path = sent_file(tmp_path, ["one", "", "dé", "one"])
    assert read_sent(path) == [b"one", "dé".encode(), b"one"]


def test_each_message_sent_is_told_received_or_not_and_what_was_not_listed_is_told(tmp_path):
    directory = kept(tmp_path, on_the_air(wreck_middle_of_half=True))
    sent = [b"short", LONG.encode(), HALF.encode(), b"never on the air"]
    (result,) = check_directory(directory, sent)
    assert result.preset == PRESET
    assert result.received == [b"short", LONG.encode()]
    assert result.missing == [HALF.encode(), b"never on the air"]
    assert result.unexpected == [b"stranger"]
    assert [m.msg_id for m in result.incomplete] == [3]
    assert result.signals_lost >= 1
    assert result.rate == 0.5


def test_a_message_sent_twice_must_be_received_twice(tmp_path):
    directory = kept(tmp_path, on_the_air())
    (result,) = check_directory(directory, [b"short", b"short"])
    assert result.received == [b"short"] and result.missing == [b"short"]


def test_the_audio_can_be_decoded_again_instead_of_trusting_the_kept_figures(tmp_path):
    directory = kept(tmp_path, on_the_air())
    sent = [b"short", LONG.encode(), HALF.encode(), b"stranger"]
    (live,) = check_directory(directory, sent)
    (again,) = check_directory(directory, sent, redecode=True)
    assert again.received == live.received and again.missing == live.missing == []


def test_the_report_shows_the_snr_of_the_frames_read(tmp_path):
    directory = kept(tmp_path, on_the_air())
    (result,) = check_directory(directory, [b"short"])
    assert result.snr_db and min(result.snr_db) > 10


def test_the_command_prints_a_line_per_preset_and_fails_when_a_message_is_missing(tmp_path, capsys):
    directory = kept(tmp_path, on_the_air())
    assert main([str(directory), str(sent_file(tmp_path, ["short", LONG, HALF]))]) is None
    assert PRESET in capsys.readouterr().out
    try:
        main([str(directory), str(sent_file(tmp_path, ["short", "never"]))])
    except SystemExit as stop:
        assert stop.code == 1
    else:
        raise AssertionError("a missing Message must give a failing exit code")


def test_an_empty_directory_is_told_not_crashed_on(tmp_path, capsys):
    (tmp_path / "none").mkdir()
    main([str(tmp_path / "none"), str(sent_file(tmp_path, ["a"]))])
    assert "no receptions" in capsys.readouterr().out

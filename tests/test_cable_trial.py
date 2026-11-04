"""The cable trial: Messages sent at known SNRs through a real chain, counted per SNR."""

import numpy as np
import pytest

from bench.cable_trial import (
    SIMULATED_THRESHOLD_DB,
    default_levels,
    device_argument,
    label,
    main,
    render,
    report,
    run_send,
    trial_messages,
)
from tests.test_keeping import PRESET, listen
from vibemodem.app.receiver import Receiver
from vibemodem.app.store import ReceptionStore
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import FakeAudio

LEVELS = [-30.0, 10.0]


def test_a_message_says_its_snr_and_its_number():
    assert label(-13.0, 7) == "T-13 #07" and label(-12.5, 0) == "T-12.5 #00"


def test_every_level_sends_the_same_number_of_distinct_messages():
    messages = trial_messages([-14.0, -12.0], per_level=3)
    assert len(messages) == 6 and len(set(messages)) == 6


def test_the_default_levels_surround_the_simulated_threshold():
    for preset, threshold in SIMULATED_THRESHOLD_DB.items():
        levels = default_levels(preset)
        assert min(levels) < threshold < max(levels) and levels == sorted(levels)


def test_the_sound_is_scaled_to_fit_the_card_and_is_the_snr_asked_for_to_the_decoder():
    modem = TurboModem(preset=PRESET)
    sound = render(modem, PRESET, "T10 #00", snr_db=10.0, seed=1)
    assert np.abs(sound).max() <= 0.95
    assert [r.message[3:] for r in modem.demodulate_report(sound).receptions] == [b"T10 #00"]


def test_each_message_is_played_once_and_a_problem_stops_nothing_silently():
    audio = FakeAudio()
    run_send(audio, output=None, preset=PRESET, levels=[10.0], per_level=3, gap_seconds=0)
    assert len(audio.played) == 3


@pytest.fixture
def kept(tmp_path):
    store = ReceptionStore(tmp_path / "kept", max_bytes=500_000_000)
    receiver = Receiver(FakeAudio(), lambda preset: TurboModem(preset=preset), store=store)
    audio = FakeAudio()
    run_send(audio, output=None, preset=PRESET, levels=LEVELS, per_level=3, gap_seconds=0)
    quiet = np.zeros(48_000 * 4, dtype=np.float32)
    heard = np.concatenate([np.concatenate([quiet, sound]) for sound in audio.played] + [quiet])
    listen(receiver, heard)
    return store.directory


def test_the_report_counts_what_was_received_at_each_snr(kept):
    rows = report(kept, PRESET, LEVELS, per_level=3)
    assert [(r.snr_db, r.received, r.sent) for r in rows] == [(-30.0, 0, 3), (10.0, 3, 3)]


def test_the_command_prints_a_row_per_level_and_the_gap_to_the_simulator(kept, capsys):
    main(["report", str(kept), "--preset", PRESET, "--snr=-30,10", "--per-level", "3"])
    out = capsys.readouterr().out
    assert "10" in out and "3 of 3" in out and "0 of 3" in out and "simulator" in out


def test_the_send_command_refuses_a_level_list_that_is_not_numbers(capsys):
    with pytest.raises(SystemExit):
        main(["report", ".", "--preset", PRESET, "--snr", "loud"])


def test_a_device_given_as_digits_is_a_number_and_anything_else_is_a_name():
    assert device_argument("10") == 10 and device_argument("Scarlett") == "Scarlett"
    assert device_argument(None) is None

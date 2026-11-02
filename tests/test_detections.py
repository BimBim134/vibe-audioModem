"""A Signal the receiver found but could not decode is reported, not silently dropped."""

import numpy as np
import pytest

from vibemodem.core import mfsk
from vibemodem.core.baseline import BaselineModem
from vibemodem.core.modem import Detection
from vibemodem.core.turbo_modem import TurboModem

FS = mfsk.SAMPLE_RATE
PRESET = "fast"


@pytest.fixture(scope="module")
def modem():
    return TurboModem(preset=PRESET)


def frame(modem, text=b"a message"):
    return modem.modulate(text, PRESET)


def wreck_data(modem, sound, first, last):
    """Noise instead of the data of a Frame, its Preamble left as it was."""
    damaged = sound.copy()
    size = modem.waveform.samples_per_symbol
    start = (mfsk.PREAMBLE_SYMBOLS + first) * size
    stop = (mfsk.PREAMBLE_SYMBOLS + last) * size
    damaged[start:stop] = np.random.default_rng(5).normal(0, 0.5, stop - start)
    return damaged


def test_a_clean_frame_is_received_and_nothing_is_reported_missing(modem):
    report = modem.demodulate_report(frame(modem))
    assert [r.message for r in report.receptions] == [b"a message"]
    assert report.undecoded == []


def test_demodulate_is_the_receptions_of_the_report(modem):
    sound = frame(modem)
    assert modem.demodulate(sound) == modem.demodulate_report(sound).receptions


def test_a_frame_whose_data_was_lost_is_reported_where_and_how_sure_it_was_seen(modem):
    report = modem.demodulate_report(wreck_data(modem, frame(modem), 0, 100))
    assert report.receptions == []
    (found,) = report.undecoded
    assert isinstance(found, Detection)
    assert found.start_sample == 0 and found.frequency_hz == pytest.approx(1450.0, abs=3)
    assert found.sync_score > 7


def test_only_the_frame_that_was_damaged_is_reported_in_a_train_of_frames(modem):
    first, third = frame(modem, b"first"), frame(modem, b"third")
    second = wreck_data(modem, frame(modem, b"second"), 0, 100)
    report = modem.demodulate_report(np.concatenate([first, second, third]))
    assert sorted(r.message for r in report.receptions) == [b"first", b"third"]
    (found,) = report.undecoded  # and not the side peaks of the Preambles that were read
    assert found.start_sample == first.size


def test_the_side_peaks_of_a_preamble_are_not_lost_signals(modem):
    report = modem.demodulate_report(np.concatenate([frame(modem, b"a"), frame(modem, b"b")]))
    assert len(report.receptions) == 2 and report.undecoded == []


def test_a_frame_that_is_still_arriving_is_not_reported_as_lost(modem):
    sound = frame(modem)
    assert modem.demodulate_report(sound[: sound.size - 3 * FS]).undecoded == []
    assert modem.demodulate_report(sound[: sound.size // 2]).undecoded == []


def test_noise_alone_reports_nothing(modem):
    for seed in range(5):
        noise = np.random.default_rng(seed).normal(0, 0.1, 30 * FS)
        report = modem.demodulate_report(noise)
        assert report.receptions == [] and report.undecoded == []


def test_every_modem_of_the_family_reports_the_same_way():
    modem = BaselineModem(preset=PRESET)
    damaged = wreck_data(modem, modem.modulate(b"x", PRESET), 0, 100)
    assert len(modem.demodulate_report(damaged).undecoded) == 1


def test_a_weak_match_is_not_reported_but_a_clear_one_is(modem):
    from vibemodem.core.coded_modem import UNDECODED_MIN_SCORE

    quiet = np.zeros(20 * FS)
    for score, reported in [(7.5, 0), (UNDECODED_MIN_SCORE - 0.1, 0), (UNDECODED_MIN_SCORE, 1)]:
        shaky = TurboModem(preset=PRESET)
        shaky._find = lambda samples, s=score: [mfsk.Candidate(1000, 1450.0, s)]
        shaky._decode = lambda samples, signal: None
        assert len(shaky.demodulate_report(quiet).undecoded) == reported


def test_the_side_peaks_of_a_frame_that_is_not_whole_yet_are_not_lost_signals(modem):
    # A Frame still arriving, cut by the end of what is heard, has side peaks of its Preamble a few
    # symbols earlier, that do fit: they must not be reported as Signals that could not be read.
    sound = np.concatenate([np.zeros(2 * FS), frame(modem), np.zeros(FS)])
    end = 2 * FS + frame(modem).size
    for short in range(5, 400, 23):  # the sound ends this many hundredths of a second too soon
        report = modem.demodulate_report(sound[: end - short * FS // 100])
        assert report.receptions == [] and report.undecoded == [], short


def test_a_second_frame_that_follows_the_first_at_once_is_still_found_when_lost(modem):
    first, second = frame(modem, b"one"), wreck_data(modem, frame(modem, b"two"), 0, 100)
    report = modem.demodulate_report(np.concatenate([first, second]))
    assert [r.message for r in report.receptions] == [b"one"]
    assert [d.start_sample for d in report.undecoded] == [first.size]

"""The bench's measurement of the Success threshold."""

import numpy as np
import pytest
from scipy.special import erfc

from bench.threshold import CurvePoint, measure_curve, success_threshold
from bench.toy import BIT_RATE, ToyModem
from tests.fake_modems import (
    DeafModem,
    NoisyModem,
    PerfectModem,
    RecordingModem,
    ToneModem,
    WrongModem,
)


def curve(*points):
    """(snr_db, successes) pairs out of 100 trials."""
    return [CurvePoint(snr_db=snr, trials=100, successes=ok) for snr, ok in points]


def test_the_threshold_is_the_lowest_snr_that_reaches_95_percent():
    points = curve((-10, 0), (-8, 50), (-6, 94), (-4, 95), (-2, 100))
    assert success_threshold(points) == -4


def test_a_lucky_low_snr_does_not_count_when_a_higher_snr_fails():
    points = curve((-6, 100), (-4, 90), (-2, 100))
    assert success_threshold(points) == -2


def test_there_is_no_threshold_when_no_snr_reaches_95_percent():
    assert success_threshold(curve((-6, 10), (-2, 94))) is None


def test_the_threshold_is_the_lowest_tested_snr_when_every_point_passes():
    assert success_threshold(curve((0, 100), (-10, 99), (-5, 100))) == -10


@pytest.mark.parametrize(
    "modem_class, expected_successes, expected_false_receptions",
    [(PerfectModem, 20, 0), (DeafModem, 0, 0), (WrongModem, 0, 20), (NoisyModem, 0, 20)],
)
def test_a_trial_succeeds_only_when_exactly_the_sent_message_comes_back(
    modem_class, expected_successes, expected_false_receptions
):
    points = measure_curve(
        modem_class(),
        preset="standard",
        snr_db_values=[-5.0, 0.0],
        trials=20,
        seed=1,
        message_bytes=4,
    )
    assert [(p.snr_db, p.trials, p.successes, p.false_receptions) for p in points] == [
        (-5.0, 20, expected_successes, expected_false_receptions),
        (0.0, 20, expected_successes, expected_false_receptions),
    ]


def measure(**overrides):
    arguments = (
        dict(preset="standard", snr_db_values=[0.0], trials=5, seed=1, message_bytes=2) | overrides
    )
    return measure_curve(PerfectModem(), **arguments)


@pytest.mark.parametrize("bad", [{"trials": 0}, {"trials": -3}, {"message_bytes": 0}])
def test_a_measurement_that_cannot_mean_anything_is_rejected(bad):
    with pytest.raises(ValueError):
        measure(**bad)


@pytest.mark.parametrize(
    "bad",
    [{"trials": 0, "successes": 0}, {"trials": 5, "successes": 6}, {"trials": 5, "successes": -1}],
)
def test_a_curve_point_must_have_trials_and_a_possible_success_count(bad):
    with pytest.raises(ValueError):
        CurvePoint(snr_db=0.0, **bad)


def run_toy(seed, snr_db_values=(-9.0, -7.0), trials=30, message_bytes=2):
    return measure_curve(
        ToyModem(),
        preset="standard",
        snr_db_values=list(snr_db_values),
        trials=trials,
        seed=seed,
        message_bytes=message_bytes,
    )


def what_the_modem_sees(seed):
    modem = RecordingModem()
    measure_curve(
        modem,
        preset="standard",
        snr_db_values=[-3.0],
        trials=4,
        seed=seed,
        message_bytes=3,
    )
    return modem


def test_the_seed_decides_which_messages_are_sent_and_which_noise_is_added():
    first, again, other = what_the_modem_sees(4), what_the_modem_sees(4), what_the_modem_sees(5)

    assert first.messages == again.messages
    for heard, heard_again in zip(first.heard, again.heard, strict=True):
        np.testing.assert_array_equal(heard, heard_again)

    assert first.messages != other.messages
    assert not np.array_equal(first.heard[0], other.heard[0])


def test_the_toy_modem_gives_the_same_curve_for_the_same_seed():
    assert run_toy(seed=4) == run_toy(seed=4)


def theoretical_success_rate(snr_db, message_bytes):
    """Chance that every bit of a coherent-BPSK Message is right on white noise.

    The SNR is in a 2,500 Hz reference bandwidth; Eb/N0 = SNR * 2,500 / bit rate.
    """
    eb_over_n0 = 10 ** (snr_db / 10) * 2500 / BIT_RATE
    bit_error_rate = 0.5 * erfc(np.sqrt(eb_over_n0))  # Q(sqrt(2 Eb/N0))
    return (1 - bit_error_rate) ** (8 * message_bytes)


# With 1,500 trials the standard error of a measured rate is at most 0.013, so a gap of 0.05
# is almost four standard errors, and a correct bench stays inside it. A 1 dB error in the noise
# scaling moves the curve by 0.10 to 0.14 at -9 and -11 dB, which falls outside it; at -7 and
# -5 dB the curve is nearly flat, so those two points only check the high end.
THEORY_TOLERANCE = 0.05


@pytest.mark.parametrize("snr_db", [-11.0, -9.0, -7.0, -5.0])
def test_the_toy_modem_follows_the_textbook_curve_on_white_noise(snr_db):
    (point,) = run_toy(seed=11, snr_db_values=[snr_db], trials=1500)
    expected = theoretical_success_rate(snr_db, message_bytes=2)
    assert point.success_rate == pytest.approx(expected, abs=THEORY_TOLERANCE)


def hear(modem_class, **overrides):
    modem = modem_class()
    arguments = (
        dict(preset="standard", snr_db_values=[60.0], trials=6, seed=2, message_bytes=2) | overrides
    )
    measure_curve(modem, **arguments)
    return modem.heard


def first_loud_sample(audio):
    return int(np.argmax(np.abs(audio) > 0.25))


def test_each_trial_hides_the_transmission_at_a_random_moment_in_a_longer_recording():
    heard = hear(RecordingModem, max_lead_in_s=2.0, tail_s=1.0)
    assert {len(audio) for audio in heard} == {480 + 3 * 48_000}  # same length every time
    starts = [first_loud_sample(audio) for audio in heard]
    assert all(0 <= start <= 2 * 48_000 for start in starts)
    assert len(set(starts)) > 1
    again = [first_loud_sample(a) for a in hear(RecordingModem, max_lead_in_s=2.0, tail_s=1.0)]
    assert again == starts  # the seed fixes the moments too


def test_noise_is_set_against_the_transmission_not_against_the_silence_around_it():
    # 480 samples of 0.5 is 0.25 W; at 0 dB in 2,500 Hz the noise std is sqrt(0.25 * 9.6).
    (audio, *_) = hear(RecordingModem, snr_db_values=[0.0], max_lead_in_s=5.0, tail_s=0.0)
    assert np.std(audio[: 4 * 48_000]) == pytest.approx(np.sqrt(0.25 * 9.6), rel=0.05)


def test_each_trial_shifts_the_whole_signal_by_a_random_frequency_in_the_range():
    heard = hear(ToneModem, freq_offset_range_hz=(100.0, 200.0))
    peaks = []
    for audio in heard:
        spectrum = np.abs(np.fft.rfft(audio))
        peaks.append(np.argmax(spectrum) * 48_000 / audio.size)
    assert all(1100 <= peak <= 1200 for peak in peaks)
    assert len({round(peak) for peak in peaks}) > 1


def test_without_padding_or_offset_the_audio_is_what_the_modem_produced():
    heard = hear(RecordingModem)
    assert {len(audio) for audio in heard} == {480}

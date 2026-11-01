"""How often a code loses a frame on white noise, from its Eb/N0."""

import json

import pytest
from scipy.special import erfc

from bench.code_curves import frame_error_rate, main
from tests.fake_modems import UncodedBits
from vibemodem.core.convolutional import ConvolutionalCode
from vibemodem.core.ldpc import LdpcCode
from vibemodem.core.turbo import TurboCode


@pytest.mark.parametrize("ebn0_db", [2.0, 4.0, 6.0])
def test_the_scale_of_ebn0_follows_the_textbook_curve_for_a_single_uncoded_bit(ebn0_db):
    # A frame of one uncoded bit is lost exactly when that bit is: Q(sqrt(2 Eb/N0)).
    expected = 0.5 * erfc((10 ** (ebn0_db / 10)) ** 0.5)
    measured = frame_error_rate(UncodedBits(1), ebn0_db, frames=40_000, seed=1)
    assert measured == pytest.approx(expected, abs=0.004)


@pytest.mark.parametrize(
    "code", [ConvolutionalCode(200), LdpcCode(), TurboCode(200)], ids=["conv", "ldpc", "turbo"]
)
def test_a_real_code_loses_nearly_every_frame_in_heavy_noise_and_none_in_light_noise(code):
    assert frame_error_rate(code, -6.0, frames=20, seed=1) >= 0.9
    assert frame_error_rate(code, 12.0, frames=20, seed=1) == 0.0


def test_the_same_seed_gives_the_same_rate():
    first = frame_error_rate(ConvolutionalCode(200), 1.0, frames=30, seed=5)
    assert frame_error_rate(ConvolutionalCode(200), 1.0, frames=30, seed=5) == first


def test_the_command_prints_the_rates_and_saves_them_with_the_code_described(tmp_path, capsys):
    out = tmp_path / "curve.json"
    main(
        [
            "--code", "tests.fake_modems:UncodedBits", "--info-bits", "8", "--ebn0-from", "0",
            "--ebn0-to", "4", "--ebn0-step", "2", "--frames", "50", "--out", str(out),
        ]
    )  # fmt: skip
    assert "Eb/N0" in capsys.readouterr().out
    saved = json.loads(out.read_text())
    assert saved["code"] == {"info_bits": 8, "coded_bits": 8, "kind": "uncoded"}
    assert [p["ebn0_db"] for p in saved["curve"]] == [0, 2, 4]
    assert all(p["frames"] == 50 and 0 <= p["errors"] <= 50 for p in saved["curve"])


@pytest.mark.parametrize(
    "bad",
    [
        ["--frames", "0"],
        ["--ebn0-step", "0"],
        ["--ebn0-from", "5", "--ebn0-to", "1"],
        ["--code", "no_such_module:X"],
        ["--code", "tests.fake_modems:NoSuchCode"],
    ],
)
def test_arguments_that_cannot_be_simulated_are_refused(tmp_path, bad):
    arguments = ["--code", "tests.fake_modems:UncodedBits", "--out", str(tmp_path / "x.json")]
    with pytest.raises(SystemExit) as stop:
        main([*arguments, *bad])
    assert stop.value.code == 2
    assert not (tmp_path / "x.json").exists()


def test_settings_given_on_the_command_line_reach_the_code_and_are_recorded(tmp_path):
    out = tmp_path / "set.json"
    main(
        [
            "--code", "vibemodem.core.ldpc:LdpcCode", "--set", "max_iterations=7",
            "--set", "normalisation=0.9", "--ebn0-from", "10", "--ebn0-to", "10",
            "--frames", "3", "--out", str(out),
        ]
    )  # fmt: skip
    code = json.loads(out.read_text())["code"]
    assert (code["max_iterations"], code["normalisation"]) == (7, 0.9)


@pytest.mark.parametrize("bad", ["no-equals-sign", "max_iterations=not json", "unknown_setting=1"])
def test_a_setting_that_cannot_be_applied_is_refused(tmp_path, bad):
    arguments = ["--code", "vibemodem.core.ldpc:LdpcCode", "--out", str(tmp_path / "x.json")]
    with pytest.raises(SystemExit) as stop:
        main([*arguments, "--set", bad])
    assert stop.value.code == 2


def test_frames_lost_are_split_between_no_answer_and_a_wrong_answer(tmp_path):
    out = tmp_path / "split.json"
    # LDPC says nothing when no codeword satisfies its rules; the convolutional code always answers.
    for code, expect_silence in (
        ("vibemodem.core.ldpc:LdpcCode", True),
        ("vibemodem.core.convolutional:ConvolutionalCode", False),
    ):
        main(
            [
                "--code",
                code,
                "--ebn0-from",
                "-6",
                "--ebn0-to",
                "-6",
                "--frames",
                "20",
                "--out",
                str(out),
            ]
        )
        point = json.loads(out.read_text())["curve"][0]
        assert point["errors"] >= 18
        assert (point["no_answer"] > 0) is expect_silence
        assert point["no_answer"] <= point["errors"]

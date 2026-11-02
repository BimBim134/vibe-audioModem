"""WAV files: 16-bit mono written, many formats read, only 48 kHz accepted."""

import numpy as np
import pytest
from scipy.io import wavfile

from vibemodem.io.wav import WavError, read_wav, write_wav

FS = 48_000


def tone(seconds=0.5, level=0.5):
    return level * np.sin(2 * np.pi * 1000 * np.arange(round(seconds * FS)) / FS)


def test_written_audio_reads_back_within_one_16_bit_step(tmp_path):
    samples = tone()
    write_wav(tmp_path / "a.wav", samples)
    back = read_wav(tmp_path / "a.wav")
    assert back.shape == samples.shape and back.dtype == np.float32
    assert np.max(np.abs(back - samples)) <= 1 / 32768


def test_a_file_is_16_bit_mono_at_48_khz(tmp_path):
    write_wav(tmp_path / "a.wav", tone())
    rate, data = wavfile.read(tmp_path / "a.wav")
    assert rate == FS and data.dtype == np.int16 and data.ndim == 1


def test_audio_that_would_clip_is_refused_not_wrapped(tmp_path):
    with pytest.raises(ValueError, match="full scale"):
        write_wav(tmp_path / "a.wav", np.array([0.0, 1.5]))
    assert not (tmp_path / "a.wav").exists()


@pytest.mark.parametrize("bad", [np.zeros((4, 2)), np.array([np.nan])])
def test_audio_that_is_not_one_channel_of_numbers_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        write_wav(tmp_path / "a.wav", bad)


@pytest.mark.parametrize(
    "dtype, scale",
    [(np.int16, 32767), (np.int32, 2**31 - 1), (np.float32, 1.0), (np.float64, 1.0)],
)
def test_the_usual_sample_formats_are_read_as_numbers_between_minus_one_and_one(
    tmp_path, dtype, scale
):
    samples = tone()
    data = (samples * scale).astype(dtype)
    wavfile.write(tmp_path / "f.wav", FS, data)
    assert np.max(np.abs(read_wav(tmp_path / "f.wav") - samples)) < 1e-3


def test_8_bit_files_are_read_too(tmp_path):
    samples = tone()
    wavfile.write(tmp_path / "u8.wav", FS, (samples * 127 + 128).astype(np.uint8))
    assert np.max(np.abs(read_wav(tmp_path / "u8.wav") - samples)) < 2e-2


def test_a_stereo_file_is_averaged_to_one_channel(tmp_path):
    left, right = tone(level=0.5), tone(level=0.1)
    wavfile.write(tmp_path / "s.wav", FS, np.stack([left, right], axis=1).astype(np.float32))
    assert np.max(np.abs(read_wav(tmp_path / "s.wav") - (left + right) / 2)) < 1e-6


def test_a_file_at_another_sample_rate_is_refused_with_its_rate(tmp_path):
    wavfile.write(tmp_path / "cd.wav", 44_100, tone().astype(np.float32))
    with pytest.raises(WavError, match="44100 Hz.*48000 Hz"):
        read_wav(tmp_path / "cd.wav")


def test_a_file_that_is_not_a_wav_is_refused(tmp_path):
    (tmp_path / "x.wav").write_bytes(b"this is not audio at all")
    with pytest.raises(WavError, match="not a readable WAV"):
        read_wav(tmp_path / "x.wav")


def test_a_file_that_does_not_exist_is_reported_as_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_wav(tmp_path / "missing.wav")


def test_a_24_bit_file_is_read_at_the_right_scale(tmp_path):
    import wave

    samples = tone()
    ints = np.round(samples * (2**23 - 1)).astype("<i4")
    packed = np.frombuffer(ints.tobytes(), dtype=np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(str(tmp_path / "24.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(3)
        out.setframerate(FS)
        out.writeframes(packed)
    assert np.max(np.abs(read_wav(tmp_path / "24.wav") - samples)) < 1e-4


def test_an_empty_wav_reads_as_no_samples(tmp_path):
    wavfile.write(tmp_path / "e.wav", FS, np.zeros(0, dtype=np.int16))
    assert read_wav(tmp_path / "e.wav").size == 0


def test_a_file_that_cannot_be_opened_is_not_called_a_bad_wav(tmp_path):
    with pytest.raises(OSError) as problem:
        read_wav(tmp_path)  # a directory
    assert not isinstance(problem.value, WavError)

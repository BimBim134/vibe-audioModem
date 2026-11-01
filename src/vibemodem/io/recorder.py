"""Spike-grade audio input: list input devices and record a few seconds.

The packaging spike (issue #3) only needs to prove that an audio library can be bundled
and can capture sound. The real audio layer is a later ticket.
"""

import numpy as np


class NoInputDeviceError(RuntimeError):
    """Raised when no audio input device can be used."""


def _sounddevice():
    try:
        import sounddevice
    except OSError as exc:  # the PortAudio library is missing
        raise NoInputDeviceError(f"audio library unavailable: {exc}") from exc
    return sounddevice


def list_input_devices() -> list[dict]:
    sd = _sounddevice()
    try:
        devices = sd.query_devices()
    except sd.PortAudioError as exc:
        raise NoInputDeviceError(str(exc)) from exc
    return [
        {"index": index, "name": d["name"], "max_input_channels": d["max_input_channels"]}
        for index, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


def record(seconds: float, device: int | None = None, sample_rate: int = 48_000) -> np.ndarray:
    """Record mono audio from an input device; returns float32 samples in [-1, 1]."""
    sd = _sounddevice()
    try:
        data = sd.rec(
            int(seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device,
        )
        sd.wait()
    except sd.PortAudioError as exc:
        raise NoInputDeviceError(str(exc)) from exc
    return data[:, 0]

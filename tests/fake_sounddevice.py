"""A stand-in for the `sounddevice` module, so the sound card layer is tried without a card."""

import numpy as np


class PortAudioError(Exception):
    pass


class FakeSounddevice:
    PortAudioError = PortAudioError

    def __init__(self, devices, rates=(48_000,), recording=None):
        self._devices = devices
        self._rates = rates
        self._recording = recording
        self.played = []
        self.recordings = []
        self.streams = []
        self.stopped = 0
        self.fail_to_start = False
        self.fail_to_stop = False

    def query_devices(self):
        return self._devices

    def _check(self, device, direction, samplerate):
        channels = self._devices[device if device is not None else 0][f"max_{direction}_channels"]
        if channels < 1:
            raise PortAudioError(f"device {device} has no {direction} channel")
        if samplerate not in self._rates:
            raise PortAudioError(f"Invalid sample rate {samplerate}")

    def check_input_settings(self, device=None, channels=None, samplerate=None, **_):
        self._check(device, "input", samplerate)

    def check_output_settings(self, device=None, channels=None, samplerate=None, **_):
        self._check(device, "output", samplerate)

    def rec(self, frames, samplerate, channels, dtype, device):
        self.recordings.append({"frames": frames, "device": device, "channels": channels})
        if self._recording is None:
            return np.zeros((frames, channels), dtype=dtype)
        return self._recording[:frames].astype(dtype).reshape(-1, channels)

    def play(self, data, samplerate, device):
        self.played.append({"data": np.asarray(data), "device": device, "rate": samplerate})

    def wait(self):
        pass

    def stop(self):
        self.stopped += 1

    def InputStream(self, **options):  # noqa: N802 (it stands for a class)
        stream = FakeInputStream(owner=self, **options)
        self.streams.append(stream)
        return stream


class FakeInputStream:
    def __init__(self, owner, samplerate, blocksize, channels, dtype, device, callback):
        self.owner = owner
        self.blocksize, self.device, self.callback = blocksize, device, callback
        self.running = self.closed = False

    def start(self):
        if self.owner.fail_to_start:
            raise PortAudioError("cannot start")
        self.running = True

    def stop(self):
        self.running = False
        if self.owner.fail_to_stop:
            raise PortAudioError("cannot stop")

    def close(self):
        self.closed = True

    def hear(self, block, overflow=False):
        """What the sound card does: hand a block to the callback."""
        status = type("Status", (), {"input_overflow": overflow, "__bool__": lambda s: overflow})()
        self.callback(np.asarray(block, dtype=np.float32).reshape(-1, 1), len(block), None, status)

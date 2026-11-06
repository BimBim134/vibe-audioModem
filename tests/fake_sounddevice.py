"""A stand-in for the `sounddevice` module, so the sound card layer is tried without a card."""

import threading
import time

import numpy as np


class PortAudioError(Exception):
    pass


class CallbackStop(Exception):
    pass


class CallbackAbort(Exception):
    pass


class FakeSounddevice:
    PortAudioError = PortAudioError
    CallbackStop = CallbackStop
    CallbackAbort = CallbackAbort

    def __init__(self, devices, rates=(48_000,), recording=None):
        self._devices = devices
        self._rates = rates
        self._recording = recording
        self.played = []
        self.recordings = []
        self.streams = []
        self.output_streams = []
        self.seconds_per_second = 0.0  # how long playing 1 s of sound takes
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

    def wait(self):
        pass

    def OutputStream(self, **options):  # noqa: N802 (it stands for a class)
        stream = FakeOutputStream(owner=self, **options)
        self.output_streams.append(stream)
        return stream

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


class FakeOutputStream:
    """A stream that asks for its sound through a callback, in real time, as a sound card does."""

    PIECE = 4800  # frames asked for at a time

    def __init__(self, owner, samplerate, channels, dtype, device, callback, finished_callback):
        self.owner, self.device, self.rate = owner, device, samplerate
        self.callback, self.finished_callback = callback, finished_callback
        self.heard_pieces = []
        self.closed = self.aborted = self.stopped = False
        self.fail_to_start = False
        self._thread = None

    def start(self):
        if self.fail_to_start:
            raise PortAudioError("cannot start")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            outdata = np.zeros((self.PIECE, 1), dtype=np.float32)
            try:
                self.callback(outdata, self.PIECE, None, None)
            except CallbackAbort:
                self.aborted = True
                break
            except CallbackStop:
                self.heard_pieces.append(outdata[:, 0].copy())
                self.stopped = True
                break
            self.heard_pieces.append(outdata[:, 0].copy())
            time.sleep(self.PIECE / self.rate * self.owner.seconds_per_second)
        self.finished_callback()

    def close(self):
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.closed = True
        self.owner.played.append(
            {
                "data": self.heard(),
                "device": self.device,
                "rate": self.rate,
                "aborted": self.aborted,
            }
        )

    def heard(self):
        if not self.heard_pieces:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.heard_pieces)

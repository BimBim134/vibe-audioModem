"""Sound cards: list, play, record and listen at the modem's sample rate, mono. No DSP.

`SoundCard` works with the `sounddevice` library (PortAudio); `FakeAudio` stands in for it in
tests and can loop what is played back into the input. Both follow the `Audio` protocol, so
the rest of the system never knows which one it has.
"""

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.io._samples import checked_samples


class AudioError(RuntimeError):
    """Something went wrong with the audio hardware or its library."""


class AudioLibraryUnavailableError(AudioError):
    """The audio library (PortAudio) itself cannot be loaded."""


class NoAudioDeviceError(AudioError):
    """No audio device fits what was asked, or none can be opened."""


class UnsupportedAudioError(AudioError):
    """The device cannot work at the modem's sample rate, in mono."""


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    inputs: int  # number of input channels
    outputs: int
    rate_hz: float  # the device's own default sample rate


def find_device(devices: list[DeviceInfo], wanted: int | str | None, direction: str) -> int | None:
    """The number of the device asked for, by number or by part of its name (None: default)."""
    if wanted is None:
        return None
    usable = [d for d in devices if (d.inputs if direction == "input" else d.outputs) > 0]
    if isinstance(wanted, bool) or not isinstance(wanted, int | str) or wanted == "":
        raise NoAudioDeviceError(f"{wanted!r} is neither a device number nor part of a name")
    if isinstance(wanted, int):
        if any(d.index == wanted for d in usable):
            return wanted
        raise NoAudioDeviceError(f"no {direction} device has the number {wanted}")
    exact = [d for d in usable if wanted.lower() == d.name.lower()]
    matches = exact or [d for d in usable if wanted.lower() in d.name.lower()]
    if not matches:
        raise NoAudioDeviceError(f"no {direction} device whose name contains {wanted!r}")
    if len(matches) > 1:
        names = ", ".join(f"{d.index}: {d.name}" for d in matches)
        raise NoAudioDeviceError(f"several {direction} devices contain {wanted!r} ({names})")
    return matches[0].index


class InputBlocks:
    """Blocks of sound heard from an input, one after the other, until it is closed.

    Iterate over it to get them (mono float32, waiting for the next one). Its queue is bounded:
    when whoever iterates is too slow, the oldest block is dropped and `dropped` counts it.
    """

    def __init__(self, capacity: int = 64, on_close: Callable[[], None] | None = None):
        self._blocks: deque[np.ndarray] = deque()
        self._capacity = capacity
        self._on_close = on_close
        self._closed = False
        self._lock = threading.Condition()
        self.dropped = 0

    def push(self, block: np.ndarray) -> None:
        with self._lock:
            if self._closed:
                return
            if len(self._blocks) >= self._capacity:
                self._blocks.popleft()
                self.dropped += 1
            self._blocks.append(block)
            self._lock.notify()

    def note_lost(self) -> None:
        """Count audio the sound card itself lost before it reached us."""
        with self._lock:
            self.dropped += 1

    def close(self) -> None:
        with self._lock:
            already, self._closed = self._closed, True
            self._lock.notify_all()
        if not already and self._on_close:
            self._on_close()

    def __enter__(self) -> "InputBlocks":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def __iter__(self):
        while True:
            with self._lock:
                while not self._blocks and not self._closed:
                    self._lock.wait()
                if not self._blocks:
                    return
                block = self._blocks.popleft()
            yield block


class Audio(Protocol):
    """What the rest of the system needs from the sound hardware."""

    def list_devices(self) -> list[DeviceInfo]: ...

    def play(self, samples: np.ndarray, device: int | str | None = None) -> None:
        """Play samples between -1 and 1 and return when they have been played."""
        ...

    def record(self, seconds: float, device: int | str | None = None) -> np.ndarray:
        """Mono float32 samples recorded for `seconds`."""
        ...

    def listen(
        self, device: int | str | None = None, block_seconds: float = 0.5, capacity: int = 64
    ) -> InputBlocks:
        """Start hearing the input; close the result (or leave its `with`) to stop."""
        ...


def _playable(samples: np.ndarray) -> np.ndarray:
    return checked_samples(samples).astype(np.float32)


def _positive(value: float, what: str) -> None:
    if not value > 0:
        raise ValueError(f"{what} lasts a positive number of seconds")


def _import_sounddevice():
    import sounddevice

    return sounddevice


class SoundCard:
    """The computer's sound card, through the `sounddevice` library."""

    def __init__(self, load: Callable = _import_sounddevice):
        self._load = load
        self._module = None

    def _sd(self):
        if self._module is None:
            try:
                self._module = self._load()
            except (OSError, ImportError) as error:  # PortAudio or the library is missing
                raise AudioLibraryUnavailableError(str(error)) from error
        return self._module

    def list_devices(self) -> list[DeviceInfo]:
        sd = self._sd()
        try:
            found = sd.query_devices()
        except sd.PortAudioError as error:
            raise NoAudioDeviceError(str(error)) from error
        return [
            DeviceInfo(
                index=index,
                name=d["name"],
                inputs=d["max_input_channels"],
                outputs=d["max_output_channels"],
                rate_hz=float(d["default_samplerate"]),
            )
            for index, d in enumerate(found)
        ]

    def _open_check(self, direction: str, device: int | str | None) -> int | None:
        """The device number, once it is known to work at the modem's rate in mono."""
        devices = self.list_devices()
        number = find_device(devices, device, direction)
        sd = self._sd()
        check = sd.check_input_settings if direction == "input" else sd.check_output_settings
        try:
            check(device=number, channels=1, samplerate=SAMPLE_RATE)
        except sd.PortAudioError as error:
            own = next((d.rate_hz for d in devices if d.index == number), None)
            hint = f" (its own rate is {own:.0f} Hz)" if own else ""
            raise UnsupportedAudioError(
                f"the {direction} device cannot be opened at {SAMPLE_RATE} Hz in mono{hint}: "
                f"{error}"
            ) from error
        return number

    def play(self, samples: np.ndarray, device: int | str | None = None) -> None:
        data = _playable(samples)
        number = self._open_check("output", device)
        sd = self._sd()
        try:
            sd.play(data, samplerate=SAMPLE_RATE, device=number)
            sd.wait()
        except sd.PortAudioError as error:
            raise NoAudioDeviceError(str(error)) from error

    def record(self, seconds: float, device: int | str | None = None) -> np.ndarray:
        _positive(seconds, "a recording")
        number = self._open_check("input", device)
        sd = self._sd()
        try:
            data = sd.rec(
                round(seconds * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=number,
            )
            sd.wait()
        except sd.PortAudioError as error:
            raise NoAudioDeviceError(str(error)) from error
        return np.asarray(data[:, 0], dtype=np.float32)

    def listen(
        self, device: int | str | None = None, block_seconds: float = 0.5, capacity: int = 64
    ) -> InputBlocks:
        _positive(block_seconds, "a block of sound")
        number = self._open_check("input", device)
        sd = self._sd()
        blocks: InputBlocks

        def heard(indata, frames, time, status):
            if status.input_overflow:
                blocks.note_lost()
            blocks.push(np.array(indata[:, 0], dtype=np.float32))

        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=round(block_seconds * SAMPLE_RATE),
                channels=1,
                dtype="float32",
                device=number,
                callback=heard,
            )
        except sd.PortAudioError as error:
            raise NoAudioDeviceError(str(error)) from error

        def stop() -> None:
            try:
                stream.stop()
            finally:
                stream.close()

        blocks = InputBlocks(capacity, on_close=stop)
        try:
            stream.start()
        except sd.PortAudioError as error:
            stream.close()
            raise NoAudioDeviceError(str(error)) from error
        return blocks


class FakeAudio:
    """Sound hardware for tests: remembers what is played, serves the input it was given.

    With `loopback` what is played is heard on the input, as with a cable from the output to
    the input of the same machine.
    """

    def __init__(
        self,
        devices: list[DeviceInfo] | None = None,
        input_samples: np.ndarray | None = None,
        loopback: bool = False,
    ):
        self._devices = devices or [DeviceInfo(0, "Fake audio device", 1, 1, float(SAMPLE_RATE))]
        self._input = np.zeros(0, dtype=np.float32)
        if input_samples is not None:
            self._input = _playable(input_samples)
        self._loopback = loopback
        self.played: list[np.ndarray] = []

    def list_devices(self) -> list[DeviceInfo]:
        return list(self._devices)

    def play(self, samples: np.ndarray, device: int | str | None = None) -> None:
        find_device(self._devices, device, "output")
        data = _playable(samples)
        self.played.append(data)
        if self._loopback:
            self._input = np.concatenate([self._input, data])

    def _take(self, count: int | None) -> np.ndarray:
        count = self._input.size if count is None else count
        taken, self._input = self._input[:count], self._input[count:]
        return np.concatenate([taken, np.zeros(count - taken.size, dtype=np.float32)])

    def record(self, seconds: float, device: int | str | None = None) -> np.ndarray:
        find_device(self._devices, device, "input")
        _positive(seconds, "a recording")
        return self._take(round(seconds * SAMPLE_RATE))

    def listen(
        self, device: int | str | None = None, block_seconds: float = 0.5, capacity: int = 64
    ) -> InputBlocks:
        find_device(self._devices, device, "input")
        _positive(block_seconds, "a block of sound")
        size = round(block_seconds * SAMPLE_RATE)
        everything = self._take(None)
        blocks = InputBlocks(capacity)
        for start in range(0, everything.size, size):
            blocks.push(everything[start : start + size])
        blocks.close()  # the scripted input has ended
        return blocks

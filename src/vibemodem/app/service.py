"""The application's service: settings, sending, cancelling and listening. No HTTP here.

One `ModemService` owns the sound hardware and the threads: at most one Transmission being
played, and one listening loop that decodes a sliding window of what it hears. Messages that
are heard are kept in memory only (the last `max_received`).
"""

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from vibemodem.core import mfsk, presets
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import Fragment, Reassembler, fragment_count, random_message_id
from vibemodem.core.transmission import (
    check_copies,
    explain_refusal,
    max_message_bytes,
    transmit,
)
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import Audio, AudioError, DeviceInfo, InputBlocks, find_device

WINDOW_SECONDS = 150.0  # more than two of the longest Frames, so every Frame is whole at a decode
DECODE_EVERY_SECONDS = 10.0
BLOCK_SECONDS = 0.5
MAX_RECEIVED = 100
MAX_SENDING_MODEMS = 8  # one per Preset and frequency recently sent at
JOIN_SECONDS = 10.0  # for the thread that plays a Transmission, once it has been told to stop
# For the listening thread: it decodes what was heard last, up to 150 s of sound, and a slow or busy
# computer takes its time; a Message heard just before the stop must not be missed for want of it.
STOP_LISTENING_SECONDS = 120.0


class SettingsError(ValueError):
    """The settings asked for are invalid; none of them was applied."""


class BusyError(RuntimeError):
    """The service is doing something that excludes this, or is closed."""


class Cancelled(BusyError):
    """The Transmission was cancelled (or the application closed) before any sound was played."""


@dataclass(frozen=True)
class Settings:
    preset: str = presets.DEFAULT_PRESET
    input_device: int | str | None = None
    output_device: int | str | None = None


@dataclass(frozen=True)
class Sent:
    msg_id: int
    fragments: int
    copies: int
    airtime_seconds: float


@dataclass(frozen=True)
class Estimate:
    """What sending a Message as asked would take, and whether it may be sent at all."""

    fragments: int
    airtime_seconds: float
    max_bytes: int  # the largest Message this Preset allows with these copies
    fits: bool
    reason: str | None  # why not, and what to do instead
    frequency_range_hz: tuple[float, float]
    default_frequency_hz: float
    frequency_problem: str | None


@dataclass(frozen=True)
class Heard:
    """A Message heard: whole, or only in part (`text` is then None and `parts` shows what)."""

    number: int | None  # the order of arrival of a whole Message
    complete: bool
    msg_id: int
    total: int  # of Fragments
    text: str | None
    parts: list[tuple[int, str]]  # (offset in bytes, text) of each stretch heard of a part Message
    missing: tuple[int, ...]
    heard_at: float


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class ModemService:
    def __init__(
        self,
        audio: Audio,
        *,
        make_modem: Callable = TurboModem,
        window_seconds: float = WINDOW_SECONDS,
        decode_every_seconds: float = DECODE_EVERY_SECONDS,
        max_received: int = MAX_RECEIVED,
    ):
        self._audio = audio
        self._make_modem = make_modem
        self._window_samples = round(window_seconds * SAMPLE_RATE)
        self._decode_every = round(decode_every_seconds * SAMPLE_RATE)
        self._lock = threading.RLock()
        self._settings = Settings()
        # For sending only (listening has its own): the last few, each a heavy object.
        self._sending_modems: OrderedDict[tuple, object] = OrderedDict()
        self._frame_samples: dict[str, int] = {}  # of one Frame, for each Preset
        self._closed = False
        self._sending = False
        self._cancel_asked = False
        self._send_thread: threading.Thread | None = None
        self._last_id: int | None = None
        self._blocks: InputBlocks | None = None
        self._listen_thread: threading.Thread | None = None
        self._reassembler = Reassembler(max_given_up=max_received)
        self._whole: deque[Heard] = deque(maxlen=max_received)
        self._count = 0
        self._last_error: str | None = None

    # Settings -------------------------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        return self._settings

    def _check_idle(self) -> None:
        self._not_closed()
        if self._sending or self._listening():
            raise BusyError("stop sending and listening before changing the settings")

    def apply_settings(self, **changes) -> Settings:
        """Change settings all together or not at all."""
        with self._lock:
            self._check_idle()
        problems = []
        unknown = set(changes) - {"preset", "input_device", "output_device"}
        if unknown:
            problems.append(f"unknown settings: {', '.join(sorted(unknown))}")
        if "preset" in changes and changes["preset"] not in presets.PRESETS:
            known = ", ".join(presets.PRESETS)
            problems.append(f"preset {changes['preset']!r} is not one of {known}")
        wanted = [(n, d) for n, d in (("input_device", "input"), ("output_device", "output"))
                  if changes.get(n) is not None]  # fmt: skip
        if wanted:  # the sound card is asked outside the lock: it can be slow
            try:
                devices = self._audio.list_devices()
            except AudioError as error:
                problems.append(f"audio: {error}")
            else:
                for name, direction in wanted:
                    try:
                        find_device(devices, changes[name], direction)
                    except AudioError as error:
                        problems.append(f"{direction}: {error}")
        if problems:
            raise SettingsError("; ".join(problems))
        with self._lock:
            self._check_idle()  # it may have changed while the devices were looked at
            self._settings = replace(self._settings, **changes)
            return self._settings

    def devices(self) -> list[DeviceInfo]:
        """The audio devices; raises `AudioLibraryUnavailableError` when PortAudio is missing."""
        return self._audio.list_devices()

    def _frequency_problem(self, preset: str, frequency_hz) -> str | None:
        """Why the lowest-tone frequency asked for cannot be used in the Preset, if so."""
        if frequency_hz is None:
            return None
        low, high = presets.frequency_range_hz(preset)
        number = isinstance(frequency_hz, int | float) and not isinstance(frequency_hz, bool)
        if not number or not low <= frequency_hz <= high:
            return (
                f"the frequency of the lowest tone must be a number of Hz between {low:g} and "
                f"{high:g} in the {preset!r} Preset (the whole Signal stays in 300 to 2700 Hz), "
                f"got {frequency_hz!r}"
            )
        return None

    def estimate(
        self, message: str | bytes, copies: int = 1, frequency_hz: float | None = None
    ) -> Estimate:
        """What sending the Message would take, without making any sound."""
        check_copies(copies)
        length = len(message.encode("utf-8")) if isinstance(message, str) else len(message)
        with self._lock:
            preset = self._settings.preset
            if preset not in self._frame_samples:  # a modem of its own: nobody else uses it
                probe = self._make_modem(preset=preset)
                size = probe.modulate(Fragment(0, 0, 1, b"").pack(), preset).size
                self._frame_samples[preset] = size
            samples = self._frame_samples[preset]
        reason = explain_refusal(length, preset, copies, samples)
        fragments = fragment_count(length)
        return Estimate(
            fragments=fragments,
            airtime_seconds=fragments * copies * samples / SAMPLE_RATE,
            max_bytes=max_message_bytes(samples / SAMPLE_RATE, copies),
            fits=reason is None,
            reason=reason,
            frequency_range_hz=presets.frequency_range_hz(preset),
            default_frequency_hz=mfsk.FIRST_TONE_HZ,
            frequency_problem=self._frequency_problem(preset, frequency_hz),
        )

    def selftest(self) -> bool:
        """The modem against itself without noise: proves the DSP libraries are all there."""
        modem = self._make_modem(preset="fast")
        heard = modem.demodulate(modem.modulate(b"selftest", "fast"))
        return [r.message for r in heard] == [b"selftest"]

    # State ----------------------------------------------------------------------------------

    def _not_closed(self) -> None:
        if self._closed:
            raise BusyError("the application is closed")

    def _listening(self) -> bool:
        return self._listen_thread is not None and self._listen_thread.is_alive()

    def _fail(self, message: str | None) -> None:
        with self._lock:
            self._last_error = message

    def status(self) -> dict:
        with self._lock:
            return {
                "sending": self._sending,
                "listening": self._listening(),
                "settings": {
                    "preset": self._settings.preset,
                    "input_device": self._settings.input_device,
                    "output_device": self._settings.output_device,
                },
                "received": len(self._whole),
                "incomplete": len(self._reassembler.pending()),
                "blocks_lost": self._blocks.dropped if self._blocks else 0,
                "last_error": self._last_error,
            }

    # Sending --------------------------------------------------------------------------------

    def send(
        self, message: str | bytes, copies: int = 1, frequency_hz: float | None = None
    ) -> Sent:
        """Play a Message in the chosen Preset; return as soon as the sound is on its way.

        `frequency_hz` is where the lowest tone of the Signal is, within the Preset's range.
        """
        data = message.encode("utf-8") if isinstance(message, str) else bytes(message)
        with self._lock:
            self._not_closed()
            if self._sending:
                raise BusyError("a Message is already being sent: cancel it or wait")
            if problem := self._frequency_problem(self._settings.preset, frequency_hz):
                raise ValueError(problem)  # before anything is taken: nothing to give back
            self._sending, self._cancel_asked, self._send_thread = True, False, None
            preset, device, last_id = (
                self._settings.preset,
                self._settings.output_device,
                self._last_id,
            )
        try:
            modem = self._sending_modem(preset, frequency_hz)
            msg_id = random_message_id(last_id)
            sound = transmit(modem, data, preset, msg_id=msg_id, copies=copies)
            with self._lock:  # the sound is ready: unless it was cancelled or we closed meanwhile
                if self._cancel_asked or self._closed:
                    raise Cancelled("cancelled before any sound was played")
                self._last_id = msg_id
                self._last_error = None
                self._send_thread = threading.Thread(
                    target=self._play, args=(sound, device), name="vibemodem-send", daemon=True
                )
                self._send_thread.start()
        except BaseException:
            with self._lock:
                self._sending, self._send_thread = False, None
            raise
        return Sent(
            msg_id=msg_id,
            fragments=fragment_count(len(data)),
            copies=copies,
            airtime_seconds=sound.size / SAMPLE_RATE,
        )

    def _sending_modem(self, preset: str, frequency_hz: float | None):
        with self._lock:
            key = (preset, frequency_hz)
            if key not in self._sending_modems:
                options = {} if frequency_hz is None else {"first_tone_hz": float(frequency_hz)}
                self._sending_modems[key] = self._make_modem(preset=preset, **options)
                while len(self._sending_modems) > MAX_SENDING_MODEMS:
                    self._sending_modems.popitem(last=False)
            self._sending_modems.move_to_end(key)
            return self._sending_modems[key]

    def _play(self, sound: np.ndarray, device) -> None:
        try:
            self._audio.play(sound, device=device)
        except Exception as error:  # a sound card can fail in many ways; say which, keep going
            self._fail(str(error))
        finally:
            with self._lock:
                self._sending = False

    def cancel(self) -> bool:
        """Cut the Transmission, if any: being made (it will not play) or being played."""
        with self._lock:
            if not self._sending:
                return False
            self._cancel_asked = True
            thread = self._send_thread
        deadline = time.monotonic() + JOIN_SECONDS
        while thread is not None and thread.is_alive() and time.monotonic() < deadline:
            self._audio.stop()
            thread.join(timeout=0.05)
        return True

    # Listening ------------------------------------------------------------------------------

    def start_listening(self) -> None:
        with self._lock:
            self._not_closed()
            if self._listening():
                raise BusyError("already listening")
            if self._blocks is not None:
                self._blocks.close()  # the stream of a listening that ended on its own
            modem = self._make_modem(preset=self._settings.preset)  # not shared with sending
            self._blocks = self._audio.listen(
                device=self._settings.input_device,
                block_seconds=BLOCK_SECONDS,
                capacity=int(2 * WINDOW_SECONDS / BLOCK_SECONDS),
            )
            self._last_error = None
            self._listen_thread = threading.Thread(
                target=self._listen,
                args=(self._blocks, modem),
                name="vibemodem-listen",
                daemon=True,
            )
            self._listen_thread.start()

    def stop_listening(self) -> bool:
        """Stop hearing the input once what is already heard has been decoded."""
        with self._lock:
            thread, blocks = self._listen_thread, self._blocks
        if thread is None or blocks is None:
            return False
        was_listening = thread.is_alive()
        blocks.close()
        thread.join(timeout=STOP_LISTENING_SECONDS)
        with self._lock:
            if not thread.is_alive() and self._listen_thread is thread:
                self._listen_thread = None  # still alive after the wait: it stays reported
        return was_listening

    def _listen(self, blocks: InputBlocks, modem) -> None:
        window: deque[np.ndarray] = deque()
        held = since_decode = 0
        try:
            for block in blocks:
                window.append(block)
                held += block.size
                since_decode += block.size
                while held - window[0].size >= self._window_samples:
                    held -= window.popleft().size
                if since_decode >= self._decode_every:
                    self._decode(window, modem)
                    since_decode = 0
            self._decode(window, modem)  # what was heard last
        except Exception as error:  # whatever happens, the stream is closed below
            self._fail(f"listening stopped: {error}")
        finally:
            blocks.close()

    def _decode(self, window: deque[np.ndarray], modem) -> None:
        if not window:
            return
        try:
            receptions = modem.demodulate(np.concatenate(list(window)).astype(np.float64))
        except Exception as error:  # a bad stretch of audio must not end the listening
            self._fail(f"decoding failed: {error}")
            return
        # What is heard first is delivered first: the receiver sorts by how sure it is.
        for reception in sorted(receptions, key=lambda r: (r.start_sample is None, r.start_sample)):
            try:
                self._take(Fragment.unpack(reception.message))
            except Exception as error:  # one bad reception must not hide the others
                self._fail(f"a reception was not understood: {error}")

    def _take(self, fragment: Fragment | None) -> None:
        if fragment is None:
            return
        with self._lock:
            done = self._reassembler.add(fragment)
            if done:
                self._count += 1
                self._whole.append(
                    Heard(
                        number=self._count,
                        complete=True,
                        msg_id=done.msg_id,
                        total=fragment.total,
                        text=_text(done.message),
                        parts=[],
                        missing=(),
                        heard_at=time.time(),
                    )
                )

    def received(self) -> list[Heard]:
        """The Messages heard whole, in order of arrival, then those heard in part."""
        with self._lock:
            whole = list(self._whole)
            pending = self._reassembler.pending()
        partial = [
            Heard(
                number=None,
                complete=False,
                msg_id=part.msg_id,
                total=part.total,
                text=None,
                parts=[(offset, _text(data)) for offset, data in part.runs()],
                missing=part.missing,
                heard_at=0.0,
            )
            for part in pending
        ]
        return whole + partial

    # Closing --------------------------------------------------------------------------------

    def close(self) -> None:
        """Stop sending and listening, join the threads, free the audio. Safe to repeat."""
        with self._lock:
            self._closed = True
        self.cancel()
        self.stop_listening()

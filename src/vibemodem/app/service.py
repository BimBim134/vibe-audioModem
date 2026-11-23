"""The application's service: settings, sending and cancelling, and listening. No HTTP here.

One `ModemService` owns the sound hardware: at most one Transmission being played, and the
`Receiver` that listens, decodes a sliding window of what it hears, and keeps what was heard in
memory only (the last `max_received` Messages).
"""

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace

import numpy as np

from vibemodem.app import callsign as callsign_module
from vibemodem.app import ptt as ptt_module
from vibemodem.app import receiver as receiver_module
from vibemodem.app.blanking import Blanking
from vibemodem.app.conversation import SentEntry, build_conversation
from vibemodem.app.heard import Heard, SpectrumRows, Undecoded
from vibemodem.app.receiver import Receiver
from vibemodem.app.settings_file import SettingsFile
from vibemodem.app.store import ReceptionStore
from vibemodem.core import mfsk, presets
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import Fragment, fragment_count, random_message_id
from vibemodem.core.transmission import (
    check_copies,
    explain_refusal,
    lead_in,
    max_message_bytes,
    transmit,
)
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import Audio, AudioError, DeviceInfo, find_device

MEGABYTE = 1_000_000
MIN_LIMIT_MB, MAX_LIMIT_MB = 10, 100_000
DEFAULT_LIMIT_MB = 200
DEFAULT_TX_MARGIN_MS = 250  # of silence after the end of playback, besides the output latency
MAX_TX_MARGIN_MS = 10_000
MAX_LEAD_IN_MS = 5_000
MAX_SENDING_MODEMS = 8  # one per Preset and frequency recently sent at
JOIN_SECONDS = 10.0  # for the thread that plays a Transmission, once it has been told to stop


class SettingsError(ValueError):
    """The settings asked for are invalid; none of them was applied."""


class BusyError(RuntimeError):
    """The service is doing something that excludes this, or is closed."""


class Cancelled(BusyError):
    """The Transmission was cancelled (or the application closed) before any sound was played."""


def check_margin(margin_ms: int) -> None:
    if (
        not isinstance(margin_ms, int)
        or isinstance(margin_ms, bool)
        or not 0 <= margin_ms <= MAX_TX_MARGIN_MS
    ):
        raise ValueError(
            f"the TX blanking margin must be a whole number of ms, 0 to {MAX_TX_MARGIN_MS}"
        )


def check_lead_in(lead_in_ms: int) -> None:
    if (
        not isinstance(lead_in_ms, int)
        or isinstance(lead_in_ms, bool)
        or not 0 <= lead_in_ms <= MAX_LEAD_IN_MS
    ):
        raise ValueError(f"the Lead-in must be a whole number of ms, 0 to {MAX_LEAD_IN_MS}")


# Settings with one value to check, and that can change at any time, even while listening.
CHECKED = {
    "tx_margin_ms": check_margin,
    "lead_in_ms": check_lead_in,
    "ptt": ptt_module.check_flag,
    "ptt_host": ptt_module.check_host,
    "ptt_port": ptt_module.check_port,
    "ptt_before_ms": ptt_module.check_delay,
    "ptt_after_ms": ptt_module.check_delay,
}


@dataclass(frozen=True)
class Settings:
    preset: str = presets.DEFAULT_PRESET
    input_device: int | str | None = None
    output_device: int | str | None = None
    copies: int = 1
    callsign: str | None = None
    tx_margin_ms: int = DEFAULT_TX_MARGIN_MS
    lead_in_ms: int = 0
    ptt: bool = False
    ptt_host: str = ptt_module.DEFAULT_HOST
    ptt_port: int = ptt_module.DEFAULT_PORT
    ptt_before_ms: int = ptt_module.DEFAULT_BEFORE_MS
    ptt_after_ms: int = ptt_module.DEFAULT_AFTER_MS


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
    signal_width_hz: float  # from the lowest tone to the highest


class ModemService:
    def __init__(
        self,
        audio: Audio,
        *,
        make_modem: Callable = TurboModem,
        window_seconds: float | None = None,
        decode_every_seconds: float = receiver_module.DECODE_EVERY_SECONDS,
        max_received: int = receiver_module.MAX_RECEIVED,
        store: ReceptionStore | None = None,
        settings_file: SettingsFile | None = None,
    ):
        self._audio = audio
        self._settings_file = settings_file
        self._make_modem = make_modem
        self._blanking = Blanking()
        self._receiver = Receiver(
            audio,
            make_modem,
            window_seconds=window_seconds,
            decode_every_seconds=decode_every_seconds,
            max_received=max_received,
            store=store,
            blanking=self._blanking,
        )
        self._lock = threading.RLock()
        self._settings = Settings()
        self._search_band: tuple[float, float] | None = None
        # For sending only (listening has its own): the last few, each a heavy object.
        self._sending_modems: OrderedDict[tuple, object] = OrderedDict()
        self._frame_samples: dict[str, int] = {}  # of one Frame, for each Preset
        self._sent_log: deque[SentEntry] = deque(maxlen=max_received)
        self._sent_count = 0
        self._closed = False
        self._sending = False
        self._cancel_asked = False
        self._send_thread: threading.Thread | None = None
        self._last_id: int | None = None
        self._last_error: str | None = None
        self._load_settings()

    # Settings -------------------------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        return self._settings

    def _load_settings(self) -> None:
        """Take the settings the last run kept. Each value is checked and a bad one is ignored,
        so a damaged file costs the values it damaged and nothing else."""
        if self._settings_file is None:
            return
        saved = self._settings_file.read()
        changes = {}
        preset = saved.get("preset")
        if isinstance(preset, str) and preset in presets.PRESETS:
            changes["preset"] = preset
        try:
            check_copies(saved.get("copies"))
            changes["copies"] = saved["copies"]
        except ValueError:
            pass
        try:
            if (callsign := callsign_module.normalise(saved.get("callsign"))) is not None:
                changes["callsign"] = callsign
        except ValueError:
            pass
        for name, check in CHECKED.items():
            try:
                check(saved.get(name))
                changes[name] = saved[name]
            except ValueError:
                pass
        devices = None
        for name, direction in (("input_device", "input"), ("output_device", "output")):
            wanted = saved.get(name)
            if isinstance(wanted, bool) or not isinstance(wanted, int | str):
                continue
            try:  # a device that is not there now stays in the file, for when it is back
                devices = self._audio.list_devices() if devices is None else devices
                find_device(devices, wanted, direction)
            except AudioError:
                continue
            changes[name] = wanted
        self._settings = replace(self._settings, **changes)
        storage = {}
        keep, limit_mb = saved.get("keep"), saved.get("limit_mb")
        if isinstance(keep, bool):
            storage["keep"] = keep
        if isinstance(limit_mb, int) and not isinstance(limit_mb, bool):
            if MIN_LIMIT_MB <= limit_mb <= MAX_LIMIT_MB:
                storage["limit_mb"] = limit_mb
        if storage and self._receiver.store is not None:
            self._set_storage(**{"keep": None, "limit_mb": None, **storage})

    def _remember(self, **values) -> None:
        if self._settings_file is not None:
            self._settings_file.update(**values)

    def _check_idle(self) -> None:
        self._not_closed()
        if self._sending or self._receiver.listening:
            raise BusyError("stop sending and listening before changing the settings")

    def _check_can_change(self, changes: dict) -> None:
        """The number of copies, the Callsign and the settings of CHECKED can change at any time;
        the rest only while nothing is going on."""
        if set(changes) <= {"copies", "callsign", *CHECKED}:
            self._not_closed()
        else:
            self._check_idle()

    def apply_settings(self, **changes) -> Settings:
        """Change settings all together or not at all."""
        with self._lock:
            self._check_can_change(changes)
        problems = []
        settable = {"preset", "input_device", "output_device", "copies", "callsign", *CHECKED}
        unknown = set(changes) - settable
        if unknown:
            problems.append(f"unknown settings: {', '.join(sorted(unknown))}")
        if "preset" in changes and changes["preset"] not in presets.PRESETS:
            known = ", ".join(presets.PRESETS)
            problems.append(f"preset {changes['preset']!r} is not one of {known}")
        if "copies" in changes:
            try:
                check_copies(changes["copies"])
            except ValueError as error:
                problems.append(str(error))
        for name, check in CHECKED.items():
            if name in changes:
                try:
                    check(changes[name])
                except ValueError as error:
                    problems.append(str(error))
        if "callsign" in changes:
            try:
                changes["callsign"] = callsign_module.normalise(changes["callsign"])
            except ValueError as error:
                problems.append(str(error))
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
            self._check_can_change(changes)  # it may have changed while the devices were looked at
            if "preset" in changes:
                self._check_band_fits(changes["preset"], self._search_band)
            self._settings = replace(self._settings, **changes)
            self._remember(**changes)
            return self._settings

    # The audio band listened in -------------------------------------------------------------

    def search_band(self) -> tuple[float, float] | None:
        return self._search_band

    @staticmethod
    def _check_band_fits(preset: str, band: tuple[float, float] | None) -> None:
        if band is None:
            return
        needed = presets.minimum_band_hz(preset)
        if band[1] - band[0] < needed:
            raise SettingsError(
                f"the band {band[0]:g} to {band[1]:g} Hz is too narrow for the {preset!r} Preset, "
                f"which needs at least {needed:g} Hz from its lowest tone to its highest: "
                "widen the band first"
            )

    def set_search_band(
        self, low_hz: float | None, high_hz: float | None
    ) -> tuple[float, float] | None:
        """Hear only the Signals entirely inside a band of audio; (None, None): all of it.
        It applies at the next decoding pass, also while listening."""
        if low_hz is None and high_hz is None:
            band = None
        else:
            if low_hz is None or high_hz is None:
                raise SettingsError("give both frequencies of the band, or neither")
            for value in (low_hz, high_hz):
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise SettingsError(
                        f"the frequencies of the band are numbers of Hz, got {value!r}"
                    )
            low, high = mfsk.SEARCH_BAND_HZ
            if not low <= low_hz <= high or not low <= high_hz <= high:
                raise SettingsError(f"the band must lie in {low:g} to {high:g} Hz")
            if low_hz >= high_hz:
                raise SettingsError("the low frequency must be below the high one")
            band = (float(low_hz), float(high_hz))
        with self._lock:
            self._not_closed()
            self._check_band_fits(self._settings.preset, band)
            self._search_band = band
            self._receiver.set_search_band(band)
            return band

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
            lead_in_seconds = self._settings.lead_in_ms / 1000
            length += len(callsign_module.prefix(self._settings.callsign))
            if preset not in self._frame_samples:  # a modem of its own: nobody else uses it
                probe = self._make_modem(preset=preset)
                size = probe.modulate(Fragment(0, 0, 1, b"").pack(), preset).size
                self._frame_samples[preset] = size
            samples = self._frame_samples[preset]
        reason = explain_refusal(length, preset, copies, samples)
        profile = presets.profile(preset)
        fragments = fragment_count(length)
        return Estimate(
            fragments=fragments,
            airtime_seconds=fragments * copies * samples / SAMPLE_RATE + lead_in_seconds,
            max_bytes=max_message_bytes(samples / SAMPLE_RATE, copies),
            fits=reason is None,
            reason=reason,
            frequency_range_hz=presets.frequency_range_hz(preset),
            default_frequency_hz=mfsk.FIRST_TONE_HZ,
            frequency_problem=self._frequency_problem(preset, frequency_hz),
            signal_width_hz=(profile.tones - 1) * 1000 / profile.symbol_ms,
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

    def _fail(self, message: str) -> None:
        with self._lock:
            self._last_error = message

    def status(self) -> dict:
        with self._lock:
            return {
                "sending": self._sending,
                "listening": self._receiver.listening,
                "settings": asdict(self._settings),
                "search_band": None if self._search_band is None else list(self._search_band),
                "received": self._receiver.counts[0],
                "incomplete": self._receiver.counts[1],
                "blocks_lost": self._receiver.blocks_lost,
                "last_error": self._receiver.last_error or self._last_error,
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
            data = callsign_module.prefix(self._settings.callsign) + data
            self._sending, self._cancel_asked, self._send_thread = True, False, None
            radio = (  # the PTT as set now: what is sent is not changed by a later setting
                ptt_module.RigctldPtt(self._settings.ptt_host, self._settings.ptt_port)
                if self._settings.ptt
                else None,
                self._settings.ptt_before_ms / 1000,
                self._settings.ptt_after_ms / 1000,
            )
            preset, device, last_id, lead_in_ms = (
                self._settings.preset,
                self._settings.output_device,
                self._last_id,
                self._settings.lead_in_ms,
            )
        try:
            modem = self._sending_modem(preset, frequency_hz)
            msg_id = random_message_id(last_id)
            sound = transmit(modem, data, preset, msg_id=msg_id, copies=copies)
            if lead_in_ms:  # before the first Preamble, as loud as the Signal
                tone = lead_in(
                    float(frequency_hz or mfsk.FIRST_TONE_HZ),
                    lead_in_ms,
                    level=float(np.abs(sound).max()),
                )
                sound = np.concatenate([tone, sound])
            with self._lock:  # the sound is ready: unless it was cancelled or we closed meanwhile
                if self._cancel_asked or self._closed:
                    raise Cancelled("cancelled before any sound was played")
                self._last_id = msg_id
                self._last_error = None
                self._sent_count += 1
                entry = SentEntry(
                    id=self._sent_count,
                    text=data.decode("utf-8", errors="replace"),
                    at=time.time(),
                    status="sending",
                    fragments=fragment_count(len(data)),
                    copies=copies,
                    frequency_hz=float(frequency_hz or mfsk.FIRST_TONE_HZ),
                    airtime_seconds=sound.size / SAMPLE_RATE,
                )
                self._sent_log.append(entry)
                self._send_thread = threading.Thread(
                    target=self._play,
                    args=(sound, device, entry, radio),
                    name="vibemodem-send",
                    daemon=True,
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

    def _play(self, sound: np.ndarray, device, entry: SentEntry, radio) -> None:
        """Key the radio if asked to, play, and release it whatever happened."""
        ptt, before, after = radio
        outcome, error_text = "sent", None
        keyed = False
        began = time.monotonic()
        self._blanking.start(time.time())  # the station is transmitting from the PTT on
        try:
            if ptt is not None:
                keyed = True  # even if the answer is lost, the radio may be keyed: release it
                ptt.key(True)
                self._wait(before)
            began = time.monotonic()
            if not self._cancel_asked:
                self._audio.play(sound, device=device)
            self._wait(after if ptt is not None else 0.0)
        except Exception as error:  # a sound card can fail in many ways; say which, keep going
            outcome, error_text = "failed", str(error)
            self._fail(error_text)
        finally:
            if keyed:
                try:
                    ptt.key(False)
                except ptt_module.PttError as error:
                    if outcome != "failed":
                        outcome, error_text = "failed", str(error)
                    self._fail(str(error))
            with self._lock:
                self._blanking.end(
                    time.time()
                    + self._audio.output_latency_seconds
                    + self._settings.tx_margin_ms / 1000
                )
                played = time.monotonic() - began
                if (
                    outcome == "sent"
                    and self._cancel_asked
                    and played < entry.airtime_seconds - 0.5
                ):
                    outcome = "cancelled"  # a cancel in the last instants cut nothing: it was sent
                entry.status, entry.error = outcome, error_text
                self._sending = False

    def _wait(self, seconds: float) -> None:
        """A pause of the Transmission, cut short by a cancel."""
        deadline = time.monotonic() + seconds
        while not self._cancel_asked and (left := deadline - time.monotonic()) > 0:
            time.sleep(min(left, 0.02))

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

    # Receptions kept -----------------------------------------------------------------------

    def storage(self) -> dict:
        """Whether receptions are kept, the bound, and what is kept now."""
        store = self._receiver.store
        if store is None:
            return {"available": False, "keep": False}
        count, used = store.usage()
        return {
            "available": True,
            "keep": self._receiver.keeping,
            "limit_mb": store.max_bytes / MEGABYTE,
            "count": count,
            "used_mb": used / MEGABYTE,
            "directory": str(store.directory),
        }

    def set_storage(self, keep: bool | None = None, limit_mb: int | None = None) -> dict:
        """Keep receptions or not, and the bound, together or not at all."""
        with self._lock:
            storage = self._set_storage(keep, limit_mb)
            self._remember(
                **{n: v for n, v in (("keep", keep), ("limit_mb", limit_mb)) if v is not None}
            )
            return storage

    def _set_storage(self, keep: bool | None, limit_mb: int | None) -> dict:
        store = self._receiver.store
        problems = []
        if store is None:
            problems.append("receptions cannot be kept: there is nowhere to keep them")
        if keep is not None and not isinstance(keep, bool):
            problems.append("keep must be true or false")
        if limit_mb is not None and (
            isinstance(limit_mb, bool)
            or not isinstance(limit_mb, int)
            or not MIN_LIMIT_MB <= limit_mb <= MAX_LIMIT_MB
        ):
            problems.append(
                f"the bound is a whole number of MB from {MIN_LIMIT_MB} to {MAX_LIMIT_MB}"
            )
        if problems:
            raise SettingsError("; ".join(problems))
        if limit_mb is not None:
            store.set_max_bytes(limit_mb * MEGABYTE)
        if keep is not None:
            self._receiver.set_keeping(keep)
        return self.storage()

    def clear_receptions(self) -> int:
        """Delete every reception that was kept; returns how many."""
        store = self._receiver.store
        return 0 if store is None else store.clear()

    # Listening ------------------------------------------------------------------------------

    def start_listening(self) -> None:
        with self._lock:
            self._not_closed()
            if self._receiver.listening:
                raise BusyError("already listening")
            self._receiver.start(self._settings.preset, self._settings.input_device)

    def stop_listening(self) -> bool:
        """Stop hearing the input once what is already heard has been decoded."""
        return self._receiver.stop()

    def conversation(self) -> list[dict]:
        """What was sent and what was heard, oldest first, for the page."""
        with self._lock:
            sent = [replace(e) for e in self._sent_log]
        receiver = self._receiver
        return build_conversation(
            sent, receiver.received(), receiver.undecoded(), receiver.arriving()
        )

    def received(self) -> list[Heard]:
        """The Messages heard whole, in order of arrival, then those heard in part."""
        return self._receiver.received()

    def undecoded(self) -> list[Undecoded]:
        """The Signals found whole whose Message was not read, the last few, oldest first."""
        return self._receiver.undecoded()

    def spectrum(self, since: int = 0) -> SpectrumRows:
        """The rows of the spectrum of the sound heard, from number `since` on."""
        return self._receiver.spectrum(since)

    # Closing --------------------------------------------------------------------------------

    def close(self) -> None:
        """Stop sending and listening, join the threads, free the audio. Safe to repeat."""
        with self._lock:
            self._closed = True
        self.cancel()
        self.stop_listening()

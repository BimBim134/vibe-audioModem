"""Listening: what is heard is decoded, kept, and drawn. No HTTP and no sending here.

A `Receiver` hears an input through the audio layer, draws a row of the spectrum for each block
of sound, and every few seconds decodes the last minutes of what it heard: Messages are put
back together once for the whole session, how each one was received is kept, and a Signal that
was found but could not be read is listed once. Times are by the audio clock: the time the
listening started plus the sound heard since, which is the time of day when the input is a live
one.
"""

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

import numpy as np

from vibemodem.app.heard import Heard, Quality, SpectrumRows, Tolerance, Undecoded, alike, summarize
from vibemodem.app.keeper import Keeper
from vibemodem.app.store import ReceptionStore
from vibemodem.core import mfsk
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import Fragment, Reassembler
from vibemodem.core.spectrum import spectrum_row
from vibemodem.io.audio import Audio, InputBlocks

# What a pass decodes is the last Frame's length of sound and a little more: a Frame that has just
# ended is whole in it, with sound around it to measure the noise, and what was decoded in an
# earlier pass is not decoded again from the start of a long window.
SLICE_EXTRA_SECONDS = 10.0
DECODE_EVERY_SECONDS = 2.0
QUEUE_SECONDS = 300.0  # of sound that may wait for the decoder before the oldest is dropped
BLOCK_SECONDS = 0.5
MAX_RECEIVED = 100
MAX_UNDECODED = 20
SPECTRUM_ROWS = 120  # a minute of sound in blocks of half a second
MEMORY = 64  # Messages whose Fragments are being heard
READ_MEMORY = 256  # Frames read, remembered to tell that a lost Signal was not
STOP_SECONDS = 120.0  # to decode what was heard last, up to 150 s of sound, on a slow computer


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class Receiver:
    def __init__(
        self,
        audio: Audio,
        make_modem: Callable,
        *,
        window_seconds: float | None = None,
        decode_every_seconds: float = DECODE_EVERY_SECONDS,
        max_received: int = MAX_RECEIVED,
        store: ReceptionStore | None = None,
    ):
        self._audio = audio
        self._keeper = Keeper(store)
        self._make_modem = make_modem
        self._window_seconds = window_seconds  # None: what one Frame needs, see `_listen`
        self._decode_every_seconds = decode_every_seconds
        self._decode_every = round(decode_every_seconds * SAMPLE_RATE)
        self._lock = threading.RLock()
        self._blocks: InputBlocks | None = None
        self._thread: threading.Thread | None = None
        self._reassembler = Reassembler(max_given_up=max_received)
        self._quality: OrderedDict[tuple[int, int], dict[int, Quality]] = OrderedDict()
        self._whole: deque[Heard] = deque(maxlen=max_received)
        self._count = 0
        self._undecoded: deque[Undecoded] = deque(maxlen=MAX_UNDECODED)
        self._read: deque[tuple[float, float]] = deque(maxlen=READ_MEMORY)  # (time, frequency)
        self._rows: deque[list[int]] = deque(maxlen=SPECTRUM_ROWS)
        self._row_count = 0
        self.last_error: str | None = None

    # State ----------------------------------------------------------------------------------

    @property
    def listening(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def blocks_lost(self) -> int:
        return self._blocks.dropped if self._blocks else 0

    @property
    def counts(self) -> tuple[int, int]:
        """The Messages heard whole, and those heard in part."""
        with self._lock:
            return len(self._whole), len(self._reassembler.pending())

    @property
    def store(self) -> ReceptionStore | None:
        return self._keeper.store

    @property
    def keeping(self) -> bool:
        return self._keeper.enabled

    def set_keeping(self, keeping: bool) -> None:
        """Keep, or stop keeping, the audio and the indicators of what is read or lost."""
        self._keeper.set_enabled(keeping)

    def _fail(self, message: str) -> None:
        with self._lock:
            self.last_error = message

    # Starting and stopping ------------------------------------------------------------------

    def start(self, preset: str, device: int | str | None) -> None:
        """Start hearing the input. Raises if the sound card cannot be opened."""
        modem = self._make_modem(preset=preset)  # not shared with sending
        tolerance = Tolerance.of(preset, modem.frame_samples())
        with self._lock:
            if self._blocks is not None:
                self._blocks.close()  # the stream of a listening that ended on its own
            self._blocks = self._audio.listen(
                device=device,
                block_seconds=BLOCK_SECONDS,
                capacity=int(QUEUE_SECONDS / BLOCK_SECONDS),
            )
            self.last_error = None
            self._keeper.start()
            self._rows.clear()  # a new waterfall: the page starts from the next row
            self._thread = threading.Thread(
                target=self._listen,
                args=(self._blocks, modem, tolerance),
                name="vibemodem-listen",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> bool:
        """Stop hearing the input once what is already heard has been decoded."""
        with self._lock:
            thread, blocks = self._thread, self._blocks
        if thread is None or blocks is None:
            return False
        was_listening = thread.is_alive()
        blocks.close()
        thread.join(timeout=STOP_SECONDS)
        with self._lock:
            if not thread.is_alive() and self._thread is thread:
                self._thread = None  # still alive after the wait: it stays reported
        return was_listening

    # The listening thread -------------------------------------------------------------------

    def _listen(self, blocks: InputBlocks, modem, tolerance: Tolerance) -> None:
        window: deque[np.ndarray] = deque()
        held = since_decode = heard = 0  # samples: in the window, since the last decode, in all
        extra = round((SLICE_EXTRA_SECONDS + self._decode_every_seconds) * SAMPLE_RATE)
        kept = (  # the sound kept: a Frame, the time between two passes and some sound around
            round(self._window_seconds * SAMPLE_RATE)
            if self._window_seconds
            else modem.frame_samples() + extra
        )
        started = None
        try:
            for block in blocks:
                if started is None:
                    started = time.time() - block.size / SAMPLE_RATE
                self._draw(block)
                window.append(block)
                held += block.size
                heard += block.size
                since_decode += block.size
                while held - window[0].size >= kept:
                    held -= window.popleft().size
                if since_decode >= self._decode_every:
                    self._decode(window, modem, tolerance, started, heard - held)
                    since_decode = 0
            if started is not None:  # the last of it: nothing more will come to complete a margin
                self._decode(window, modem, tolerance, started, heard - held, final=True)
        except Exception as error:  # whatever happens, the stream is closed below
            self._fail(f"listening stopped: {error}")
        finally:
            blocks.close()

    def _draw(self, block: np.ndarray) -> None:
        """One more row of the waterfall."""
        try:
            row = np.round(spectrum_row(block)).astype(int).tolist()
        except ValueError:  # a block too short to measure: nothing to draw
            return
        with self._lock:
            self._rows.append(row)
            self._row_count += 1

    def _decode(
        self, window, modem, tolerance: Tolerance, started: float, window_start: int, final=False
    ):
        """Decode the window; `window_start` is where it starts in everything heard (samples)."""
        if not window:
            return
        samples = np.concatenate(list(window)).astype(np.float64)
        try:
            report = modem.demodulate_report(samples)
        except Exception as error:  # a bad stretch of audio must not end the listening
            self._fail(f"decoding failed: {error}")
            return

        def when(start: int) -> float:
            return started + (window_start + start) / SAMPLE_RATE

        # What is heard first is delivered first: the receiver sorts by how sure it is.
        in_time = sorted(report.receptions, key=lambda r: (r.start_sample is None, r.start_sample))
        for reception in in_time:
            try:
                fragment = Fragment.unpack(reception.message)
                if fragment is not None:
                    self._take(fragment, reception, when(reception.start_sample or 0), tolerance)
            except Exception as error:  # one bad reception must not hide the others
                self._fail(f"a reception was not understood: {error}")
        for lost in report.undecoded:
            # A Frame cut by the start of the window has lost part of its Preamble: it was judged
            # when it was whole, in an earlier pass.
            if window_start > 0 and lost.start_sample < tolerance.preamble_samples:
                continue
            self._note_lost(when(lost.start_sample), lost.frequency_hz, lost.sync_score, tolerance)
        if self._keeper.enabled:
            try:
                listed = lambda at, hz: self._is_listed(at, hz, tolerance)  # noqa: E731
                problems = self._keeper.keep(samples, modem, report, tolerance, when, listed, final)
            except Exception as error:  # whatever happens, the listening goes on
                problems = [f"a reception could not be kept: {error}"]
            if problems:
                self._fail(problems[0])

    def _is_listed(self, at: float, hz: float, tolerance: Tolerance) -> bool:
        """Whether a lost Signal is one the operator is told about (not a side peak, not read)."""
        with self._lock:
            return any(
                alike(at, hz, u.heard_at, u.frequency_hz, tolerance) for u in self._undecoded
            )

    def _take(self, fragment: Fragment, reception, at: float, tolerance: Tolerance) -> None:
        key = (fragment.msg_id, fragment.total)
        quality = Quality.of(reception, at)
        with self._lock:
            self._note_read(quality, tolerance)
            parts = self._quality.setdefault(key, {})
            known = parts.get(fragment.index)
            if known is None or (quality.sync_score or 0) > (known.sync_score or 0):
                parts[fragment.index] = quality  # the clearest sighting of the Fragment
            self._quality.move_to_end(key)
            while len(self._quality) > MEMORY:
                self._quality.popitem(last=False)
            done = self._reassembler.add(fragment)
            if done:
                self._count += 1
                self._whole.append(
                    self._heard(
                        summarize(self._quality.pop(key, parts)),
                        number=self._count,
                        complete=True,
                        msg_id=done.msg_id,
                        total=fragment.total,
                        text=_text(done.message),
                        parts=[],
                        missing=(),
                    )
                )

    def _note_read(self, quality: Quality, tolerance: Tolerance) -> None:
        """A Frame was read: remember where, and forget a lost Signal that was the same one."""
        if quality.frequency_hz is None:
            return
        self._undecoded = deque(
            (
                known
                for known in self._undecoded
                if not self._alike(known.heard_at, known.frequency_hz, quality, tolerance)
            ),
            maxlen=MAX_UNDECODED,
        )
        self._read.append((quality.at, quality.frequency_hz))

    @staticmethod
    def _alike(at: float, hz: float, quality: Quality, tolerance: Tolerance) -> bool:
        return (
            quality.frequency_hz is not None
            and abs(at - quality.at) <= tolerance.seconds
            and abs(hz - quality.frequency_hz) <= tolerance.hertz
        )

    def _note_lost(self, at: float, hz: float, score: float, tolerance: Tolerance) -> None:
        with self._lock:
            apart = tolerance.frame_seconds - tolerance.seconds / 2  # inside a Frame that was read
            if any(
                abs(at - t) < apart and abs(hz - f) <= tolerance.width_hz for t, f in self._read
            ):
                return  # the side peak of a Preamble that was read, or a Frame read in a pass
            for known in self._undecoded:
                if abs(known.heard_at - at) <= tolerance.seconds and (
                    abs(known.frequency_hz - hz) <= tolerance.hertz
                ):
                    return  # the same Signal, seen again in another pass
            self._undecoded.append(Undecoded(at, hz, score))

    @staticmethod
    def _heard(quality: Quality, **fields) -> Heard:
        offset = None if quality.frequency_hz is None else quality.frequency_hz - mfsk.FIRST_TONE_HZ
        return Heard(
            heard_at=quality.at,
            snr_db=quality.snr_db,
            frequency_hz=quality.frequency_hz,
            offset_hz=offset,
            sync_score=quality.sync_score,
            **fields,
        )

    # What was heard -------------------------------------------------------------------------

    def received(self) -> list[Heard]:
        """The Messages heard whole, in order of arrival, then those heard in part."""
        with self._lock:
            whole = list(self._whole)
            pending = self._reassembler.pending()
            qualities = {key: dict(parts) for key, parts in self._quality.items()}
        partial = [
            self._heard(
                summarize(qualities.get((part.msg_id, part.total), {})),
                number=None,
                complete=False,
                msg_id=part.msg_id,
                total=part.total,
                text=None,
                parts=[(offset, _text(data)) for offset, data in part.runs()],
                missing=part.missing,
            )
            for part in pending
        ]
        return whole + partial

    def undecoded(self) -> list[Undecoded]:
        """The Signals found whole whose Message was not read, the last few, oldest first."""
        with self._lock:
            return list(self._undecoded)

    def spectrum(self, since: int = 0) -> SpectrumRows:
        """The rows of the spectrum of the sound heard from number `since` on (the last ones
        kept: older rows are forgotten)."""
        with self._lock:
            oldest = self._row_count - len(self._rows)
            first = max(since, oldest)
            rows = list(self._rows)[first - oldest :]
            return SpectrumRows(first=first, next=self._row_count, rows=rows)

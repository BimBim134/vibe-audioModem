"""Keeping receptions: each Frame read and each Signal lost, once, with sound around it.

What is kept goes to a `ReceptionStore`. The piece of sound begins on the grid of the search of the
window it comes from, so that replaying it searches at the same times and reads the same figures.
"""

from collections import deque
from collections.abc import Callable

import numpy as np

from vibemodem.app.heard import Tolerance, alike
from vibemodem.app.store import ReceptionStore
from vibemodem.core import mfsk
from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import Fragment

MARGIN_SECONDS = 3.0  # of sound kept before and after a Frame
MEMORY = 256  # Frames remembered as kept


class Keeper:
    def __init__(self, store: ReceptionStore | None):
        self.store = store
        self.enabled = False
        self._kept: deque[tuple[float, float]] = deque(maxlen=MEMORY)  # (time, frequency)

    def set_enabled(self, enabled: bool) -> None:
        if enabled and self.store is None:
            raise ValueError("there is nowhere to keep receptions")
        self.enabled = bool(enabled)

    def start(self) -> None:
        """A new listening: what was kept before is not in the new audio."""
        self._kept.clear()

    def keep(
        self,
        samples: np.ndarray,
        modem,
        report,
        tolerance: Tolerance,
        when: Callable[[int], float],
        listed: Callable[[float, float], bool],
        final: bool,
    ) -> list[str]:
        """Keep what the pass found and was not kept yet. Returns what went wrong, one text per
        reception that could not be kept (each is given up on: it is not tried again)."""
        frame = modem.frame_samples()
        margin = round(MARGIN_SECONDS * SAMPLE_RATE)
        sightings = [
            (r.start_sample, True, r) for r in report.receptions if r.start_sample is not None
        ]
        sightings += [
            (lost.start_sample, False, lost)
            for lost in report.undecoded
            if listed(when(lost.start_sample), lost.frequency_hz)
        ]
        problems = []
        for start, decoded, found in sorted(sightings, key=lambda s: s[0]):
            hz = mfsk.FIRST_TONE_HZ + found.frequency_offset_hz if decoded else found.frequency_hz
            at = when(start)
            if any(alike(at, hz, t, f, tolerance) for t, f in self._kept):
                continue  # kept in an earlier pass
            if samples.size - (start + frame) < margin and not final:
                continue  # the margin after it is not heard yet: next pass
            self._kept.append((at, hz))  # even if it fails: it would fail again every pass
            try:
                piece, first = self._piece(samples, modem, start, frame, margin)
                self.store.save(piece, self._record(modem, found, decoded, hz, at, first))
            except (OSError, ValueError) as error:
                problems.append(f"a reception could not be kept: {error}")
        return problems

    @staticmethod
    def _piece(samples, modem, start: int, frame: int, margin: int):
        step = modem.search_step_samples()
        begin = max(0, (start - margin) // step * step)
        end = min(samples.size, start + frame + margin)
        return np.clip(samples[begin:end], -1.0, 1.0), start - begin

    @staticmethod
    def _record(modem, found, decoded: bool, hz: float, at: float, first: int) -> dict:
        record = {
            "preset": modem.preset,
            "modem": f"{type(modem).__module__}:{type(modem).__qualname__}",
            "frame_samples": modem.frame_samples(),
            "kind": "frame" if decoded else "lost",
            "decoded": decoded,
            "frequency_hz": hz,
            "sync_score": found.sync_score,
            "started_at": at,
            "frame_start_sample": first,
        }
        if decoded:
            fragment = Fragment.unpack(found.message)
            record.update(
                snr_db=found.snr_db,
                frequency_offset_hz=found.frequency_offset_hz,
                body_hex=found.message.hex(),
                msg_id=fragment.msg_id if fragment else None,
                index=fragment.index if fragment else None,
                total=fragment.total if fragment else None,
            )
        return record

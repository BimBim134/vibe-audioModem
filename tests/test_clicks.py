"""A click is not a Signal: a short loud sound in a quiet room must not look like a Preamble.

The room was heard with a real sound card: almost silence, with now and then a click (a key, a
mouse, a loudspeaker popping). A click holds energy at every frequency for a few milliseconds, so
against the very low noise around it, it can look like a strong match of the Preamble.
"""

import numpy as np
import pytest

from vibemodem.core import mfsk
from vibemodem.core.presets import PRESETS
from vibemodem.core.turbo_modem import TurboModem

FS = mfsk.SAMPLE_RATE


def quiet_room(seconds, clicks, amplitude, noise=0.002, seed=0):
    """Faint noise and, at the given times, clicks: 4 ms of noise dying away in 1 ms."""
    rng = np.random.default_rng(seed)
    room = rng.normal(0, noise, int(seconds * FS))
    length = int(0.004 * FS)
    for at in clicks:
        start = int(at * FS)
        decay = np.exp(-np.arange(length) / (0.001 * FS))
        room[start : start + length] += amplitude * rng.normal(0, 1, length) * decay
    return np.clip(room, -1, 1)


@pytest.fixture(scope="module", params=sorted(PRESETS))
def modem(request):
    return TurboModem(preset=request.param)


@pytest.mark.parametrize("clicks", [[3.7], [3.7, 5.7, 10.2], list(np.arange(3, 20, 0.35))])
def test_clicks_in_a_quiet_room_are_neither_a_signal_lost_nor_a_signal_arriving(modem, clicks):
    report = modem.demodulate_report(quiet_room(24, clicks, amplitude=0.2))
    assert report.receptions == [] and report.undecoded == [] and report.arriving == []


def test_a_message_is_still_read_in_a_room_with_clicks(modem):
    room = quiet_room(modem.frame_samples() / FS + 12, [3.0, 5.2, 9.0], amplitude=0.2)
    sound = modem.modulate(b"through the clicks", modem.preset)
    start = 4 * FS
    room[start : start + sound.size] += sound * 0.3
    report = modem.demodulate_report(np.clip(room, -1, 1))
    assert [r.message for r in report.receptions] == [b"through the clicks"]

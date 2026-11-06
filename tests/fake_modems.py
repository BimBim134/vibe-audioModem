"""Stand-in candidate modems: they implement the interface and nothing else."""

import numpy as np

from vibemodem.core.modem import Reception


class _RemembersLastMessage:
    """Carries nothing on the air: it just remembers what it was asked to send."""

    def modulate(self, message, preset):
        self.sent = message
        return np.full(480, 0.5)


class PerfectModem(_RemembersLastMessage):
    def demodulate(self, samples):
        return [Reception(message=self.sent)]


class DeafModem(_RemembersLastMessage):
    def demodulate(self, samples):
        return []


class WrongModem(_RemembersLastMessage):
    def demodulate(self, samples):
        return [Reception(message=bytes(b ^ 0xFF for b in self.sent))]


class NoisyModem(_RemembersLastMessage):
    """Returns the right Message but also a wrong one."""

    def demodulate(self, samples):
        wrong = bytes(b ^ 0xFF for b in self.sent)
        return [Reception(message=wrong), Reception(message=self.sent)]


class RecordingModem(PerfectModem):
    """Keeps what the bench handed it, to check what a seed controls."""

    def __init__(self):
        self.messages = []
        self.heard = []

    def modulate(self, message, preset):
        self.messages.append(message)
        return super().modulate(message, preset)

    def demodulate(self, samples):
        self.heard.append(samples.copy())
        return super().demodulate(samples)


class NeedsArguments:
    def __init__(self, required):
        self.required = required


class ToneModem(RecordingModem):
    """Sends one second of a 1,000 Hz tone, so the bench's frequency shift can be measured."""

    def modulate(self, message, preset):
        self.messages.append(message)
        self.sent = message
        return 0.5 * np.sin(2 * np.pi * 1000 * np.arange(48_000) / 48_000)


class UncodedBits:
    """A 'code' that adds nothing: coded bits are the information bits, decided by their sign."""

    def __init__(self, info_bits=1):
        self.info_bits = self.coded_bits = info_bits
        self.parameters = {"kind": "uncoded"}

    def encode(self, bits):
        return np.asarray(bits, dtype=np.uint8)

    def decode(self, soft):
        return (np.asarray(soft) < 0).astype(np.uint8)


class OptionModem(PerfectModem):
    """A modem with settings, to check that the bench passes them on and records them."""

    def __init__(self, tones=8, interleave=False):
        self.tones = tones
        self.interleave = interleave

    @property
    def parameters(self):
        return {"tones": self.tones, "interleave": self.interleave}


class ComboModem(PerfectModem):
    """A modem whose Transmission is `tones` tones 10 Hz apart, to test sweeps of the settings."""

    def __init__(self, tones=8, symbol_ms=80.0, interleave=False):
        self.tones = tones
        self.symbol_ms = symbol_ms
        self.interleave = interleave

    @property
    def parameters(self):
        return {"tones": self.tones, "symbol_ms": self.symbol_ms, "interleave": self.interleave}

    def modulate(self, message, preset):
        super().modulate(message, preset)
        time = np.arange(2 * 48_000) / 48_000
        tones = sum(np.sin(2 * np.pi * (1000 + 10 * tone) * time) for tone in range(self.tones))
        return 0.1 * tones

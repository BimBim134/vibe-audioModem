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

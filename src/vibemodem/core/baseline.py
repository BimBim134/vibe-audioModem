"""The baseline modem: the reference every later candidate is measured against.

8-FSK in about 100 Hz with a rate-1/2 convolutional code of constraint length 7 (see
`coded_mfsk` for the rest).
"""

from vibemodem.core import frame
from vibemodem.core.coded_mfsk import CodedMfskModem
from vibemodem.core.coded_modem import MAX_RECORDING_SECONDS, NOISE_BANDWIDTH_HZ, SAMPLE_RATE
from vibemodem.core.convolutional import ConvolutionalCode
from vibemodem.core.frame import MESSAGE_CAPACITY

__all__ = [
    "MAX_RECORDING_SECONDS",
    "MESSAGE_CAPACITY",
    "NOISE_BANDWIDTH_HZ",
    "SAMPLE_RATE",
    "BaselineModem",
]


class BaselineModem(CodedMfskModem):
    def __init__(self, **options):
        super().__init__(ConvolutionalCode(frame.FRAME_BITS), **options)

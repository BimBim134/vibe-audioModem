"""The baseline modem with its convolutional code replaced by an LDPC code of the same rate.

Everything else is the baseline's, so the difference in Success threshold is the code's.
"""

from vibemodem.core import frame
from vibemodem.core.coded_mfsk import CodedMfskModem
from vibemodem.core.ldpc import LdpcCode


class LdpcModem(CodedMfskModem):
    def __init__(self):
        super().__init__(LdpcCode(info_bits=frame.FRAME_BITS, coded_bits=2 * frame.FRAME_BITS))

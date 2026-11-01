"""The baseline modem with its code replaced by the long-constraint convolutional code.

Everything else is the baseline's, so the difference in Success threshold is the code's. The
code sends 462 coded bits (its tail is 31 bits long), so a Transmission lasts 16 symbols
(1.3 s, 9%) longer than the others.
"""

from vibemodem.core import frame
from vibemodem.core.coded_mfsk import CodedMfskModem
from vibemodem.core.long_convolutional import LongConvolutionalCode


class LongConvolutionalModem(CodedMfskModem):
    def __init__(self):
        super().__init__(LongConvolutionalCode(info_bits=frame.FRAME_BITS))

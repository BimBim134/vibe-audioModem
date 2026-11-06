"""The baseline modem with its convolutional code replaced by a turbo code of the same rate.

Everything else is the baseline's, so the difference in Success threshold is the code's. The
turbo code sends 412 coded bits, as the convolutional code does, so a Transmission lasts as long.
"""

from vibemodem.core import frame
from vibemodem.core.coded_mfsk import CodedMfskModem
from vibemodem.core.turbo import TurboCode


class TurboModem(CodedMfskModem):
    def __init__(self, **options):
        super().__init__(TurboCode(info_bits=frame.FRAME_BITS), **options)

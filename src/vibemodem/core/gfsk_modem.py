"""The GFSK modem with the turbo code, the v1 default code, for the bench to measure."""

from vibemodem.core import frame
from vibemodem.core.coded_gfsk import CodedGfskModem
from vibemodem.core.turbo import TurboCode


class GfskModem(CodedGfskModem):
    def __init__(self, **options):
        super().__init__(TurboCode(info_bits=frame.FRAME_BITS), **options)

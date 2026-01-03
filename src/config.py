"""
some configuration class to keep things tidy
"""

from dataclasses import dataclass

from gnuradio import digital
from reedsolo import RSCodec

# PACKET CONFIG


@dataclass
class PacketConfig:
    """packet configuration"""

    total_packets_len: int
    preamble_packets: int
    postamble_packets: int
    error_correction_len: int

    @property
    def data_chunck_len(self) -> int:
        """amount of data in each packet. 1 bytes is put aside for packet_len

        Returns:
            int: len of usefull data in each packet
        """
        return self.total_packets_len - self.error_correction_len - 1
    
    @property
    def rsc_codec(self)->RSCodec:
        """reed solomon codec"""
        return RSCodec(self.error_correction_len)


DEFAULT_PACKET_CONFIG = PacketConfig(
    total_packets_len=255,
    preamble_packets=3,
    postamble_packets=1, # serve as EOF flag
    error_correction_len=12,
)


# SIGNAL CONFIG


@dataclass
class SignalConfig:
    """signal configuration"""
    samp_rate: int

    carrier_freq: float
    baudrate: int

    @property
    def sps(self) -> int:
        """sample per symbol

        Returns:
            int: number of sample per symbol
        """
        return int(self.samp_rate / self.baudrate)


DEFAULT_SIGNAL_CONFIG = SignalConfig(samp_rate=48000, carrier_freq=2500, baudrate=500)


# CONSTELLATION CONFIG

DEFAULT_DQPSK_CONST = digital.constellation_dqpsk()

DEFAULT_8PSK_CONST = digital.constellation_8psk_natural()


if __name__ == "__main__":
    pass

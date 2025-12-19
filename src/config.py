"""
some configuration class to keep things tidy
"""

from dataclasses import dataclass


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


DEFAULT_PACKET_CONFIG = PacketConfig(
    total_packets_len=128,
    preamble_packets=3,
    postamble_packets=0,
    error_correction_len=12,
)


@dataclass
class SignalConfig:
    samp_rate: int

    carrier_freq: float
    baudrate: int

    @property
    def sps(self) -> int:
        return int(self.samp_rate / self.baudrate)


DEFAULT_SIGNAL_CONFIG = SignalConfig(samp_rate=48000, carrier_freq=2500, baudrate=500)

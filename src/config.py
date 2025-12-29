"""
some configuration class to keep things tidy
"""

from dataclasses import dataclass

from gnuradio import digital

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


DEFAULT_PACKET_CONFIG = PacketConfig(
    total_packets_len=128,
    preamble_packets=3,
    postamble_packets=0,
    error_correction_len=12,
)


# SIGNAL CONFIG


@dataclass
class SignalConfig:
    samp_rate: int

    carrier_freq: float
    baudrate: int

    @property
    def sps(self) -> int:
        return int(self.samp_rate / self.baudrate)


DEFAULT_SIGNAL_CONFIG = SignalConfig(samp_rate=48000, carrier_freq=2500, baudrate=500)


# CONSTELLATION CONFIG

DEFAULT_BSK_CONST = digital.bpsk_constellation()

DEFAULT_DQPSK_CONST = digital.psk_constellation(
    m=4, mod_code=digital.mod_codes.GRAY_CODE, differential=True
)

DEFAULT_8PSK_CONST = digital.psk_constellation(
    m=8, mod_code=digital.mod_codes.GRAY_CODE, differential=True
)

DEFAULT_QAM_CONST = digital.qam_constellation(
    constellation_points=16,
    differential=True,
    mod_code=digital.mod_codes.GRAY_CODE,
    large_ampls_to_corners=False,
)


if __name__ == "__main__":
    pass

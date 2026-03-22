"""
some configuration class to keep things tidy
"""

import logging
from dataclasses import dataclass

from gnuradio import digital
from reedsolo import RSCodec
import numpy as np


def setup_logging(level=logging.DEBUG):
    """
    Configure logging for the entire application.
    This can be called safely multiple times, but the first call will set the configuration.
    """
    logging.basicConfig(
        format="%(asctime)s: %(processName)s: %(message)s",
        level=level,
    )
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)


# Automatically setup logging when config is imported
setup_logging()


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
    def rsc_codec(self) -> RSCodec:
        """reed solomon codec"""
        return RSCodec(self.error_correction_len)


@dataclass
class SignalConfig:
    """signal configuration"""

    samp_rate: int

    carrier_freq: float
    beeper_duration: float
    baudrate: int
    modulation_preset: str = "MEDIUM"

    @property
    def constellation(self):
        return MODULATION_PRESETS.get(self.modulation_preset, MODULATION_PRESETS["MEDIUM"]).constellation

    @property
    def sps(self) -> int:
        """sample per symbol"""
        return int(self.samp_rate / self.baudrate)

    @property
    def beeper_nb_sample(self) -> int:
        """beeper number of audio sample"""
        return int(self.samp_rate * self.beeper_duration)

    @property
    def nyquist_freq(self) -> float:
        """nyquist frequency"""
        return self.samp_rate / 2


@dataclass
class PortsConfig:
    """ports configuration"""

    audio_port: int

    fft_port: int
    fft_size: int

    raw_packets_port: int
    constellation_port: int
    constellation_ports_count: int

    messages_port: int
    config_port: int
    peak_detector_system_port: int

    @property
    def half_fft_size(self) -> int:
        """half of self.fft_size"""
        return self.fft_size // 2


DEFAULT_PACKET_CONFIG = PacketConfig(
    total_packets_len=255,
    preamble_packets=1,
    postamble_packets=1,  # serve as EOF flag
    error_correction_len=32,
)

DEFAULT_BPSK_CONST = digital.constellation_bpsk()
DEFAULT_DQPSK_CONST = digital.constellation_dqpsk()
DEFAULT_8PSK_CONST = digital.constellation_8psk_natural()

@dataclass
class ModulationPreset:
    name: str
    baudrate: int
    constellation: digital.constellation

MODULATION_PRESETS = {
    "SLOW": ModulationPreset("SLOW", 70, DEFAULT_BPSK_CONST),
    "MEDIUM": ModulationPreset("MEDIUM", 200, DEFAULT_DQPSK_CONST),
    "FAST": ModulationPreset("FAST", 500, DEFAULT_8PSK_CONST),
}

DEFAULT_SIGNAL_CONFIG = SignalConfig(
    samp_rate=48000, beeper_duration=3.0, carrier_freq=2500, baudrate=200, modulation_preset="MEDIUM"
)



DEFAULT_PORTS_CONFIG = PortsConfig(
    audio_port=5555,
    fft_port=5556,
    fft_size=4096,
    raw_packets_port=5557,
    messages_port=5558,
    config_port=5559,
    peak_detector_system_port=5560,
    constellation_port=5563,
    constellation_ports_count=10,
)


if __name__ == "__main__":
    pass

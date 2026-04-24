"""
some configuration class to keep things tidy
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from gnuradio import digital
from reedsolo import RSCodec
import numpy as np


def setup_logging(
    level=logging.DEBUG,
    log_file: str = "audiomodem.log",
    console: bool = False
):
    """
    Configure logging for the entire application.
    Logs to file by default. Can optionally enable console output.
    
    Args:
        level: Log level (default: DEBUG)
        log_file: Path to log file (default: "audiomodem.log")
        console: If True, also output to stdout (default: False)
    """
    handlers = [logging.FileHandler(log_file, mode="a")]
    if console:
        handlers.append(logging.StreamHandler())
    
    logging.basicConfig(
        format="%(asctime)s: %(processName)s: %(levelname)s: %(message)s",
        level=level,
        handlers=handlers,
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("audio_portaudio_source").setLevel(logging.INFO)


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
    constellation_name: Optional[str] = field(default=None)

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

    messages_port: int
    config_port: int
    peak_detector_system_port: int

    @property
    def half_fft_size(self) -> int:
        """half of self.fft_size"""
        return self.fft_size // 2


DEFAULT_PACKET_CONFIG = PacketConfig(
    total_packets_len=48,
    preamble_packets=1,
    postamble_packets=1,
    error_correction_len=16,
)

BPSK_CONST = digital.constellation_bpsk()
DQPSK_CONST = digital.constellation_dqpsk()
PSK8_CONST = digital.constellation_8psk_natural()

CONSTELLATION_MAP = {
    "default":BPSK_CONST,
    "bpsk": BPSK_CONST,
    "qpsk": DQPSK_CONST,
    "8psk": PSK8_CONST,
}

DEFAULT_SIGNAL_CONFIG = SignalConfig(
    samp_rate=48000, beeper_duration=3.0, carrier_freq=2500, baudrate=200
)


DEFAULT_PORTS_CONFIG = PortsConfig(
    audio_port=5555,
    fft_port=5556,
    fft_size=4096,
    raw_packets_port=5557,
    messages_port=5558,
    config_port=5559,
    peak_detector_system_port=5560,
)


if __name__ == "__main__":
    pass

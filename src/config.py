"""
some configuration class to keep things tidy
"""
import logging
from dataclasses import dataclass

from gnuradio import digital
from reedsolo import RSCodec
import numpy as np

logging.basicConfig(format="%(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)


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
    

@dataclass
class SignalConfig:
    """signal configuration"""
    samp_rate: int

    carrier_freq: float
    beeper_duration: float
    baudrate: int

    @property
    def sps(self) -> int:
        """sample per symbol"""
        return int(self.samp_rate / self.baudrate)
    
    @property
    def beeper_nb_sample(self) -> int:
        """beeper number of audio sample"""
        return int(self.samp_rate*self.beeper_duration)
    
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

    raw_packets_port:int

    @property
    def half_fft_size(self)->int:
        """half of self.fft_size"""
        return self.fft_size // 2

    @property
    def half_spectrum(self)->slice:
        """slice object to get only half of the spectrum"""
        return slice(self.fft_size, None, None)
    
    def frequency_array(self, sig:SignalConfig)->np.ndarray:
        """get frequency array for x-axis of fft display

        Args:
            Sig (SignalConfig): signal configuration

        Returns:
            np.ndarray: frequency array
        """
        return np.linspace(0, sig.nyquist_freq, self.fft_size // 2)


DEFAULT_PACKET_CONFIG = PacketConfig(
    total_packets_len=255,
    preamble_packets=3,
    postamble_packets=1, # serve as EOF flag
    error_correction_len=12,
)

DEFAULT_SIGNAL_CONFIG = SignalConfig(
    samp_rate=48000, beeper_duration=0.5, carrier_freq=2500, baudrate=500
)

DEFAULT_DQPSK_CONST = digital.constellation_dqpsk()
DEFAULT_8PSK_CONST = digital.constellation_8psk_natural()

DEFAULT_PORTS_CONFIG = PortsConfig(audio_port=5555, fft_port=5556, fft_size=4096, raw_packets_port=5557)


if __name__ == "__main__":
    pass

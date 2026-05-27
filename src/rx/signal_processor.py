import logging
from collections import deque
import numpy as np
from scipy.signal import find_peaks, medfilt

logger = logging.getLogger(__name__)

class SignalProcessor:
    """Handles FFT processing and peak detection logic."""

    def __init__(
        self,
        fft_size,
        freq_resolution,
        baudrate,
        buffer_size=10,
        min_prominence=2.0,
        enable_smoothing=True,
        enable_noise_floor=True,
        persistence_hits=3,
        persistence_window=5
    ):
        self.fft_size = fft_size
        self.freq_resolution = freq_resolution
        self.baudrate = baudrate
        self.min_prominence = min_prominence
        
        # Buffers and state
        self.fft_buffer = deque(maxlen=buffer_size)
        
        # Feature flags
        self.enable_smoothing = enable_smoothing
        self.enable_noise_floor = enable_noise_floor
        
        # Persistence (hit counter per frequency bin or region)
        # For simplicity, we'll track persistence of candidate peaks
        self.persistence_hits = persistence_hits
        self.persistence_window = persistence_window
        self.candidate_peaks = {} # freq_bin -> [hit_count, age]

    def process_frame(self, real_spectrum):
        """Process a single FFT frame and return detected frequencies."""
        self.fft_buffer.append(real_spectrum)
        
        # 1. Averaging
        avg_spectrum = np.mean(self.fft_buffer, axis=0)
        
        processed_spectrum = avg_spectrum

        # 2. Smoothing (Optional)
        if self.enable_smoothing:
            # Simple moving average for smoothing
            window_size = 5
            processed_spectrum = np.convolve(processed_spectrum, np.ones(window_size)/window_size, mode='same')

        # 3. Noise Floor Estimation (Optional)
        detection_spectrum = processed_spectrum
        if self.enable_noise_floor:
            # Median filter to estimate background noise floor
            # kernel_size should be larger than the expected signal bandwidth
            kernel_size = int(self.baudrate * 2 / self.freq_resolution)
            if kernel_size % 2 == 0:
                kernel_size += 1
            
            noise_floor = medfilt(processed_spectrum, kernel_size=kernel_size)
            # Avoid division by zero
            noise_floor = np.maximum(noise_floor, 1e-6)
            detection_spectrum = processed_spectrum / noise_floor

        # 4. Peak Detection
        # distance: ensure peaks are separated by at least half the baudrate
        distance = max(1, int(self.baudrate / (2 * self.freq_resolution)))
        
        # We want to detect peaks that are significantly above the local noise
        if self.enable_noise_floor:
            # detection_spectrum is already normalized by noise floor
            # min_prominence is the SNR ratio threshold (e.g. 3.0 = 10dB)
            prominence = self.min_prominence
            # Also require a minimum absolute level to avoid picking up noise in silence
            min_height = 1.0 # SNR must be at least 1.0 (obviously)
        else:
            # Prominence relative to the mean of the spectrum
            avg_val = np.mean(avg_spectrum)
            prominence = self.min_prominence * avg_val
            min_height = prominence # Peak must be at least this high

        # Ensure min_height and prominence are at least a small epsilon to avoid float issues
        min_height = max(min_height, 1e-6)
        prominence = max(prominence, 1e-7)

        peaks, properties = find_peaks(
            detection_spectrum,
            distance=distance,
            prominence=prominence,
            height=min_height
        )

        detected_freqs = peaks * self.freq_resolution
        
        # 5. Persistence (Optional)
        if self.persistence_hits > 1:
            return self._apply_persistence(peaks)
        
        return detected_freqs.tolist()

    def _apply_persistence(self, current_peaks):
        """
        Apply a hit-counter based persistence to detected peaks.
        - Increments hit count for regions where a peak is found.
        - Decrements hit count for regions where no peak is found.
        - Only returns peaks that have reached self.persistence_hits.
        """
        # Tolerance for frequency drift/jitter (in bins)
        tolerance = max(1, int(self.baudrate / (4 * self.freq_resolution)))
        
        # 1. Update hit counts for existing candidates
        updated_candidates = {}
        matched_current_peaks = set()

        for cand_bin, hits in self.candidate_peaks.items():
            # Check if any current peak matches this candidate
            match = None
            for cp_bin in current_peaks:
                if abs(cp_bin - cand_bin) <= tolerance:
                    match = cp_bin
                    break
            
            if match is not None:
                # Increment hits, capped at persistence_window (max persistence memory)
                updated_candidates[match] = min(hits + 1, self.persistence_window)
                matched_current_peaks.add(match)
            else:
                # Decrement hits
                if hits - 1 > 0:
                    updated_candidates[cand_bin] = hits - 1

        # 2. Add new candidates for unmatched current peaks
        for cp_bin in current_peaks:
            if cp_bin not in matched_current_peaks:
                updated_candidates[cp_bin] = 1

        self.candidate_peaks = updated_candidates

        # 3. Filter confirmed peaks
        confirmed_peaks = []
        for cp_bin in current_peaks:
            # A peak is confirmed if its bin (or a very close one) has enough hits
            for cand_bin, hits in self.candidate_peaks.items():
                if abs(cp_bin - cand_bin) <= tolerance and hits >= self.persistence_hits:
                    confirmed_peaks.append(cp_bin * self.freq_resolution)
                    break
        
        return confirmed_peaks

    def set_options(self, **kwargs):
        """Update processing options dynamically."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"SignalProcessor option '{key}' set to {value}")

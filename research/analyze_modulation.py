import numpy as np
import scipy.io.wavfile as wav
import matplotlib.pyplot as plt
from pathlib import Path

def analyze_modulation(file_path):
    print(f"Analyzing modulation in {file_path}...")
    sample_rate, data = wav.read(file_path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    
    # Parameters
    beeper_end_s = 3.0
    beeper_end_idx = int(sample_rate * beeper_end_s)
    
    if len(data) <= beeper_end_idx:
        print("File too short.")
        return

    signal_part = data[beeper_end_idx:]
    
    # We'll analyze in windows
    window_sec = 0.1
    window_size = int(sample_rate * window_sec)
    
    times = []
    bandwidths = []
    amplitudes = []
    
    print("\nScanning signal part for modulation changes...")
    
    for i in range(0, len(signal_part) - window_size, window_size):
        window = signal_part[i:i+window_size]
        t = beeper_end_s + i / sample_rate
        
        # FFT to see bandwidth
        fft = np.abs(np.fft.rfft(window))
        freqs = np.fft.rfftfreq(len(window), 1/sample_rate)
        
        # Find peak freq (should be around 2500Hz)
        peak_idx = np.argmax(fft)
        peak_freq = freqs[peak_idx]
        peak_val = fft[peak_idx]
        
        # Measure bandwidth: how many bins around the peak are significant?
        # We'll use a threshold of 10dB below peak
        threshold = peak_val * 0.316 # -10dB
        significant_indices = np.where(fft > threshold)[0]
        if len(significant_indices) > 0:
            bw = freqs[significant_indices[-1]] - freqs[significant_indices[0]]
        else:
            bw = 0
            
        times.append(t)
        bandwidths.append(bw)
        amplitudes.append(np.max(np.abs(window)))
        
    # Find where bandwidth drops (modulation stops)
    # Beacuse 500 baud DQPSK should have BW ~600-700Hz.
    # Unmodulated carrier will have BW ~ 1/window_sec = 10Hz.
    modulation_threshold_bw = 100 # Hz
    
    is_modulated = np.array(bandwidths) > modulation_threshold_bw
    
    if not np.all(is_modulated):
        first_unmodulated = np.where(~is_modulated)[0]
        if len(first_unmodulated) > 0:
            # Check if it STAYS unmodulated
            for idx in first_unmodulated:
                # If there's still significant amplitude but low BW, it's an unmodulated carrier
                if amplitudes[idx] > 0.1:
                    print(f"ALERT: Modulation seems to STOP at t={times[idx]:.3f}s (Amplitude: {amplitudes[idx]:.4f}, BW: {bandwidths[idx]:.1f}Hz)")
                    break
            else:
                 print("No unmodulated carrier with significant amplitude found.")
        else:
            print("Signal stays modulated until the end.")
    else:
        print("Signal stays modulated until the end.")

    # Find where amplitude drops (signal ends)
    amplitude_threshold = 0.05
    is_active = np.array(amplitudes) > amplitude_threshold
    if not np.all(is_active):
        last_active = np.where(is_active)[0][-1]
        print(f"Signal activity ends at t={times[last_active]:.3f}s")

if __name__ == "__main__":
    analyze_modulation("research/test.wav")

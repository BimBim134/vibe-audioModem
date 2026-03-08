import numpy as np
import scipy.io.wavfile as wav
import matplotlib.pyplot as plt
from pathlib import Path

def analyze_wav(file_path):
    print(f"Analyzing {file_path}...")
    sample_rate, data = wav.read(file_path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    
    duration = len(data) / sample_rate
    print(f"Sample Rate: {sample_rate} Hz")
    print(f"Duration: {duration:.3f} s")
    print(f"Total Samples: {len(data)}")

    # The beeper is supposed to be 3.0 seconds (from DEFAULT_SIGNAL_CONFIG)
    beeper_samples = int(sample_rate * 3.0)
    
    if len(data) > beeper_samples:
        beeper_part = data[:beeper_samples]
        signal_part = data[beeper_samples:]
        
        beeper_peak = np.max(np.abs(beeper_part))
        beeper_rms = np.sqrt(np.mean(beeper_part**2))
        
        signal_peak = np.max(np.abs(signal_part))
        signal_rms = np.sqrt(np.mean(signal_part**2))
        
        print(f"\nBeeper Part (0-3s):")
        print(f"  Peak: {beeper_peak:.4f}")
        print(f"  RMS:  {beeper_rms:.4f}")
        
        print(f"\nSignal Part (3s-end):")
        print(f"  Peak: {signal_peak:.4f}")
        print(f"  RMS:  {signal_rms:.4f}")
        
        # Look for the point where signal "stops"
        # We can look for where the energy drops significantly
        window_size = 1000
        energy = np.array([np.mean(signal_part[i:i+window_size]**2) for i in range(0, len(signal_part), window_size)])
        
        # Find where energy drops below a threshold (e.g., 10% of max signal energy)
        threshold = np.max(energy) * 0.1
        active_indices = np.where(energy > threshold)[0]
        if len(active_indices) > 0:
            last_active_idx = active_indices[-1] * window_size
            active_duration = last_active_idx / sample_rate
            print(f"\nSignal activity seems to end at ~{3.0 + active_duration:.3f} s")
        else:
            print("\nNo signal activity detected after beeper.")

    else:
        print("\nFile is too short to contain full beeper and signal.")

    # Generate Spectrogram
    plt.figure(figsize=(12, 6))
    plt.specgram(data, Fs=sample_rate, NFFT=1024, noverlap=512)
    plt.title(f"Spectrogram of {Path(file_path).name}")
    plt.xlabel("Time (s)")
    plt.ylabel("Frequency (Hz)")
    plt.colorbar(label="Intensity (dB)")
    plt.ylim(0, 5000) # Carrier is at 2500Hz
    plt.savefig("research/test_spectrogram.png")
    print(f"\nSpectrogram saved to research/test_spectrogram.png")

if __name__ == "__main__":
    analyze_wav("research/test.wav")

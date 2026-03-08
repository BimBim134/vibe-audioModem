import numpy as np
import scipy.io.wavfile as wav
import matplotlib.pyplot as plt

def analyze_gap(file_path, target_time=7.522, window=0.2):
    print(f"Analyzing gap in {file_path} around {target_time}s...")
    sample_rate, data = wav.read(file_path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    
    start_idx = int((target_time - window/2) * sample_rate)
    end_idx = int((target_time + window/2) * sample_rate)
    
    segment = data[start_idx:end_idx]
    time = np.linspace(target_time - window/2, target_time + window/2, len(segment))
    
    # Plot waveform
    plt.figure(figsize=(15, 8))
    plt.subplot(2, 1, 1)
    plt.plot(time, segment)
    plt.axvline(x=target_time, color='r', linestyle='--', label='Target Timeline')
    plt.title(f"Waveform around {target_time}s")
    plt.ylabel("Amplitude")
    plt.legend()

    # Plot spectrogram with high resolution
    plt.subplot(2, 1, 2)
    plt.specgram(segment, Fs=sample_rate, NFFT=256, noverlap=200)
    plt.title("Spectrogram (High Resolution)")
    plt.ylabel("Frequency (Hz)")
    plt.xlabel("Time (s relative to 0 in plot)")
    plt.ylim(2000, 3000) # Carrier at 2500Hz
    
    plt.savefig("research/gap_zoom.png")
    print("Saved zoom plot to research/gap_zoom.png")

    # Detect exactly when it stops and starts
    # Threshold for modulation: check variance in envelope or bandwidth
    # But simpler: check for constant amplitude sine wave vs alternating amplitude
    # Let's check the variance of the absolute value in small windows
    win_size = int(sample_rate * 0.005) # 5ms
    stds = []
    for i in range(0, len(segment)-win_size, 10):
        w = segment[i:i+win_size]
        stds.append(np.std(np.abs(w)))
    
    stds = np.array(stds)
    # A pure sine wave will have very low std of |w| (it's a constant DC after rectification)
    # Modulated signal has significant variation
    gap_indices = np.where(stds < np.mean(stds) * 0.2)[0]
    if len(gap_indices) > 0:
        gap_start = target_time - window/2 + (gap_indices[0] * 10) / sample_rate
        gap_end = target_time - window/2 + (gap_indices[-1] * 10) / sample_rate
        print(f"Detected gap from ~{gap_start:.4f}s to ~{gap_end:.4f}s (Duration: {gap_end-gap_start:.4f}s)")
    else:
        print("No definitive gap detected with variance threshold.")

if __name__ == "__main__":
    analyze_gap("research/test.wav")

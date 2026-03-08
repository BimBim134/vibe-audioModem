import numpy as np
import scipy.io.wavfile as wav

def scan_gaps(file_path):
    print(f"Scanning {file_path} for unmodulated carrier gaps...")
    sample_rate, data = wav.read(file_path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    
    # window size: 10ms
    win_len = int(sample_rate * 0.01)
    
    results = []
    # Scan from 4s to end (beeper ends at 3s)
    for i in range(int(3.1 * sample_rate), len(data) - win_len, win_len // 2):
        window = data[i:i+win_len]
        t = i / sample_rate
        
        fft = np.abs(np.fft.rfft(window))
        freqs = np.fft.rfftfreq(len(window), 1/sample_rate)
        
        # Power around 2500Hz
        carrier_idx = np.argmin(np.abs(freqs - 2500))
        # Total power in band 2200-2800
        band_mask = (freqs > 2100) & (freqs < 2900)
        band_power = np.sum(fft[band_mask])
        
        # Peak power at carrier
        peak_power = fft[carrier_idx]
        
        # Ratio: if very high, it's a spike (unmodulated)
        # In modulated signal, power is distributed.
        ratio = peak_power / (band_power + 1e-9)
        
        if ratio > 0.4: # A threshold for a spike
             results.append((t, ratio))

    # Group detected points into gaps
    if not results:
        print("No gaps detected.")
        return

    print("\nDetected spikes (potential unmodulated gaps):")
    current_start = results[0][0]
    last_t = results[0][0]
    for i in range(1, len(results)):
        t, r = results[i]
        if t - last_t > 0.02: # Gap in detections
            duration = last_t - current_start
            if duration > 0.01:
                print(f"Gap at ~{current_start:.4f}s, Duration: {duration:.4f}s")
            current_start = t
        last_t = t
    
    # Last one
    duration = last_t - current_start
    if duration > 0.01:
        print(f"Gap at ~{current_start:.4f}s, Duration: {duration:.4f}s")

if __name__ == "__main__":
    scan_gaps("research/test.wav")

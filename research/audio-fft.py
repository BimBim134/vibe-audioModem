import numpy as np
import matplotlib.pyplot as plt
import scipy.io.wavfile as wav
from matplotlib.widgets import Slider
import sys
import os

def plot_fft_interactive(filename):
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)

    print(f"Reading {filename}...")
    sample_rate, data = wav.read(filename)
    
    # If stereo, take the first channel
    if data.ndim > 1:
        print("Stereo detected, using first channel.")
        data = data[:, 0]

    # Pre-compute full FFT once for performance
    print("Computing full FFT...")
    full_fft = np.fft.fft(data)
    n_samples = len(data)
    
    # Create the figure and main axis
    fig, ax = plt.subplots(figsize=(12, 7))
    plt.subplots_adjust(bottom=0.25)  # Make room for sliders

    # Initial parameters
    init_decimation = 20
    init_smooth = 1000

    # Initialize plot lines with dummy data to establish the plot object
    line_raw, = ax.semilogy([0], [1e-6], alpha=0.3, label='Raw (Decimated)', color='tab:blue')
    line_smooth, = ax.semilogy([0], [1e-6], label='Smoothed', color='tab:orange')

    # Formatting
    ax.set_xticks(np.arange(0, 20001, 500))
    ax.set_xlim([0, 6000])
    ax.set_ylim([1e-6, 1.2])  # Standard normalized range for log scale
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Amplitude (Normalized)')
    ax.set_title(f'FFT Analysis: {os.path.basename(filename)}')
    ax.grid(True, which="both", ls="-", alpha=0.4)
    ax.legend()

    # Slider Axes
    ax_decim = plt.axes([0.25, 0.1, 0.55, 0.03])
    ax_smooth = plt.axes([0.25, 0.05, 0.55, 0.03])

    # Slider Widgets
    s_decim = Slider(ax_decim, 'Decimation', 1, 100, valinit=init_decimation, valstep=1)
    s_smooth = Slider(ax_smooth, 'Smoothing', 1, 5000, valinit=init_smooth, valstep=10)

    def update(val):
        decimation = int(s_decim.val)
        smooth_length = int(s_smooth.val)

        # 1. Truncate and decimate in frequency domain (averaging bins)
        # This matches the original script's logic
        truncated_len = (len(full_fft) // decimation) * decimation
        if truncated_len == 0:
            return

        # Reshape and average
        fft_decimated = full_fft[:truncated_len].reshape(-1, decimation).mean(axis=1)
        fft_abs = np.abs(fft_decimated)

        # 2. Normalize
        max_val = np.max(fft_abs)
        if max_val > 0:
            fft_abs /= max_val
        
        # 3. Smoothing
        actual_smooth = min(smooth_length, len(fft_abs))
        if actual_smooth > 1:
            fft_data_smooth = np.convolve(fft_abs, np.ones(actual_smooth)/actual_smooth, mode="same")
        else:
            fft_data_smooth = fft_abs

        # 4. Calculate Frequencies
        # Equivalent to original: freqs = np.fft.fftfreq(len(data), 1/(sample_rate*decimation))
        freq_step = (sample_rate * decimation) / n_samples
        freqs = np.arange(len(fft_abs)) * freq_step
        
        # Only plot the positive half
        idx = len(fft_abs) // 2
        
        # Update plot data
        line_raw.set_data(freqs[:idx], fft_abs[:idx])
        line_smooth.set_data(freqs[:idx], fft_data_smooth[:idx])
        
        # Update canvas
        fig.canvas.draw_idle()

    # Bind sliders to update function
    s_decim.on_changed(update)
    s_smooth.on_changed(update)

    # Initial call to populate the plot
    update(None)
    
    print("Close the window to exit.")
    plt.show()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python audio-fft.py <wav file>")
        sys.exit(1)
    
    plot_fft_interactive(sys.argv[1])

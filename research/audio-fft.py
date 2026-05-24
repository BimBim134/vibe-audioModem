import numpy as np
import matplotlib.pyplot as plt
import scipy.io.wavfile as wav
from matplotlib.widgets import Slider
import sys
import os

class InteractiveFFT:
    def __init__(self, filename):
        if not os.path.exists(filename):
            print(f"Error: File '{filename}' not found.")
            sys.exit(1)

        print(f"Reading {filename}...")
        self.sample_rate, data = wav.read(filename)
        
        # Handle multi-channel audio by taking the first channel
        if len(data.shape) > 1:
            print(f"Stereo/Multi-channel detected, using first channel.")
            self.data = data[:, 0]
        else:
            self.data = data
            
        print("Computing FFT...")
        self.full_fft = np.fft.fft(self.data)
        self.fft_size = len(self.data)
        
        # Initial parameters from original script
        self.decimation = 20
        self.smooth_length = 1000
        
        # Create figure and axis
        self.fig, self.ax = plt.subplots(figsize=(12, 8))
        plt.subplots_adjust(bottom=0.25) # Make room for sliders
        
        # Initialize plot lines
        self.line_raw, = self.ax.semilogy([], [], alpha=0.3, label='Raw (Decimated)', color='tab:blue')
        self.line_smooth, = self.ax.semilogy([], [], label='Smoothed', color='tab:orange')
        
        # Configure axis to match original style
        self.ax.set_xticks(np.arange(0, 20001, 500))
        self.ax.set_xlim([0, 6000])
        self.ax.set_xlabel('Frequency (Hz)')
        self.ax.set_ylabel('Amplitude')
        self.ax.set_title(f'FFT of {os.path.basename(filename)}')
        self.ax.grid(which="both")
        self.ax.legend()

        # Add Sliders for interactivity
        ax_decim = plt.axes([0.25, 0.1, 0.55, 0.03])
        self.slider_decim = Slider(ax_decim, 'Decimation', 1, 100, valinit=self.decimation, valstep=1)
        
        ax_smooth = plt.axes([0.25, 0.05, 0.55, 0.03])
        self.slider_smooth = Slider(ax_smooth, 'Smooth Length', 1, 5000, valinit=self.smooth_length, valstep=10)
        
        # Register update callbacks
        self.slider_decim.on_changed(self.update)
        self.slider_smooth.on_changed(self.update)
        
        # Initial plot update
        self.update(None)

    def update(self, val):
        decimation = int(self.slider_decim.val)
        smooth_length = int(self.slider_smooth.val)
        
        # 1. Decimate the FFT data (matching original logic)
        truncated_len = (len(self.full_fft) // decimation) * decimation
        fft_decimated = self.full_fft[:truncated_len].reshape(-1, decimation).mean(axis=1)
        
        # 2. Normalize power spectrum to log scale (matching original logic)
        fft_decimated /= np.max(np.abs(fft_decimated))
        
        # 3. Smoothing (matching original logic)
        actual_smooth = min(smooth_length, len(fft_decimated))
        if actual_smooth > 1:
            fft_data_smooth = np.convolve(fft_decimated, np.ones(actual_smooth)/actual_smooth, "same")
        else:
            fft_data_smooth = fft_decimated
            
        # 4. Compute frequency bins (matching original logic)
        freqs = np.fft.fftfreq(self.fft_size, 1/(self.sample_rate * decimation))
        idx = int(fft_decimated.size / 2)
        
        # Update plot data
        self.line_raw.set_data(freqs[:idx], np.abs(fft_decimated[:idx]))
        self.line_smooth.set_data(freqs[:idx], np.abs(fft_data_smooth[:idx]))
        
        # Redraw
        self.fig.canvas.draw_idle()

def main():
    if len(sys.argv) < 2:
        print("Usage: python audio-fft.py <wav file>")
        sys.exit(1)
    
    filename = sys.argv[1]
    app = InteractiveFFT(filename)
    plt.show()

if __name__ == '__main__':
    main()

# function to open a wav file and plt a fft
import numpy as np
import matplotlib.pyplot as plt
import scipy.io.wavfile as wav

import sys

def plot_fft(filename):
    # read the wav file
    sample_rate, data = wav.read(filename)
    # compute the fft
    fft_data = np.fft.fft(data)
    # power spectrum to log scale
    fft_data /= np.max(np.abs(fft_data))
    # compute the frequency bins
    freqs = np.fft.fftfreq(len(data), 1/sample_rate)
    # plot the fft
    idx = int(fft_data.size/2)
    plt.figure(layout="constrained")
    plt.semilogy(freqs[:idx], np.abs(fft_data[:idx]))
    plt.xlim([0,10000])
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Amplitude')
    plt.title('FFT of ' + filename)
    plt.xticks(np.arange(0, 20001, 500))
    plt.grid(which="both")
    plt.show()

if __name__ == '__main__':
    try:
        filename = sys.argv[1]
    except IndexError:
        print("Usage: python fft_data.py <wav file>")
        sys.exit(1)
    plot_fft(filename)
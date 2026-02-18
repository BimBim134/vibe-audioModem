import zmq
import numpy as np
from scipy.signal import find_peaks

import matplotlib.pyplot as plt

# --- Paramètres identiques à AUDIO_INTERFACE.py ---
ZMQ_PORT = 5555
FFT_SIZE = 2048
SAMPLE_RATE = 44100  # Défini dans ton self.samp_rate

# --- Initialisation ZMQ ---
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect(f"tcp://127.0.0.1:{ZMQ_PORT}")
socket.setsockopt(zmq.SUBSCRIBE, b"")  # S'abonner à tou
print(f"Connexion au flux FFT sur le port {ZMQ_PORT}...")

try:
    while True:
        msg = socket.recv()
        data = np.frombuffer(msg, dtype=np.float32)

        if data.size != FFT_SIZE:
            continue

        half_size = FFT_SIZE // 2
        real_spectrum = data[half_size:]

        peaks, properties = find_peaks(real_spectrum, height=0.5, distance=20)

        freq_resolution = SAMPLE_RATE / FFT_SIZE
        peak_freqs = peaks * freq_resolution
        peak_amps = properties['peak_heights']

        if len(peak_freqs) > 0:
            
            fig, ax = plt.subplots()
            ax.semilogy(np.linspace(0, SAMPLE_RATE/2, real_spectrum.size) ,real_spectrum)
            ax.scatter(peak_freqs, peak_amps)
            ax.set_xlabel("frequency (Hz)")
            ax.set_ylabel("magnitude (dB)")
            ax.grid()
            fig.savefig("test_spectrum.png")
            plt.close(fig)
            exit()

except KeyboardInterrupt:
    print("\nArrêt...")
    socket.close()
    context.term()
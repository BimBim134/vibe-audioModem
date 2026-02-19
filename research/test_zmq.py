import zmq
import numpy as np
from scipy.signal import find_peaks

import matplotlib.pyplot as plt

# --- Paramètres identiques à AUDIO_INTERFACE.py ---
ZMQ_PORT = 5556
FFT_SIZE = 2048
SAMPLE_RATE = 44100  # Défini dans ton self.samp_rate
SPECTROGRAM_LENGTH = 1000

# --- Initialisation ZMQ ---
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect(f"tcp://127.0.0.1:{ZMQ_PORT}")
socket.setsockopt(zmq.SUBSCRIBE, b"")  # S'abonner à tou
print(f"Connexion au flux FFT sur le port {ZMQ_PORT}...")

half_size = FFT_SIZE // 2
waterfall = np.zeros((SPECTROGRAM_LENGTH, half_size))
row=0
try:
    while row < SPECTROGRAM_LENGTH:
        msg = socket.recv()
        data = np.frombuffer(msg, dtype=np.float32)

        if data.size != FFT_SIZE:
            continue

        waterfall[row, :] = 10 * np.log10(data[half_size:])

        row += 1
        print("#", end='')

except KeyboardInterrupt:
    print("\nArrêt...")
    socket.close()
    context.term()


fig, ax = plt.subplots(layout="constrained")
ax.matshow(waterfall)
fig.savefig("spectrogram.png")
plt.close(fig)
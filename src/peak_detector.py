import time
import sys
import numpy as np
from gnuradio import gr, analog, audio, blocks, fft
from gnuradio.fft import window

import matplotlib.pyplot as plt

from config import SignalConfig
from config import DEFAULT_SIGNAL_CONFIG

class FrequencyListener(gr.top_block):
    def __init__(self, samp_rate:int, fft_size:int):
        gr.top_block.__init__(self, "Frequency Listener")
        
        # variables
        self.fft_size = fft_size
        self.samp_rate = samp_rate

        # blocks
        self.audio_src = audio.source(self.samp_rate, '', True)
        self.stream_to_vec = blocks.stream_to_vector(gr.sizeof_float, self.fft_size)
        self.window = window.blackmanharris(self.fft_size)
        self.fft = fft.fft_vfc(self.fft_size, True, self.window, True, 1)
        self.to_mag = blocks.complex_to_mag(self.fft_size)
        self.probe = blocks.probe_signal_vf(self.fft_size)

        # Connections
        self.connect(self.audio_src, self.stream_to_vec)
        self.connect(self.stream_to_vec, self.fft)
        self.connect(self.fft, self.to_mag)
        self.connect(self.to_mag, self.probe)


def wait_for_beep(sig:SignalConfig, fft_size = 2048, threshold=50.0):
    tb = FrequencyListener(sig.samp_rate, fft_size)
    tb.start()
    
    print(">>> En attente du BEEP...")
    
    found_freq = None
    
    try:
        while True:
            # 1. On récupère le spectre depuis la sonde (C'est instantané)
            spectrum = np.array(tb.probe.level())
            
            # 2. On cherche le max (pic d'énergie)
            peak_idx = np.argmax(spectrum)
            peak_val = spectrum[peak_idx]
            
            # 3. Vérification du seuil (Est-ce du bruit ou un signal ?)
            if peak_val > threshold:
                # Conversion index -> fréquence
                # freq = index * (Fs / FFT_size)
                freq = peak_idx * (sig.samp_rate / fft_size)
                
                # Petit filtre pour ignorer le DC (0Hz) et les très basses fréquences
                if freq > 400: 
                    print(f"!!! BEEP DÉTECTÉ à {freq:.1f} Hz (Amplitude: {peak_val:.1f}) !!!")
                    found_freq = freq
                    break
            
            # Petite pause pour ne pas manger 100% du CPU
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        pass
    finally:
        tb.stop()
        tb.wait()
        del tb # Libération de la carte son
        
    return found_freq

def live_spectrogram():
    samp_rate = 48000
    fft_size = 1024
    history_length = 100  # Nombre de lignes dans le spectrogramme (historique)

    # Initialisation GNU Radio
    tb = FrequencyListener(samp_rate, fft_size)
    tb.start()
    
    # Préparation des données
    # On crée une matrice vide pour l'historique (Temps x Fréquence)
    waterfall_data = np.zeros((history_length, fft_size // 2)) 

    # Configuration Matplotlib
    plt.ion() # Mode interactif
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # On affiche une image initiale
    # extent permet d'avoir les bons axes (Hz et Temps)
    im = ax.imshow(waterfall_data, aspect='auto', origin='lower', 
                   extent=[0, samp_rate/2, 0, history_length],
                   cmap='inferno', vmin=0, vmax=50) # Ajuste vmax selon le volume
    
    ax.set_xlabel("Fréquence (Hz)")
    ax.set_ylabel("Temps (passé)")
    ax.set_title("Spectrogramme Temps-Réel")
    plt.colorbar(im, label="Amplitude")

    print(">>> Affichage du spectrogramme. Ctrl+C pour arrêter.")
    
    try:
        while True:
            # 1. Récupérer les données de la sonde
            # La FFT retourne fft_size points. On ne garde que la moitié positive (0 -> Fs/2)
            raw_data = np.array(tb.probe.level())
            half_spectrum = raw_data[:fft_size // 2]
            
            # 2. Conversion en décibels (optionnel mais recommandé pour voir mieux)
            # On ajoute 1e-6 pour éviter log(0)
            db_spectrum = 20 * np.log10(half_spectrum + 1e-6)
            
            # 3. Mise à jour de la "Chute d'eau"
            # On décale tout vers le bas (roll) et on met la nouvelle ligne en haut
            waterfall_data = np.roll(waterfall_data, -1, axis=0)
            waterfall_data[-1, :] = db_spectrum
            
            # 4. Mise à jour du graphique
            im.set_data(waterfall_data)
            # Mise à jour de l'échelle de couleur dynamique (optionnel)
            im.set_clim(vmin=np.min(db_spectrum), vmax=np.max(db_spectrum) + 10)
            
            plt.draw()
            plt.pause(0.05) # Petite pause pour laisser l'interface respirer
            
    except KeyboardInterrupt:
        pass
    finally:
        tb.stop()
        tb.wait()
        print("Arrêt.")

if __name__ == "__main__":
    # freq = wait_for_beep(DEFAULT_SIGNAL_CONFIG)
    # if freq:
    #     print(f"Lancement de la démodulation sur {freq} Hz...")
    #     # Ici tu peux lancer ta classe Receiver avec la fréquence trouvée
    live_spectrogram()
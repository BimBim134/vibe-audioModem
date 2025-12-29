import sounddevice as sd

def lister_peripheriques():
    devices = sd.query_devices()
    
    print(f"{'ID':<4} {'Nom du Périphérique':<50} {'Entrées':<8} {'Sorties':<8}")
    print("-" * 70)
    
    for i, dev in enumerate(devices):
        inputs = dev['max_input_channels']
        outputs = dev['max_output_channels']
        name = dev['name']
        
        # On affiche tout, ou on filtre selon ce qui est actif
        if inputs > 0 or outputs > 0:
            print(f"{i:<4} {name:<50} {inputs:<8} {outputs:<8}")

if __name__ == "__main__":
    print("=== Liste des périphériques audio détectés ===\n")
    lister_peripheriques()
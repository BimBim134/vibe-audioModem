import zmq
import pmt # Module pour manipuler les types GNU Radio (optionnel si raw bytes)

def receveur_paquets():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # On se connecte à GNU Radio (qui agit comme serveur sur le port 5555)
    # Si le script est sur la même machine : localhost
    socket.connect("tcp://localhost:5555")
    
    # S'abonner à tous les messages (filtre vide)
    socket.setsockopt(zmq.SUBSCRIBE, b'')
    
    print("En attente de paquets depuis GNU Radio...")
    
    while True:
        try:
            # Réception du message
            # GNU Radio envoie souvent les PDUs sous forme de paire (meta, data)
            # Mais via ZMQ PUB Message Sink, on reçoit souvent les bytes bruts si configuré simplement.
            msg = socket.recv()
            
            # Si le message contient "pdu" à la fin (encapsulation PMT), 
            # il faut parfois décoder plus finement. 
            # Mais généralement, pour un PDU simple, vous recevez les bytes du payload.
            
            print(f"Paquet reçu ({len(msg)} octets) : {msg}")
            
            # Exemple : conversion en hexadécimal
            # print(msg.hex())
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Erreur : {e}")

if __name__ == "__main__":
    receveur_paquets()
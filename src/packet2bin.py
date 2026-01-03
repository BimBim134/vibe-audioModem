import zmq

from reedsolo import ReedSolomonError

from config import PacketConfig
from config import DEFAULT_PACKET_CONFIG

def decode_packet(raw_packet:bytes, pkt: PacketConfig):
    payload = raw_packet[10:]
    
    try:
        decoded_payload = pkt.rsc_codec.decode(payload)[0]
    except ReedSolomonError:
        return "data corrupted" 

    packet_len = decoded_payload[0]

    if packet_len == 0:
        return "preamble"
    elif packet_len == 255:
        return "postamble"
    else:
        return decoded_payload[1:packet_len+1]


def receveur_paquets(pkt:PacketConfig):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")

    socket.setsockopt(zmq.SUBSCRIBE, b'')
    
    print("En attente de paquets depuis GNU Radio...")
    
    while True:
        try:
            msg = socket.recv()
            print(decode_packet(msg, pkt))
            
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    receveur_paquets(DEFAULT_PACKET_CONFIG)
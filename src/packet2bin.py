import zmq
import logging

from reedsolo import ReedSolomonError

from config import PacketConfig
from config import DEFAULT_PACKET_CONFIG

logging.basicConfig(format="%(levelname)s: %(module)s: %(message)s", level=logging.DEBUG)


def decode_packet(raw_packet: bytes, pkt: PacketConfig):
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
        return decoded_payload[1 : packet_len + 1]


def receveur_paquets(pkt: PacketConfig):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")

    socket.setsockopt(zmq.SUBSCRIBE, b"")

    logging.info("waiting for packets on tcp://localhost:5555")

    while True:
        try:
            msg = socket.recv()
            logging.debug(decode_packet(msg, pkt))

        except KeyboardInterrupt:
            break


logging.info("packet2bin module loaded")

if __name__ == "__main__":
    receveur_paquets(DEFAULT_PACKET_CONFIG)

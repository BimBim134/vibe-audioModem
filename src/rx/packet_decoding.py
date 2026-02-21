import zmq
import logging

from reedsolo import ReedSolomonError

from src.config import PacketConfig
from src.config import DEFAULT_PACKET_CONFIG, DEFAULT_PORTS_CONFIG, PortsConfig

logging.basicConfig(format="%(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)


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


def listen_for_packets(
        pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
        ports: PortsConfig = DEFAULT_PORTS_CONFIG,
        stop_event = None
    ):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.bind(f"tcp://*:{ports.raw_packets_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.setsockopt(zmq.RCVTIMEO, 500)

    logging.info(f"Packet decoder listening for packets on port {ports.raw_packets_port}")

    try:
        while stop_event is None or not stop_event.is_set():
            try:
                msg = socket.recv()
                logging.debug("Received packet: %s", decode_packet(msg, pkt))
            except zmq.Again:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        logging.info("Packet decoder: closing socket and context")
        socket.close()
        context.term()


logging.info("packet2bin module loaded")

if __name__ == "__main__":
    receveur_paquets(DEFAULT_PACKET_CONFIG)

import zmq
import logging
import pmt

from reedsolo import ReedSolomonError
import numpy as np

from src.config import PacketConfig
from src.config import DEFAULT_PACKET_CONFIG, DEFAULT_PORTS_CONFIG, PortsConfig

logger = logging.getLogger(__name__)


def decode_packet(raw_packet: bytes, pkt: PacketConfig):
    payload = raw_packet[1].tobytes()
    try:
        decoded_payload = pkt.rsc_codec.decode(payload)[0]
    except ReedSolomonError:
        logger.error("Data corrupted")
        logger.debug("Raw packet: %s", raw_packet)
        return "data corrupted"

    packet_len = decoded_payload[0]

    if packet_len == 0:
        return "preamble"
    elif packet_len == 255:
        return "postamble"
    else:
        raw_payload = pmt.to_python(pmt.deserialize_str(decoded_payload[1 : packet_len + 1]))

        return raw_payload


def listen_for_packets(
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    stop_event=None,
):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.bind(f"tcp://*:{ports_conf.raw_packets_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.setsockopt(zmq.RCVTIMEO, 500)

    logger.info(
        f"Packet decoder listening for packets on port {ports_conf.raw_packets_port}"
    )

    try:
        while stop_event is None or not stop_event.is_set():
            try:
                received = socket.recv()
                payload = pmt.to_python(pmt.deserialize_str(received))
                logger.debug("Received packet from demodulator %s: %s", payload[0]["demodulator_id"], decode_packet(payload, pkt_conf))
            except zmq.Again:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Packet decoder: closing socket and context")
        socket.close()
        context.term()


if __name__ == "__main__":
    listen_for_packets(DEFAULT_PACKET_CONFIG)

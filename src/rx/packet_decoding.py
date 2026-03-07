import zmq
import logging
import pmt

from reedsolo import ReedSolomonError
import numpy as np

from src.config import PacketConfig
from src.config import DEFAULT_PACKET_CONFIG, DEFAULT_PORTS_CONFIG, PortsConfig

logger = logging.getLogger(__name__)


class PacketReassembler:
    """Stateful reassembler for multi-packet PMT messages."""
    def __init__(self):
        self.buffer = bytearray()
        self.state = "IDLE"
        self.frequency = 0.0
        self.reset()

    def reset(self):
        self.buffer = bytearray()
        self.state = "IDLE"

    def process_packet(self, decoded_payload: bytes, frequency: float = 0.0):
        packet_len = decoded_payload[0]
        logger.debug(f"Processing packet with len flag: {packet_len}")

        if packet_len == 0:
            logger.info("Preamble detected, starting reassembly")
            self.reset()
            self.frequency = frequency
            self.state = "COLLECTING"
            return "preamble"
        elif packet_len == 255:
            if self.state == "COLLECTING":
                logger.info(f"Postamble detected, reassembling {len(self.buffer)} bytes")
                try:
                    raw_payload = pmt.to_python(pmt.deserialize_str(bytes(self.buffer)))
                    if isinstance(raw_payload, dict):
                        raw_payload["carrier_freq"] = self.frequency
                    self.reset()
                    return raw_payload
                except Exception as e:
                    logger.error(f"Failed to deserialize reassembled PMT: {e}")
                    # Log first few bytes to debug deserialization
                    logger.debug(f"Buffer start: {self.buffer[:20].hex()}")
                    self.reset()
                    return "deserialization error"
            return "postamble"
        else:
            if self.state == "COLLECTING":
                self.buffer.extend(decoded_payload[1 : packet_len + 1])
                return "collecting"
            else:
                logger.debug(f"Discarding data packet while in state {self.state}")
                return "unexpected data"


# Per-demodulator reassemblers
reassemblers = {}

def decode_packet(payload: list, pkt: PacketConfig):
    """
    Decodes a single raw packet and routes it to the appropriate reassembler.

    This function performs the transition from raw ZMQ-received PDUs to stateful
    message reassembly. It handles multiple demodulator sources simultaneously.

    Args:
        payload (list): A list containing metadata and raw bytes:
            [{"demodulator_id": str, ...}, np.ndarray]
        pkt (PacketConfig): Configuration object containing the RS codec.

    Returns:
        Union[dict, str]: 
            - A dictionary if a full PMT message was successfully reassembled.
            - A status string ("preamble", "collecting", "postamble", "data corrupted", etc.)
              indicating the current state of reassembly for this source.
    """
    metadata = payload[0]
    demod_id = metadata["demodulator_id"]
    carrier_freq = metadata.get("carrier_freq", 0.0)
    raw_packet_data = payload[1].tobytes()

    if demod_id not in reassemblers:
        reassemblers[demod_id] = PacketReassembler()

    reassembler = reassemblers[demod_id]

    try:
        decoded_payload = pkt.rsc_codec.decode(raw_packet_data)[0]
    except ReedSolomonError:
        logger.error(f"Data corrupted for demodulator {demod_id}")
        reassembler.reset()
        return "data corrupted"

    return reassembler.process_packet(decoded_payload, carrier_freq)


def listen_for_packets(
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    stop_event=None,
):
    context = zmq.Context()
    
    # Socket for receiving raw packets from demodulators
    socket = context.socket(zmq.SUB)
    # The decoder binds, and multiple demodulator workers connect to it.
    socket.bind(f"tcp://*:{ports_conf.raw_packets_port}")
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.setsockopt(zmq.RCVTIMEO, 500)

    # Socket for forwarding successfully reassembled messages
    msg_pub_socket = context.socket(zmq.PUB)
    msg_pub_socket.bind(f"tcp://*:{ports_conf.messages_port}")

    logger.info(
        f"Packet decoder listening for packets (binding) on port {ports_conf.raw_packets_port}"
    )
    logger.info(
        f"Packet decoder publishing reassembled messages on port {ports_conf.messages_port}"
    )

    try:
        while stop_event is None or not stop_event.is_set():
            try:
                received = socket.recv()
                logger.debug(f"ZMQ received {len(received)} bytes")
                payload = pmt.to_python(pmt.deserialize_str(received))
                result = decode_packet(payload, pkt_conf)
                
                if isinstance(result, dict):
                    logger.info(
                        f"Successfully reassembled message from {result.get('sender_name', 'unknown')}: {result}"
                    )
                    if result.get("type") == "raw_string":
                        sender_name = result.get("sender_name", "unknown")
                        # PMT to_python returns a numpy array for buffers/blobs
                        # We must convert it to bytes before decoding to string
                        data = result.get("data")
                        if isinstance(data, np.ndarray):
                            message_str = data.tobytes().decode("utf-8")
                        else:
                            message_str = str(data)
                        logger.info(f"Message from {sender_name}: {message_str}")
                        
                        # Forward the original result dict as a PMT message
                        msg_pub_socket.send(pmt.serialize_str(pmt.to_pmt(result)))
                else:
                    logger.debug(
                        f"Packet result from {payload[0]['demodulator_id']}: {result}"
                    )
                    
            except zmq.Again:
                continue
            except Exception as e:
                logger.error(f"Error in packet decoder loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Packet decoder: closing sockets and context")
        socket.close()
        msg_pub_socket.close()
        context.term()


if __name__ == "__main__":
    listen_for_packets(DEFAULT_PACKET_CONFIG)

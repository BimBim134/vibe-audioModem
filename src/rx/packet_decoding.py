import zmq
import logging
import pmt
import base64

from reedsolo import ReedSolomonError
import numpy as np

from src.misc.config import PacketConfig, log_zmq_monitor_event
from src.misc.config import DEFAULT_PACKET_CONFIG, DEFAULT_PORTS_CONFIG, PortsConfig
from src.misc.scrambling import Unscrambler

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
        logger.debug("Processing packet with len flag: %s", packet_len)

        if packet_len == 0:
            logger.info("Preamble detected, starting reassembly")
            self.reset()
            self.frequency = frequency
            self.state = "COLLECTING"
            return ("preamble", frequency)
        elif packet_len == 255:
            if self.state == "COLLECTING":
                logger.info(
                    "Postamble detected, reassembling %s bytes", len(self.buffer)
                )
                try:
                    unscrambler = Unscrambler()
                    raw_payload = pmt.to_python(
                        pmt.deserialize_str(unscrambler.process(bytes(self.buffer)))
                    )
                    if isinstance(raw_payload, dict):
                        raw_payload["carrier_freq"] = self.frequency
                    self.reset()
                    return (raw_payload, frequency)
                except Exception as e:
                    logger.error("Failed to deserialize reassembled PMT: %s", e)
                    logger.debug("Buffer start: %s", self.buffer[:20].hex())
                    self.reset()
                    return ("deserialization error", frequency)
            return ("postamble", frequency)
        else:
            if self.state == "COLLECTING":
                self.buffer.extend(decoded_payload[1 : packet_len + 1])
                return ("collecting", len(self.buffer))
            else:
                logger.debug("Discarding data packet while in state %s", self.state)
                return ("unexpected data", None)


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
        tuple: (result, system_messages)
            - result: A dictionary if a full PMT message was successfully reassembled,
                      or a status string ("preamble", "collecting", "postamble",
                      "data corrupted", etc.) indicating the current state.
            - system_messages: List of dicts with type="system" to send to web UI.
    """
    metadata = payload[0]
    demod_id = metadata["demodulator_id"]
    carrier_freq = metadata.get("carrier_freq", 0.0)
    raw_packet_data = payload[1].tobytes()

    # The PDU might include a 4-byte header (if from our Demodulator)
    if len(raw_packet_data) == pkt.total_packets_len + 4:
        raw_packet_data = raw_packet_data[4:]

    system_messages = []

    if demod_id not in reassemblers:
        reassemblers[demod_id] = PacketReassembler()

    reassembler = reassemblers[demod_id]

    try:
        decoded_payload = pkt.rsc_codec.decode(raw_packet_data)[0]
    except ReedSolomonError:
        logger.error("Data corrupted for demodulator %s", demod_id)
        reassembler.reset()
        system_messages.append({
            "type": "system",
            "status": "error",
            "error": f"Reed-Solomon error — data corrupted at {carrier_freq:.0f} Hz",
            "carrier_freq": carrier_freq,
        })
        return "data corrupted", system_messages

    result, info = reassembler.process_packet(decoded_payload, carrier_freq)

    if result == "preamble":
        system_messages.append({
            "type": "system",
            "status": "preamble",
            "carrier_freq": carrier_freq,
        })
    elif result == "collecting":
        system_messages.append({
            "type": "system",
            "status": "collecting",
            "bytes_received": info,
        })
    elif result == "deserialization error":
        system_messages.append({
            "type": "system",
            "status": "deserialization_error",
            "carrier_freq": carrier_freq,
        })

    return result, system_messages


def send_message(socket, msg_type, **kwargs):
    """Send a unified PMT message to the web UI."""
    msg = {"type": msg_type, **kwargs}
    try:
        socket.send(pmt.serialize_str(pmt.to_pmt(msg)))
    except Exception as e:
        logger.error("Failed to send message: %s", e)


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
    socket.setsockopt(zmq.IMMEDIATE, 1)
    monitor = socket.get_monitor_socket(zmq.EVENT_ALL)

    # Socket for forwarding successfully reassembled messages
    msg_pub_socket = context.socket(zmq.PUB)
    msg_pub_socket.bind(f"tcp://*:{ports_conf.messages_port}")

    logger.info(
        "Packet decoder listening for packets (binding) on port %s",
        ports_conf.raw_packets_port,
    )
    logger.info(
        "Packet decoder publishing messages on port %s",
        ports_conf.messages_port,
    )

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    poller.register(monitor, zmq.POLLIN)

    try:
        while stop_event is None or not stop_event.is_set():
            try:
                socks = dict(poller.poll(500))
            except zmq.ZMQError:
                break

            if monitor in socks and socks[monitor] == zmq.POLLIN:
                try:
                    event = monitor.recv_multipart()
                    logger.info(
                        "ZMQ monitor [%s] %s",
                        ports_conf.raw_packets_port,
                        log_zmq_monitor_event(event),
                    )
                except Exception as e:
                    logger.debug("ZMQ monitor error: %s", e)

            if socket in socks and socks[socket] == zmq.POLLIN:
                try:
                    received = socket.recv(zmq.NOBLOCK)
                    logger.debug("ZMQ received %s bytes", len(received))
                    payload = pmt.to_python(pmt.deserialize_str(received))
                    result, system_messages = decode_packet(payload, pkt_conf)

                    for msg in system_messages:
                        send_message(msg_pub_socket, msg["type"], **{k: v for k, v in msg.items() if k != "type"})

                    if isinstance(result, dict):
                        logger.info(
                            "Successfully reassembled message from %s: %s",
                            result.get("sender_name", "unknown"),
                            result,
                        )
                        
                        data = result.get("data")
                        if result.get("type") == "raw_string":
                            if isinstance(data, np.ndarray):
                                result["data"] = data.tobytes().decode("utf-8", errors="replace")
                            else:
                                result["data"] = str(data)
                            logger.info("Message from %s: %s", result["sender_name"], result["data"])
                        else:
                            # For raw_bytes and file, use base64 for JSON compatibility downstream
                            if isinstance(data, np.ndarray):
                                result["data"] = base64.b64encode(data.tobytes()).decode("utf-8")
                        
                        # Set unified type for CLI/UI display logic
                        result["type"] = "data"
                        msg_pub_socket.send(pmt.serialize_str(pmt.to_pmt(result)))
                    else:
                        logger.debug(
                            "Packet result from %s: %s",
                            payload[0]["demodulator_id"],
                            result,
                        )

                except zmq.Again:
                    continue
                except Exception as e:
                    logger.error("Error in packet decoder loop: %s", e)
                    import traceback

                    logger.debug(traceback.format_exc())
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Packet decoder: closing sockets and context")
        if monitor:
            monitor.close()
        socket.close()
        msg_pub_socket.close()
        context.term()


if __name__ == "__main__":
    listen_for_packets(DEFAULT_PACKET_CONFIG)

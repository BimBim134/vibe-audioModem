from functools import singledispatch
from itertools import chain
from pathlib import Path
from typing import Iterator, Any
from secrets import token_bytes

import numpy as np
import pmt
from reedsolo import RSCodec

import config

def split_payload_into_packet(
    payload: bytes, pkt: config.PacketConfig
) -> Iterator[bytes]:
    """split data into packet such as :
    packet = [[data_len], [data], [filler]].

    Args:
        payload (bytes): payload data
        pkt (config.PacketConfig): packet configuration

    Yields:
        Iterator[bytes]: packet
    """
    mv = memoryview(payload)
    pointer = 0

    # first packets
    while pointer + pkt.data_chunck_len < len(mv):
        # construct packet
        data = mv[pointer : pointer + pkt.data_chunck_len]
        data_len_flag = pkt.data_chunck_len.to_bytes()

        # assemble packet
        data_chunck = data_len_flag + data

        # "move" pointer to next data chunck
        pointer += pkt.data_chunck_len

        # yield data chunck
        yield data_chunck

    # last packet with filler
    data = mv[pointer:]
    filler = token_bytes(pkt.data_chunck_len - len(data))
    data_len_flag = len(data).to_bytes()

    # assemble packet
    data_chunck = data_len_flag + data + filler

    # yield data chunck
    yield data_chunck


def generate_dummy_packet(pkt: config.PacketConfig, mode:str="preamble") -> bytes:
    """generate a dummy packet. the data_len flag is set to 0.

    Args:
        pkt (config.PacketConfig): packet description
        mode (str): 

    Returns:
        bytes: dummy packet
    """
    data = token_bytes(pkt.data_chunck_len)
    if mode == "preamble":
        data_len_flag = (0).to_bytes()
    else:
        data_len_flag = (255).to_bytes()
    return data_len_flag + data


def payload_to_encoded_packet(payload: bytes, pkt: config.PacketConfig) -> np.ndarray:
    """packetize payload with preamble, data, postamble.

    Args:
        payload (bytes): _description_
        pkt (config.PacketConfig): _description_

    Returns:
        tuple: _description_
    """
    # initialize encoder
    rsc = RSCodec(pkt.error_correction_len)

    # encode packet
    packets = [
        rsc.encode(data_chunck)
        for data_chunck in split_payload_into_packet(payload, pkt)
    ]

    # add preamble and postamble
    preamble = [
        rsc.encode(generate_dummy_packet(pkt)) for _ in range(pkt.preamble_packets)
    ]
    postamble = [
        rsc.encode(generate_dummy_packet(pkt, "postamble")) for _ in range(pkt.postamble_packets)
    ]

    # chain everything together
    flattened = b"".join(chain(preamble, packets, postamble))

    return np.frombuffer(flattened, dtype=np.uint8)


def import_file_from_path(filepath: Path) -> bytes:
    """opens a file from path

    Args:
        filepath (Path): input file path

    Returns:
        bytes: serialized pmt payload with path included
    """
    with open(filepath, "rb") as f:
        input_file = f.read()
    input_file = np.frombuffer(input_file, dtype=np.uint8)
    payload = pmt.to_pmt({"path": filepath, "data": input_file})
    output = pmt.serialize_str(payload)
    return output


@singledispatch
def prepare_data(input_data, pkt: config.PacketConfig) -> np.ndarray:
    """generic function to prepare bytes from input data"""
    raise NotImplementedError


@prepare_data.register
def _(input_data: Path, pkt: config.PacketConfig) -> np.ndarray:
    """prepare data from filepath

    Args:
        input_data (Path): file path
        pkt (config.PacketConfig): packet configuration

    Returns:
        bytes: packetized and error encoded file
    """
    file = import_file_from_path(input_data)
    return payload_to_encoded_packet(file, pkt)


@prepare_data.register
def _(input_data: bytes, pkt: config.PacketConfig) -> np.ndarray:
    """prepare data from bytes

    Args:
        input_data (bytes): file
        pkt (config.PacketConfig): packet configuration

    Returns:
        bytes: packetized and error encoded file
    """
    return payload_to_encoded_packet(input_data, pkt)


def export_to_bin(input_data: Any, pkt: config.PacketConfig, filepath: Path) -> None:
    """export file to packetized file

    Args:
        input_data (Any): input data
        pkt (config.PacketConfig): packet configuration
        filepath (Path): output file path
    """
    data = prepare_data(input_data, pkt)
    with filepath.open("wb") as f:
        f.write(data)


if __name__ == "__main__":
    conf = config.DEFAULT_PACKET_CONFIG
    TEST_PAYLOAD = (
        b"hello world ! this is a message transmitted using vibe-audio-modem :)"
    )
    packets = prepare_data(TEST_PAYLOAD, conf)
    assert len(packets) % conf.total_packets_len == 0

    print(f"payload (length:{len(packets)}):\n", TEST_PAYLOAD)
    print("packets")
    for p in range(int(len(packets) / conf.total_packets_len)):
        idx = slice(p * conf.total_packets_len, (p + 1) * conf.total_packets_len)
        print(
            p,
            f"(lenght:{len(packets[idx])})\n",
            b"".join([b.tobytes() for b in packets[idx]]),
        )
    
    export_to_bin(TEST_PAYLOAD, conf, Path("research/test_payload_packetized.bin"))

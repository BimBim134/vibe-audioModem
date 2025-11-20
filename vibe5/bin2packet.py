"""
Embedded Python Block: bytes to packets block
"""

from random import randbytes
from pathlib import Path
from typing import Iterator
from math import ceil
from itertools import chain
from functools import singledispatch

import pmt
from reedsolo import RSCodec
import numpy as np

import config


def split_payload_into_packet(payload: bytes, packets_len: int) -> Iterator[bytes]:
    """split payload into packets

    Args:
        payload (bytes): input payload
        packets_len (int): packet length

    Yields:
        Iterator[bytes]: output packets
    """
    # add some random bytes after the payload so that its length is a multiple of packet_len
    len_filler = ceil(len(payload) / packets_len) * packets_len - len(payload)
    payload += randbytes(len_filler)
    for i in range(0, len(payload), packets_len):
        yield payload[i : i + packets_len]


def payload_to_encoded_packet(payload: bytes, pkt: config.PacketConfig) -> tuple:
    """_summary_

    Args:
        payload (bytes): _description_
        pkt (config.PacketConfig): _description_

    Returns:
        bytes: _description_
    """
    # initialize encoder
    ecc = RSCodec(pkt.error_correction_len)
    data_chunck_len = pkt.data_chunck_len

    # encode packet
    packets = [
        ecc.encode(data_chunck)
        for data_chunck in split_payload_into_packet(payload, data_chunck_len)
    ]

    # add preamble and postamble
    preamble = [ecc.encode(randbytes(data_chunck_len))] * pkt.preamble_packets
    postamble = [ecc.encode(randbytes(data_chunck_len))] * pkt.postamble_packets

    # chain everything together
    flattened = b"".join(chain(preamble, packets, postamble))

    return tuple(flattened)


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
def prepare_data(input_data, pkt: config.PacketConfig) -> bytes:
    """generic function to prepare bytes from input data"""
    raise NotImplementedError


@prepare_data.register
def _(input_data: Path, pkt: config.PacketConfig) -> tuple:
    """prepare data from filepath

    Args:
        input_data (Path): file path
        pkt (config.PacketConfig): packet configuration

    Returns:
        bytes: packetized and error encoded file
    """
    file = import_file_from_path(filepath)
    return payload_to_encoded_packet(file, pkt)

@prepare_data.register
def _(input_data:bytes, pkt: config.PacketConfig) -> tuple:
    """prepare data from bytes

    Args:
        input_data (bytes): file
        pkt (config.PacketConfig): packet configuration

    Returns:
        bytes: packetized and error encoded file
    """
    return payload_to_encoded_packet(input_data, pkt)

if __name__ == "__main__":
    pass

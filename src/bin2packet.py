"""
Embedded Python Block: bytes to packets block
"""

from random import randbytes
from pathlib import Path
from typing import Iterator
from math import ceil
from itertools import chain
from functools import singledispatch
from secrets import token_bytes

import pmt
from reedsolo import RSCodec
import numpy as np

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

    else:
        # last packet with filler
        data = mv[pointer:]
        filler = token_bytes(pkt.data_chunck_len - len(data))
        data_len_flag = len(data).to_bytes()

        # assemble packet
        data_chunck = data_len_flag + data + filler

        # yield data chunck
        yield data_chunck


def generate_dummy_packet(pkt: config.PacketConfig)->bytes:
    """generate a dummy packet. the data_len flag is set to 0.

    Args:
        pkt (config.PacketConfig): packet description

    Returns:
        bytes: dummy packet
    """
    data = token_bytes(pkt.data_chunck_len)
    data_len_flag = (0).to_bytes()
    return data_len_flag + data


def payload_to_encoded_packet(payload: bytes, pkt: config.PacketConfig) -> tuple:
    """packetize payload with preamble, data, postamble.

    Args:
        payload (bytes): _description_
        pkt (config.PacketConfig): _description_

    Returns:
        tuple: _description_
    """
    # initialize encoder
    ecc = RSCodec(pkt.error_correction_len)

    # encode packet
    packets = [
        ecc.encode(data_chunck)
        for data_chunck in split_payload_into_packet(payload, pkt)
    ]

    # add preamble and postamble
    preamble = [ecc.encode(generate_dummy_packet(pkt)) * pkt.preamble_packets]
    postamble = [ecc.encode(generate_dummy_packet(pkt)) * pkt.postamble_packets]

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
def prepare_data(input_data, pkt: config.PacketConfig) -> tuple:
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
    file = import_file_from_path(input_data)
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

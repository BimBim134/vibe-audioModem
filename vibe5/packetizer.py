from random import randbytes
from pathlib import Path
import base64

from reedsolo import RSCodec
import numpy as np


def importFileFromPath(path):
    """import file as binary

    Args:
        path (str): file path

    Returns:
        data (bytes): output file
    """
    with open(path, "rb") as f:
        data = f.read()
    return data


def split_into_chuncks(data, chunck_size):
    """takes some binary data and split it into chuncks

    Args:
        data (bytes): input data
        chunck_size (int): chunck size in bytes

    Yields:
        bytes: chunck
    """
    for i in range(0, len(data), chunck_size):
        yield data[i : i + chunck_size]


def binary_to_encoded_packet(
    binaryFile,
    packet_size=64,
    preamble_size=3,
    postamble_size=1,
    ecc_size=6,
    id_len=2,
    data_len=1,
    verbose=False,
):
    """takes a binary file and split it into encoded packets.

    each packet is formatted like so, before Reed Solomon Encoding:
    [ID, data_length, data]

    Args:
        binaryFile (bytes, str): input binary file
        packet_size (int, optional): total packet size in bytes. Defaults to 64.
        preamble_size(int, optionnal): preamble size in packet.
        postamble_size(int, optionnal): postamble size in packet.
        ecc_size (int, optional): Error Correction Code length. Defaults to 5.
        id_len (int, optional): id descriptor length. (With 2 bytes, 65535 packet can be identified at most). Defaults to 2.
        data_len (int, optional): data length descriptor length. (with 1 byte, max packet size is 255). Defaults to 1.
        verbose (bool, optional): if true, you get to know the ecc performance.
    Returns:
        output (np.uint8): output packets
    """
    # checking for input data type
    if isinstance(binaryFile, str):
        path = Path(binaryFile)
        if path.is_file():
            binaryFile = importFileFromPath(path)
        else:
            raise FileExistsError
    elif isinstance(binaryFile, bytes):
        pass
    else:
        raise TypeError

    # encoding the input binaries to base64
    binaryFile = base64.urlsafe_b64encode(binaryFile)

    # creating preamble
    preamble = [
        (0).to_bytes(id_len, "big") + randbytes(packet_size - id_len - ecc_size)
    ] * preamble_size

    # creating postamble
    postamble = [
        (0).to_bytes(id_len, "big")
        + b"eof"
        + randbytes(packet_size - id_len - ecc_size - 3)
    ] * postamble_size

    # spliting data into packets
    chuncks = split_into_chuncks(binaryFile, packet_size - ecc_size - id_len - data_len)
    chunck_with_id = [
        (i + 1).to_bytes(id_len, "big") + len(c).to_bytes(data_len, "big") + c
        for i, c in enumerate(chuncks)
    ]
    # filling the last packet with random bytes to reach packet chunk size
    while len(chunck_with_id[-1]) < packet_size - ecc_size:
        chunck_with_id[-1] += randbytes(1)

    # assembling packets
    chunck_with_id = preamble + chunck_with_id + postamble

    # adding error code correction
    ecc = RSCodec(ecc_size)
    ecc.maxerrata(verbose=verbose)
    encoded_chuncks = [ecc.encode(c) for c in chunck_with_id]

    # converting to np.array([np.uint8])
    output = np.array([np.frombuffer(ec, dtype=np.uint8) for ec in encoded_chuncks])

    return output


def open_and_packetize_file(path):
    """
    Open a binary file and packetize it into encoded packets.

    Args:
        path (str): The path to the binary file to be packetized.

    Returns:
        np.uint8: A flattened array of encoded packets.
    """
    packets = binary_to_encoded_packet(path)
    output_vector = packets.flatten()
    return output_vector


if __name__ == "__main__":
    # this is a module
    pass

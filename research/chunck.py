from random import randbytes, shuffle, randint, choice
import warnings
import hashlib
from pathlib import Path

from reedsolo import RSCodec, ReedSolomonError
import numpy as np

def importFileFromPath(path):
    """import file as binary

    Args:
        path (str): file path

    Returns:
        data (bytes): output file
    """
    with open(path, 'rb') as f:
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
        yield data[i:i + chunck_size]



def binary_to_encoded_packet(binaryFile,
                             packet_size=64,
                             preamble_size = 3,
                             postamble_size = 3,
                             ecc_size=6,
                             id_len=2,
                             data_len=1,
                             verbose=False):
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

    ecc = RSCodec(ecc_size)
    ecc.maxerrata(verbose=verbose)

    chuncks = split_into_chuncks(binaryFile,
                                 packet_size - ecc_size - id_len - data_len)
    
    preamble = [(0).to_bytes(id_len, 'big') + randbytes(packet_size - id_len)] * preamble_size
    postamble = [(0).to_bytes(id_len, 'big') + b'eof' + randbytes(packet_size - id_len - 3)] * postamble_size

    chunck_with_id = preamble + [(i+1).to_bytes(id_len, 'big') +
                                 len(c).to_bytes(data_len, 'big') + c
                                 for i, c in enumerate(chuncks)] + postamble

    while len(chunck_with_id[-1]) < packet_size - ecc_size:
        chunck_with_id[-1] += randbytes(1)

    encoded_chuncks = [ecc.encode(c) for c in chunck_with_id]

    output = [np.frombuffer(ec, dtype=np.uint8) for ec in encoded_chuncks]

    return output


def decode_single_packet(packet,
                         ecc,
                         id_len,
                         data_len):
    """takes a single packet and decode it.

    Args:
        packet (bytes): input packet
        ecc (RSCodec): Reed Solomon Encoder
        id_len (int): id descriptor length
        data_len (int): data length descriptor length

    Returns:
        id, data (int, bytes): packet id, packet data
    """
    try:
        decoded_packet = ecc.decode(packet)[0]
        id = int.from_bytes(decoded_packet[:id_len], 'big') - 1
        if id == -1: # filter out the preamble and postamble
            if (packet[id_len:id_len+3] - np.array([101, 111, 102])).sum() == 0 :
                return (-1, b'')
        else:
            d_len = int.from_bytes(decoded_packet[id_len:id_len + data_len], 'big')
            return (id, decoded_packet[id_len + data_len:id_len + data_len + d_len])
    except ReedSolomonError as e:
        warnings.warn("packet is corrupted beyond repair !")
        print(e)
    return (-1, b'')

def encoded_packets_to_binary(packets,
                              ecc_size=6,
                              id_len=2,
                              data_len=1,
                              verbose=False):
    """takes a list of packet and decode it back to the original file.

    Args:
        packets (list, bytearray): input data
        ecc_size (int, optional): Error Correction Code length. Defaults to 5.
        id_len (int, optional): id descriptor length. (With 2 bytes, 65535 packet can be identified at most). Defaults to 2.
        data_len (int, optional): data length descriptor length. (with 1 byte, max packet size is 255). Defaults to 1.
        verbose (bool, optional): if true, you get to know the ecc performance.

    Returns:
        bytes: output binary
    """
    ecc = RSCodec(ecc_size)
    ecc.maxerrata(verbose=verbose)

    data = {}

    for p in packets:
        id, packet_data = decode_single_packet(p, ecc, id_len, data_len)
        if not id == -1:
            data[id] = packet_data

    data = dict(sorted(data.items()))

    received_ids = set(data.keys())
    check_id = set(range(len(data)))
    if received_ids != check_id:
        warnings.warn("data may be incomplete !", BytesWarning)

    data = list(data.values())
    return b''.join(data)


if __name__ == "__main__":

    def test_for_decoding(errors_enable):
        """torture test

        Returns:
            bool: returns True if the test succeed
        """
        binaryFile = randbytes(1000)
        packets = binary_to_encoded_packet(binaryFile)
        # torture test
        if errors_enable:
            for p in packets:
                for error in range(3):
                    idx = randint(0, len(p)-1)
                    p[idx] = randint(0, 255)  # change byte to simulate an error
        decoded_binary = encoded_packets_to_binary(packets)
        # calculating hash
        original_file_hash = hashlib.md5(binaryFile).hexdigest()
        decoded_file_hash = hashlib.md5(decoded_binary).hexdigest()
        return original_file_hash == decoded_file_hash
    
    assert test_for_decoding(errors_enable=False)
    assert test_for_decoding(errors_enable=True)

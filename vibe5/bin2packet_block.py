"""
Embedded Python Block: bytes to packets block
"""

from random import randbytes
import pmt
from pathlib import Path
import base64

from reedsolo import RSCodec
from gnuradio import gr
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

    binaryFile = base64.urlsafe_b64encode(binaryFile)

    chuncks = split_into_chuncks(binaryFile,
                                 packet_size - ecc_size - id_len - data_len)
    
    preamble = [(0).to_bytes(id_len, 'big') + randbytes(packet_size - id_len - ecc_size)] * preamble_size
    postamble = [(0).to_bytes(id_len, 'big') + b'eof' + randbytes(packet_size - id_len - ecc_size -3)] * postamble_size

    chunck_with_id = [(i+1).to_bytes(id_len, 'big') + len(c).to_bytes(data_len, 'big') + c
                      for i, c in enumerate(chuncks)]

    while len(chunck_with_id[-1]) < packet_size - ecc_size:
        chunck_with_id[-1] += randbytes(1)

    # adding the preamble and postamble
    chunck_with_id = preamble + chunck_with_id + postamble

    encoded_chuncks = [ecc.encode(c) for c in chunck_with_id]

    output = [np.frombuffer(ec, dtype=np.uint8) for ec in encoded_chuncks]

    return output


class blk(gr.basic_block):
    def __init__(self,
                 input_binary=randbytes(1000),
                 packet_size=64,
                 preamble_size=3,
                 postamble_size=3,
                 ecc_size=6,
                 id_len=2,
                 data_len=1):
        gr.basic_block.__init__(
            self,
            name='Binary to Packet',
            in_sig=None,
            out_sig=[np.uint8]
        )
        self.packet_size = packet_size
        self.out_packets = binary_to_encoded_packet(binaryFile=input_binary,
                                                    packet_size=packet_size,
                                                    preamble_size=preamble_size,
                                                    postamble_size=postamble_size,
                                                    ecc_size=ecc_size,
                                                    id_len=id_len,
                                                    data_len=data_len)
        self.preamble_size = preamble_size
        self.postamble_size = postamble_size

        self.id_len = id_len
        self.current_packet_index = 0
        self.indx = 0
        self.packet_count = len(self.out_packets)
        self.eof = False

    def get_state(self, idx):
        if idx < self.preamble_size:
            return "preamble"
        elif self.preamble_size <= idx < self.packet_count - self.postamble_size:
            return "data"
        elif self.packet_count - self.postamble_size <= idx < self.packet_count:
            return "postamble"
        else:
            return "idle"

    def general_work(self, input_items, output_items):
        if not self.eof:
            if self.current_packet_index < self.packet_count:
                current_packet = self.out_packets[self.current_packet_index]
                output_items[0][:self.packet_size] = current_packet
                gr.log_debug.info(f"sending packet {self.current_packet_index}. {self.get_state(self.current_packet_index)}")

                self.indx += self.packet_size
                self.current_packet_index += 1
                self.produce(0, self.packet_size)
                return 0
            else:
                self.eof = True
                gr.log_debug.info("EOF")
                return 0
        else:
            return 0


if __name__ == "__main__":
    test = blk()
from random import randbytes
import pmt

from reedsolo import RSCodec
from gnuradio import gr


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
        binaryFile (bytes): input binary file
        packet_size (int, optional): total packet size in bytes. Defaults to 64.
        preamble_size(int, optionnal): preamble size in packet.
        postamble_size(int, optionnal): postamble size in packet.
        ecc_size (int, optional): Error Correction Code length. Defaults to 5.
        id_len (int, optional): id descriptor length. (With 2 bytes, 65535 packet can be identified at most). Defaults to 2.
        data_len (int, optional): data length descriptor length. (with 1 byte, max packet size is 255). Defaults to 1.
        verbose (bool, optional): if true, you get to know the ecc performance.
    Returns:
        encoded_chuncks (list): output packets
    """
    ecc = RSCodec(ecc_size)
    ecc.maxerrata(verbose=verbose)

    chuncks = split_into_chuncks(binaryFile,
                                 packet_size - ecc_size - id_len - data_len)
    
    preamble = [(0).to_bytes(id_len, 'big') + randbytes(packet_size - id_len)] * preamble_size
    postamble = [(0).to_bytes(id_len, 'big') + randbytes(packet_size - id_len)] * postamble_size

    chunck_with_id = preamble + [(i+1).to_bytes(id_len, 'big') +
                                 len(c).to_bytes(data_len, 'big') + c
                                 for i, c in enumerate(chuncks)] + postamble

    while len(chunck_with_id[-1]) < packet_size - ecc_size:
        chunck_with_id[-1] += randbytes(1)

    encoded_chuncks = [ecc.encode(c) for c in chunck_with_id]

    return encoded_chuncks


class blk(gr.sync_block):
    def __init__(self,
                 input_binary,
                 packet_size=64,
                 preamble_size=3,
                 postamble_size=3,
                 ecc_size=6,
                 id_len=2,
                 data_len=1):
        gr.sync_block.__init__(
            self,
            name='Binary to Packet',
            out_sig=[bytes]
        )
        self.out_packets = binary_to_encoded_packet(input_binary,
                                                    preamble_size,
                                                    postamble_size,
                                                    packet_size,
                                                    ecc_size,
                                                    id_len,
                                                    data_len)
        self.current_packet_index = 0
        self.packet_count = len(self.out_packets)
        self.eof = False

    def work(self, input_items, output_items):
        if not self.eof:
            if self.current_packet_index <= self.packet_count:
                output_items[0][:] = self.out_packets[self.current_packet_index]
                self.current_packet_index += 1
                
                packet_length = len(output_items[0])
                key = pmt.intern("packet_len")
                val = pmt.from_long(packet_length)
                self.add_item_tag(0,  # Write to output port 0
                                self.indx,   # Index of the tag
                                key,   # Key of the tag
                                val,
                                srcid=pmt.PMT_F)
                return packet_length
            else:
                self.eof = True
                return 0
        else:
            return 0

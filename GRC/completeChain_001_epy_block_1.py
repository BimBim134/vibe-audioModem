"""
Embedded Python Blocks:

Each time this file is saved, GRC will instantiate the first class it finds
to get ports and parameters of your block. The arguments to __init__  will
be the parameters. All of them are required to have default values!
"""

import warnings

import numpy as np
from gnuradio import gr
from reedsolo import RSCodec, ReedSolomonError

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
                return (-1, b'eof')
        else:
            d_len = int.from_bytes(decoded_packet[id_len:id_len + data_len], 'big')
            return (id, decoded_packet[id_len + data_len:id_len + data_len + d_len])
    except ReedSolomonError as e:
        warnings.warn("packet is corrupted beyond repair !")
        print(e)
    return (-1, b'')

class blk(gr.sync_block):  # other base classes are basic_block, decim_block, interp_block
    def __init__(self,
                 out_filename='',
                 packet_size=64,
                 ecc_size=6,
                 id_len=2,
                 data_len=1,
                 verbose=False):
        gr.sync_block.__init__(
            self,
            name='Binary to Packet',
            in_sig=[np.uint8],
            out_sig=None
        )
        self.out_filename = out_filename
        self.packet_size = packet_size
        self.ecc = RSCodec(ecc_size)
        self.ecc.maxerrata(verbose=verbose)
        self.id_len = id_len
        self.data_len = data_len

        self.packets = {}

        self.indx = 0
        self.packet_count = 0
        self.eof = False
    
    def save_file(self):
        data = dict(sorted(self.packets.items()))

        received_ids = set(data.keys())
        check_id = set(range(len(data)))
        if received_ids != check_id:
            warnings.warn("data may be incomplete !", BytesWarning)

        data = list(data.values())
        with open(self.out_filename, 'wb') as f:
            f.write(b''.join(data))

    def work(self, input_items, output_items):
        if not self.eof:
            for p in input_items[0]:
                if isinstance(p, np.uint8):
                    return 0
                else:
                    id, packet_data = decode_single_packet(p,
                                                        self.ecc,
                                                        self.id_len,
                                                        self.data_len)
                    if not id == -1:
                        # saving data
                        self.packet[id] = packet_data
                    else:
                        # checking if it is EOF
                        if packet_data == b'eof':
                            self.eof = True
                            break
            return 0
        else:
            gr.log_debug(f'saving file to {self.out_filename}')
            self.save_file()
            return 0

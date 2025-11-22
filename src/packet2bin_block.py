"""
Embedded Python Blocks:

Each time this file is saved, GRC will instantiate the first class it finds
to get ports and parameters of your block. The arguments to __init__  will
be the parameters. All of them are required to have default values!
"""

import warnings
import base64

import numpy as np
from gnuradio import gr
from reedsolo import RSCodec, ReedSolomonError
import pmt

from config import PacketConfig

def decode_single_packet(packet:np.uint8,
                         pkt:PacketConfig):

    try:
        decoded_packet = ecc.decode(packet)[0]
        data_len = int.from_bytes(decoded_packet[0])
        return decoded_packet[1:data_len]

    except ReedSolomonError as e:
        warnings.warn("packet is corrupted beyond repair !")
        print(e)
        return b''

class blk(gr.basic_block):  # other base classes are basic_block, decim_block, interp_block
    def __init__(self,
                 out_filename='',
                 packet_size=64,
                 ecc_size=6,
                 id_len=2,
                 data_len=1,
                 verbose=False):
        gr.sync_block.__init__(
            self,
            name='Packets to Binaries',
            in_sig=[np.uint8],
            out_sig=None
        )
        self.out_filename = out_filename
        self.packet_size = packet_size
        self.rsc = RSCodec(ecc_size)
        self.rsc.maxerrata(verbose=verbose)
        self.id_len = id_len
        self.data_len = data_len

        self.packets = {}

        self.packet_count = 0
        self.eof = False

    
    def save_file(self):
        data = dict(sorted(self.packets.items()))

        received_ids = set(data.keys())
        check_id = set(range(len(data)))
        if received_ids != check_id:
            warnings.warn("data may be incomplete !", BytesWarning)

        data = list(data.values())
        output = b''.join(data)
        output = base64.urlsafe_b64decode(output)
        with open(self.out_filename, 'wb') as f:
            f.write(output)

    def work(self, input_items, output_items):
        if not self.eof:
            in0 = input_items[0]
            tags = self.get_tags_in_window(0, 0, len(in0))

            packet_start = 0
            for tag in tags:
                if tag.key == pmt.string_to_symbol("packet_len"):
                    packet_len = pmt.to_long(tag.value)
                    packet_end = packet_start + packet_len

                    if packet_end <= len(in0):
                        raw_packet = in0[packet_start:packet_end]

                        id, packet_data = decode_single_packet(raw_packet,
                                                            self.rsc,
                                                            self.id_len,
                                                            self.data_len)
                        if len(packet_data) > 0:
                            packet_start = packet_end
                            self.consume(0, packet_start)
                            if not id == -1:
                                # saving data
                                gr.log_debug.info(f"receiving packet {id:0>6d} : {len(packet_data)}")
                                self.packets[id] = packet_data
                                return 0
                            else:
                                # checking if it is EOF
                                gr.log_debug.info(f"receiving packet pre/postamble : {len(packet_data)}")
                                if b'eof' in packet_data:
                                    gr.log_debug.info("receving EOF")
                                    self.eof = True
                                    self.save_file()
                                    gr.log_debug.info(f'saving file to {self.out_filename}')
                                return 0
                        else:
                            gr.log_debug.info("no data in packet")
                            return 0

                    else:
                        gr.log_debug.info("packet not complete, waiting for more data")
                        return 0              
                else:
                    gr.log_debug.info(f'unknown tag {tag.key}')
                    return 0
        return -1 # Return -1 to indicate end of file

if __name__ == "__main__":
    test = blk()
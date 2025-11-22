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
import pmt

from config import PacketConfig

def decode_single_packet(packet:np.ndarray,
                         rsc: RSCodec):

    try:
        decoded_packet = rsc.decode(packet)[0]
        data_len = int.from_bytes(decoded_packet[0])
        return decoded_packet[1:data_len]

    except ReedSolomonError as e:
        warnings.warn("packet is corrupted beyond repair !")
        print(e)
        return b''

class Packet2Bin(gr.basic_block):
    def __init__(self,
                 pkt: PacketConfig,
                 ):
        gr.basic_block.__init__(
            self,
            name='Packets to Binaries',
            in_sig=[np.uint8],
            out_sig=None
        )
        self.rsc = RSCodec(pkt.error_correction_len)
        self.eof = False
        self.output_data = b''
        self.state = 'preamble'

    def work(self, input_items, output_items):
        in0 = input_items[0]
        # check if not allready eof
        if not self.eof:
            # get bytes
            tags = self.get_tags_in_window(0, 0, len(in0))

            pointer = 0
            for tag in tags:
                if tag.key == pmt.string_to_symbol("packet_len"):
                    packet_len = pmt.to_long(tag.value)
                    current_packet_end = pointer + packet_len

                    # check if there is enough input data to work with
                    if current_packet_end <= len(in0):
                        # read and decode data
                        raw_packet = in0[pointer:current_packet_end]
                        extracted_data = decode_single_packet(self.rsc, raw_packet)

                        # saving data and updating pointer
                        self.output_data += extracted_data
                        pointer = current_packet_end
                        
                        # updating state
                        if len(extracted_data) > 0 and self.state == 'preamble':
                            self.state = 'data'
                        elif len(extracted_data) == 0 and self.state == 'data':
                            self.state = 'preamble'
                            self.eof = True

        return len(in0)
                        

if __name__ == "__main__":
    test = blk()
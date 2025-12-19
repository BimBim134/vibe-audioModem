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

from config import PacketConfig, DEFAULT_PACKET_CONFIG

def decode_single_packet(packet:np.ndarray,
                            rsc: RSCodec) -> np.ndarray:
    """Decode a single Reed-Solomon encoded packet into its binary data.
    Args:
        packet (np.ndarray): The encoded packet as numpy array of 8-bit integers.
        rsc (RSCodec): An instance of the RSCodec to use for decoding.
    Returns:
        np.ndarray: The decoded packet as numpy array of 8-bit integers.
    """

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

        # Register message output port
        self.message_port_register_out(pmt.intern("bin_out"))

    def work(self, input_items, output_items):
        in0 = input_items[0]
        consumed = 0

        if not self.eof:
            tags = self.get_tags_in_window(0, 0, len(in0))

            # Sort tags by offset to ensure proper ordering
            tags = sorted(tags, key=lambda t: t.offset)

            for tag in tags:
                if tag.key == pmt.string_to_symbol("packet_len"):
                    packet_len = pmt.to_long(tag.value)

                    # Compute relative offset of tag inside current buffer
                    tag_offset = tag.offset - self.nitems_read(0)
                    packet_end = tag_offset + packet_len

                    # Not enough data yet → don't consume anything
                    if packet_end > len(in0):
                        break

                    # Extract and decode packet
                    raw_packet = in0[tag_offset:packet_end]
                    extracted = decode_single_packet(raw_packet, self.rsc)

                    # Save result
                    self.output_data += extracted

                    # Update state machine
                    if len(extracted) > 0 and self.state == 'preamble':
                        self.state = 'data'
                    elif len(extracted) == 0 and self.state == 'data':
                        self.state = 'preamble'
                        self.eof = True

                    # We have processed up to packet_end
                    consumed = packet_end

                # If EOF reached → publish output_data once
        if self.eof and len(self.output_data) > 0:
            msg = pmt.init_u8vector(len(self.output_data), self.output_data)
            self.message_port_pub(pmt.intern("bin_out"), msg)
            self.output_data = b''  # Reset buffer after sending

        return consumed

if __name__ == "__main__":
    test = Packet2Bin(pkt=DEFAULT_PACKET_CONFIG)

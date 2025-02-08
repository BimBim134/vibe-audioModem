"""
Just a collection of the different blocks type in GNU radio
"""

import numpy as np
from gnuradio import gr



class my_basic_adder_block(gr.basic_block):
    def __init__(self):
        gr.basic_block.__init__(self,
            name="another_adder_block",
            in_sig=[np.float32, np.float32],
            out_sig=[np.float32])

    def general_work(self, input_items, output_items):
        #buffer references
        in0 = input_items[0][:len(output_items[0])]
        in1 = input_items[1][:len(output_items[0])]
        out = output_items[0]

        #process data
        out[:] = in0 + in1

        #consume the inputs
        self.consume(0, len(in0)) #consume port 0 input
        self.consume(1, len(in1)) #consume port 1 input


        #return produced
        return len(out)


class my_interp_block(gr.interp_block):
    def __init__(self, args):
        gr.interp_block.__init__(self,
            name="my block",
            in_sig=[np.float32],
            out_sig=[np.float32])
        self.set_relative_rate(interpolation)

    #work function here...


class my_decim_block(gr.decim_block):
    def __init__(self, decim_rate):
        gr.decim_block.__init__(self,
            name="my block",
            in_sig=[np.float32],
            out_sig=[np.float32],
            decim = decim_rate)
        self.set_relative_rate(1.0/decim_rate)
        self.decimation = decim_rate

    def work(self, input_items, output_items):
        output_items[0][:] = input_items[0][0::self.decimation]
        return len(output_items[0])
    
class my_sync_block(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(self,
            name = "my sync block",
            in_sig = [np.float32, np.float32],
            out_sig = [np.float32],
        )
    def work(self, input_items, output_items):
        output_items[0][:] = input_items[0] + input_items[1]
        return len(output_items[0])
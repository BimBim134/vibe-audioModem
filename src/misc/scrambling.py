class AdditiveScrambler:
    def __init__(self, mask=0x48, seed=0x7F, reg_length=7):
        """
        mask: taps positions (ex: 0x88 for x^7 + x^4)
        seed: initial seed value (must not be 0)
        reg_length: number of bits of the register (7 for Voyager-style)
        """
        self.mask = mask
        self.initial_seed = seed
        self.reg_length = reg_length
        self.reg = seed

    def _get_next_bit(self):
        """get the next bit of the pseudo-random sequence"""
        feedback = bin(self.reg & self.mask).count('1') % 2
        out_bit = (self.reg >> (self.reg_length - 1)) & 1
        self.reg = ((self.reg << 1) | feedback) & ((1 << self.reg_length) - 1)
        return out_bit

    def process(self, data):
        """take a bytes or bytearray and return the processed result."""
        self.reg = self.initial_seed
        result = bytearray()
        
        for byte in data:
            out_byte = 0
            for i in range(7, -1, -1):
                bit_in = (byte >> i) & 1
                scramble_bit = self._get_next_bit()
                bit_out = bit_in ^ scramble_bit
                out_byte |= (bit_out << i)
            result.append(out_byte)
            
        return bytes(result)

class Scrambler(AdditiveScrambler):
    """Class for transmission"""
    pass

class Unscrambler(AdditiveScrambler):
    """Class for reception (identical to transmission)"""
    pass


if __name__ == "__main__":
    scrambler = Scrambler()
    unscrambler = Unscrambler()
    
    data = b"\x00\x00\x00\x00\x00"
    scrambled_data = scrambler.process(data)
    unscrambled_data = unscrambler.process(scrambled_data)
    
    print(f"Original data: {data}")
    print(f"Scrambled data: {scrambled_data}")
    print(f"Unscrambled data: {unscrambled_data}")
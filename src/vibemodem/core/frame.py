"""The fixed-size Frame: length byte, padded Message and CRC-32, whitened.

A Frame always holds the same number of bytes, so a receiver that has found the start of a
Transmission knows exactly how many symbols to decode.
"""

import zlib

import numpy as np

MESSAGE_CAPACITY = 20
CRC_BYTES = 4
FRAME_BYTES = 1 + MESSAGE_CAPACITY + CRC_BYTES
FRAME_BITS = 8 * FRAME_BYTES


def pseudo_random_bits(count: int, state: int) -> np.ndarray:
    """Bits of a 15-bit linear-feedback shift register (x^15 + x^14 + 1) from a nonzero state."""
    bits = np.empty(count, dtype=np.uint8)
    for index in range(count):
        new = ((state >> 14) ^ (state >> 13)) & 1
        state = ((state << 1) | new) & 0x7FFF
        bits[index] = new
    return bits


# Whitening stops long runs of identical bits (such as the zero padding) from becoming long
# runs of one tone.
_WHITENING = pseudo_random_bits(FRAME_BITS, state=0x1ACE)
_WHITENING.flags.writeable = False


def encode_frame(message: bytes) -> np.ndarray:
    """The FRAME_BITS bits that carry a Message."""
    if len(message) > MESSAGE_CAPACITY:
        raise ValueError(
            f"a Message holds at most {MESSAGE_CAPACITY} bytes in one Frame, got {len(message)}; "
            "longer Messages need to be split into Fragments"
        )
    body = bytes([len(message)]) + message.ljust(MESSAGE_CAPACITY, b"\x00")
    frame = body + zlib.crc32(body).to_bytes(CRC_BYTES, "big")
    return np.unpackbits(np.frombuffer(frame, dtype=np.uint8)) ^ _WHITENING


def decode_frame(bits: np.ndarray) -> bytes | None:
    """The Message in a Frame's bits, or None when the checksum or the length does not fit."""
    frame = np.packbits(bits ^ _WHITENING).tobytes()
    body, checksum = frame[:-CRC_BYTES], frame[-CRC_BYTES:]
    if zlib.crc32(body).to_bytes(CRC_BYTES, "big") != checksum or body[0] > MESSAGE_CAPACITY:
        return None
    return body[1 : 1 + body[0]]

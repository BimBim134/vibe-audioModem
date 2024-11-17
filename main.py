from random import randbytes

from reedsolo import RSCodec
import hashlib

binaryFile = randbytes(1000)

ecc = RSCodec(5)

original_file_hash = hashlib.md5(binaryFile).hexdigest()

print(original_file_hash)
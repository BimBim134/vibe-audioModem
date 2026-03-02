a = '11100001010110101110100010010011'

val = int(a, 2)

b_arr = val.to_bytes(4, byteorder='big')

print(b_arr)

b_arr = list(int(a[i:i+8], 2) for i in range(0, len(a), 8))

print(b_arr)
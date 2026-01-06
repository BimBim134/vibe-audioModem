import pmt
import numpy as np


def bytes_from_file(filepath):
    with open(filepath, "rb") as f:
        input_file = f.read()
    # input_file = np.frombuffer(input_file, dtype=np.uint8)
    payload = pmt.to_pmt({"path": filepath, "data": input_file})
    output = pmt.serialize_str(payload)
    return output


def file_from_bytes(input_bytes):
    payload = pmt.deserialize_str(input_bytes)
    output = pmt.to_python(payload)
    with open("test_" + output["path"], "wb") as file:
        file.write(output["data"])


if __name__ == "__main__":
    filepath = "gardner1986.pdf"
    test = bytes_from_file(filepath)
    file_from_bytes(test)

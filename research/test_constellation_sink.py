import zmq
import numpy as np
import time


def test_receiver():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:5559")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    print("Waiting for constellation points on port 5559...")

    try:
        while True:
            if socket.poll(1000):
                data = socket.recv()
                points = np.frombuffer(data, dtype=np.complex64)
                print(f"Received {len(points)} constellation points")
                print(f"First 5 points: {points[:5]}")
            else:
                print("No data received yet...")
                time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping test script.")
    finally:
        socket.close()
        context.term()


if __name__ == "__main__":
    test_receiver()

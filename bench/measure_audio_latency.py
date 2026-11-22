"""Round-trip latency of a sound card: a click played on the output and heard on the input.

Plug the output of the interface into its own input (a cable, or the loopback of the interface)
and run, for example:

    uv run python bench/measure_audio_latency.py --input 1 --output 1

The result is the delay TX blanking has to cover on that machine, besides the margin for the tail
of the radio. Write it down in `docs/measurements/audio-latency.md`.
"""

import argparse

import numpy as np
import sounddevice as sd

from vibemodem.core.coded_modem import SAMPLE_RATE


def measure(input_device, output_device, repeats: int) -> list[float]:
    click = np.zeros(SAMPLE_RATE, dtype=np.float32)
    click[SAMPLE_RATE // 2 : SAMPLE_RATE // 2 + 48] = 0.8  # 1 ms, half a second in
    delays = []
    for _ in range(repeats):
        heard = sd.playrec(
            click.reshape(-1, 1),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=(input_device, output_device),
        )
        sd.wait()
        position = int(np.argmax(np.abs(heard[:, 0])))
        if abs(heard[position, 0]) < 0.05:
            raise SystemExit("nothing heard: check the cable and the levels")
        delays.append((position - SAMPLE_RATE // 2) / SAMPLE_RATE * 1000)
    return delays


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=int, default=None)
    parser.add_argument("--output", type=int, default=None)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    delays = measure(args.input, args.output, args.repeats)
    print(
        f"round trip: min {min(delays):.1f} ms, median {np.median(delays):.1f} ms, "
        f"max {max(delays):.1f} ms over {len(delays)} runs"
    )
    stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, device=args.output)
    print(f"output latency reported by the library: {stream.latency * 1000:.1f} ms")
    stream.close()


if __name__ == "__main__":
    main()

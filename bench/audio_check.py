"""Try the sound card by hand: list devices, check an input's level, or send a Message through.

    python -m bench.audio_check --list
    python -m bench.audio_check --input Scarlett --level 3
    python -m bench.audio_check --input Scarlett --output default --preset fast --message bonjour

The last one plays a Transmission on the output while listening on the input, then receives
what was heard: an audio cable from the output to the input, or a loudspeaker in front of a
microphone, shows whether the whole chain works.
"""

import argparse
import time

import numpy as np

from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.core.message import random_message_id
from vibemodem.core.transmission import receive, transmit
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.io.audio import Audio, AudioError, SoundCard
from vibemodem.io.levels import check_level

BLOCK_SECONDS = 0.5
TAIL_SECONDS = 1.5  # kept listening after the last sound, for the room and the cables


def print_devices(audio: Audio) -> None:
    for d in audio.list_devices():
        directions = ("in " if d.inputs else "   ") + ("out" if d.outputs else "   ")
        print(f"{d.index:3d}  {directions}  {d.rate_hz:6.0f} Hz  {d.name}")


def print_level(audio: Audio, device, seconds: float) -> None:
    report = check_level(audio.record(seconds, device=device))
    print(f"peak {report.peak:.3f}, level {report.rms_dbfs:.1f} dBFS")
    print("\n".join(report.messages) or "the level looks fine")


def send_through(
    audio: Audio, *, output, input, preset: str, message: bytes, tail_seconds: float = TAIL_SECONDS
) -> bool:
    """Play a Transmission, listen meanwhile, and say what was received."""
    modem = TurboModem(preset=preset)
    sound = transmit(modem, message, preset, msg_id=random_message_id(), copies=1)
    needed = int((sound.size / SAMPLE_RATE + tail_seconds) / BLOCK_SECONDS) + 8
    with audio.listen(device=input, block_seconds=BLOCK_SECONDS, capacity=needed) as heard:
        print(f"playing {sound.size / SAMPLE_RATE:.1f} s of sound...")
        audio.play(sound, device=output)
        time.sleep(tail_seconds)  # still listening: the room and the cables take a moment
        heard.close()
    blocks = list(heard)
    recording = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
    print(f"heard {recording.size / SAMPLE_RATE:.1f} s, {heard.dropped} blocks lost")
    if recording.size:
        report = check_level(recording)
        print(f"peak {report.peak:.3f}, level {report.rms_dbfs:.1f} dBFS")
        print("\n".join(report.messages))
    received = receive(modem, recording)
    for done in received.complete:
        print(f"RECEIVED: {done.message!r}")
    for part in received.incomplete:
        print(f"incomplete: Fragments {sorted(part.fragments)} of {part.total} heard")
    ok = any(done.message == message for done in received.complete)
    print("it works" if ok else "nothing was received: check the levels and the connection")
    return ok


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Try the sound card by hand.")
    parser.add_argument("--list", action="store_true", help="list the audio devices and stop")
    parser.add_argument("--input", help="input device: a number or part of its name")
    parser.add_argument("--output", help="output device: a number or part of its name")
    parser.add_argument("--level", type=float, metavar="SECONDS", help="check the input level")
    parser.add_argument("--preset", default="fast", choices=["max-range", "standard", "fast"])
    parser.add_argument("--message", default="bonjour", help="the Message to send through")
    args = parser.parse_args(argv)

    def number(text):
        return int(text) if text is not None and text.isdigit() else text

    audio = SoundCard()
    try:
        if args.list:
            print_devices(audio)
        elif args.level:
            print_level(audio, number(args.input), args.level)
        else:
            send_through(
                audio,
                output=number(args.output),
                input=number(args.input),
                preset=args.preset,
                message=args.message.encode(),
            )
    except (AudioError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()

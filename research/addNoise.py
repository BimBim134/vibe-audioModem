#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

import numpy as np
from scipy.io import wavfile


def add_noise(input_file: Path, snr: float, output_file: Path | None = None) -> None:
    sample_rate, data = wavfile.read(input_file)
    if data.ndim > 1:
        data = np.mean(data, axis=1).astype(data.dtype)

    data = data.astype(np.float64)
    signal_power = np.mean(data ** 2)
    noise_power = signal_power / snr
    noise_std = np.sqrt(noise_power)
    noise = np.random.normal(0, noise_std, data.shape)
    noisy = data + noise

    lead_in = np.random.normal(0, noise_std, sample_rate)
    noisy = np.concatenate([lead_in, noisy])

    peak = np.max(np.abs(noisy))
    if peak > 32767:
        noisy = noisy * (32767 / peak)

    output = output_file or input_file.with_stem(input_file.stem + "_noisy")
    wavfile.write(str(output), sample_rate, noisy.astype(np.int16))


def main(input_file: Path, snr: float) -> None:
    temp_output = input_file.with_stem(input_file.stem + "_noisy")
    add_noise(input_file, snr, output_file=temp_output)
    import os
    os.replace(temp_output, input_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add noise to WAV file at desired SNR")
    parser.add_argument("-f", "--file", required=True, help="input file")
    parser.add_argument("-s", "--snr", required=True, type=float, help="desired SNR")
    args = parser.parse_args()
    main(Path(args.file), args.snr)

# transmitter
```mermaid
flowchart TD
    binary[binary file]
    chuncks([chuncks])
    packet@{shape: procs, label: "[ID, LENGTH, DATA]"}
    encoder([RSC encoder])
    encoded_packet@{shape: procs, label: "encoded packets"}
    protocol([protocol formatting])
    access@{shape: text, label: access key}
    FEC([Forward Error Correction])
    const_mod([consteallation modulator])
    upconvert([up-conversion])
    audio[audio out]

    preamble -- bytes --> chuncks
    binary -- bytes --> chuncks
    postamble -- bytes --> chuncks
    chuncks -- bytes arrays --> packet
    packet -- bytes arrays --> encoder
    encoder -- bytes arrays --> encoded_packet
    access -- bytes --> protocol
    encoded_packet -- bytes --> protocol
    protocol -- bytes --> FEC
    FEC -- bytes --> const_mod
    const_mod -- complex128 --> upconvert
    upconvert -- float --> audio
```
 
# listenning

stream from soundcard

peak detection

when peak detected:
    launch receiver

# receiver

stream from soundcard

converting to complex : hilbert transform

automatic gain control

down converting to baseband signal

lienar equalizatiion

costa loop

constellation decoder

FEC decoder
    convolutionnal code

access code correlation, packet synchronization and protocol parsing

filter out preamble and postamble

reed solomon decoding of each packet

binary file reconstitution
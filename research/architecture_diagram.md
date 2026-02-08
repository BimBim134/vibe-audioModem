# Vibe architecture
## Receiver
### Diagram
```mermaid
flowchart LR
IN@{ shape: circle, label: "Audio IN"}
LST[Listenner]
FFT
PD[Peak detector]
DM@{shape: procs, label: "Demodulators"}
P2B[Packet Decoder]
DB@{ shape: lin-cyl, label: "Messages Database"}

subgraph UI
Waterfall@{ shape: curv-trap, label: "Waterfall"}
Messages@{ shape: curv-trap, label: "Messages"}
end

AUDIO_data@{ shape: f-circ}
FFT_data@{ shape: f-circ}
MESSAGES_data@{ shape: f-circ}

LST ---|5555| AUDIO_data
FFT ---|5556| FFT_data --> PD
DM  ---|5557| P2B
P2B ---|5558| MESSAGES_data --> Messages & DB

IN ==> LST
AUDIO_data --> FFT & DM
FFT_data --> Waterfall
PD -.- DM
```

### port description
| port number |  stream description   |     data type      |
| :---------- | :-------------------: | :----------------: |
| 5555        |     Audio stream      |       float        |
| 5556        |      FFT stream       |   complex vector   |
| 5557        |      Raw packets      |       bytes        |
| 5558        | Deserialized messages | json + binary blob |

### Nodes description
| Node                 |                                             function                                             |   input    |  output   |
| :------------------- | :----------------------------------------------------------------------------------------------: | :--------: | :-------: |
| Audio IN + Listenner |                                 Gets Audio stream from soundcard                                 | Sound Card | port 5555 |
| FFF                  |                                 Compute the FFT of audio stream                                  | port 5555  | port 5556 |
| Peak Detector        | Analyze the spectrum and start a demodulator when and where a incomming transmission is detected | port 5556  |           |
| Demodulators         |             Initialized by the peak detector, demodulate and incomming transmission              | port 5555  | port 5557 |
| Packet Decoder       |                          convert raw packet into deserialized messages                           | port 5557  | port 5558 |
| Messages Database    |                                Store all messages into a database                                | port 5558  |           |



## Transmitter
```mermaid
flowchart LR
OUT@{ shape: circle, label: "Audio OUT"}
MD[Modulator]
DB@{ shape: lin-cyl, label: "Messages Database"}

subgraph UI
direction LR
Message["Message entry"]
Settings
end

UI -----|5558| DB

UI ---> MD ==> OUT

```
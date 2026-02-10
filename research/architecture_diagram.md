# Vibe architecture
## Receiver
### Diagram
```mermaid
flowchart LR
PD[Peak detector]
DM@{shape: procs, label: "Demodulators"}
P2B[Packet Decoder]
DB@{ shape: lin-cyl, label: "Messages Database"}

subgraph UI
Waterfall@{ shape: curv-trap, label: "Waterfall"}
Messages@{ shape: curv-trap, label: "Messages"}
end

subgraph AI[Audio Interface]
direction LR
IN@{ shape: circle, label: "Audio IN"}
FFT
end

FFT_data@{ shape: f-circ}
MESSAGES_data@{ shape: f-circ}

AI ---|"5555 audio : (float)"| DM
AI ----|"5556 FFT : (complex)"| FFT_data --> PD
DM  ---|"5557 packet : vibe packet (bytes)"| P2B
P2B ---|"5558 formatted messages (json)"| MESSAGES_data --> Messages & DB

IN --> FFT
FFT_data --> Waterfall
PD -.- DM
```

### port description
| port number |  stream description   |   data type    |
| :---------- | :-------------------: | :------------: |
| 5555        |     Audio stream      |     float      |
| 5556        |      FFT stream       | complex vector |
| 5557        |      Raw packets      |     bytes      |
| 5558        | Deserialized messages |      json      |

### Nodes description
| Node              |                                                function                                                 |   input   |      output      |
| :---------------- | :-----------------------------------------------------------------------------------------------------: | :-------: | :--------------: |
| Audio interface   | Gets input audio stream from sound card and computes its FFT. Provides audio and FFT on separated ports |           | ports 5555, 5556 |
| Peak Detector     |    Analyze the spectrum and start a demodulator when and where a incomming transmission is detected     | port 5556 |                  |
| Demodulators      |                 Initialized by the peak detector, demodulate and incomming transmission                 | port 5555 |    port 5557     |
| Packet Decoder    |                              convert raw packet into deserialized messages                              | port 5557 |    port 5558     |
| Messages Database |                                   Store all messages into a database                                    | port 5558 |                  |

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
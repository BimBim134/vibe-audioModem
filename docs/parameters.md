# settings
## packet configuration
### details
| setting                      | value |  unit  |
| :--------------------------- | :---: | :----: |
| total packet lenght          |  64  |  bit   |
| pramble packets              |   1   | packet |
| postamble packets            |   1   | packet |
| error correction code length |  32   |  bit   |

### single packet description
```mermaid
packet
+1:"flag"
+31:"data"
+32:"Reed Solomon error code"
```
## signal configuration
### details
| setting         | value |   unit   |
| :-------------- | :---: | :------: |
| sampling rate   | 48000 | sample/s |
| beeper duration |   3   | seconds  |
| baud            |  200  |   baud   |
| constellation   | BPSK  |    /     |

## ports configuration
| port description            | port |
| :-------------------------- | :--: |
| audio                       | 5555 |
| fft                         | 5556 |
| raw packet                  | 5557 |
| messages                    | 5558 |
| modem configuration         | 5559 |
| peak detector configuration | 5560 |

## process connection
```mermaid
flowchart TD
AIF["audio<br>interface"]
PDT["peak<br>detector"]
PDC["packet<br>decoder"]
CLI["modem<br>CLI"]
DM@{label: demodulator, shape: procs}
MD["audio<br>modem"]
TX[transmitter]

CLI ----->|"5559<br>configuration"| MD
AIF -->|"5557<br>fft"| PDT
AIF -->|"5555<br>audio"| DM
DM  -->|"5557<br>raw packet"| PDC
PDC -->|"5558<br>messages"| MD
MD  -->|"5560<br>configuration"| PDT
MD  -.->|"python<br>import"| TX
PDT -.->|"python<br>import"| DM
```
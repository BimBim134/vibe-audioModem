# Packet Decoding Process

This document explains the packet decoding and reassembly process in `src/rx/packet_decoding.py`.

## Data Flow Overview

The packet decoder acts as a central sink for decoded PDUs (Protocol Data Units) coming from one or more `Demodulator` workers.

```mermaid
graph TD
    subgraph Demodulator Workers
        D1[Demodulator 1]
        D2[Demodulator 2]
        DN[Demodulator N]
    end

    subgraph Packet Decoder
        Z[ZMQ SUB Socket - Bind]
        L[Listen Loop]
        DP[decode_packet]
        PR{PacketReassembler}
        DES[PMT Deserialization]
    end

    D1 -- Connect --> Z
    D2 -- Connect --> Z
    DN -- Connect --> Z
    Z --> L
    L -- pmt.to_python --> DP
    DP -- RS Decode --> PR
    PR -- Collecting --> PR
    PR -- Postamble --> DES
    DES -- Success --> Log[Final Message Logged]
```

## PacketReassembler State Machine

The `PacketReassembler` handles messages that span multiple physical packets. It uses the `packet_len` flag (the first byte of the data chunk) to manage state.

- **Preamble (`len=0`)**: Resets the buffer and enters `COLLECTING` state.
- **Data (`0 < len < 255`)**: Appends the specified number of bytes to the buffer.
- **Postamble (`len=255`)**: Triggers deserialization of the accumulated buffer and returns to `IDLE`.

```mermaid
sequenceDiagram
    participant T as Transmitter
    participant D as Demodulator
    participant PR as PacketReassembler
    participant O as Output (PMT)

    Note over T,O: Multi-packet Burst Transmission
    T->>D: Packet 1: Preamble (len=0)
    D->>PR: process_packet(len=0)
    PR-->>PR: reset() & state=COLLECTING
    
    T->>D: Packet 2: Data (len=N)
    D->>PR: process_packet(len=N)
    PR-->>PR: append(data)
    
    T->>D: Packet 3: Data (len=M)
    D->>PR: process_packet(len=M)
    PR-->>PR: append(data)
    
    T->>D: Packet 4: Postamble (len=255)
    D->>PR: process_packet(len=255)
    PR->>PR: deserialize(buffer)
    PR->>O: Return PMT Object
    PR-->>PR: reset() & state=IDLE
```

## Implementation Details

- **RS Decoding**: Each raw packet is first passed through a Reed-Solomon decoder ($n=255, k=243, t=6$).
- **Multi-Source Support**: The decoder maintains a dictionary of `PacketReassembler` instances, keyed by `demodulator_id`. This allows interleaved packets from different sources to be reassembled correctly.
- **Deserialization**: Once a postamble is received, the entire buffer is passed to `pmt.deserialize_str` and then converted to a Python dictionary using `pmt.to_python`.
- **ZMQ Architecture**: The `Packet Decoder` binds to the ZMQ port (`SUB`), while the `Demodulator` workers connect to it. This allows a single decoder to aggregate packets from multiple transient workers.
- **Data Type Handling**: Python's `pmt.to_python` returns data buffers as `numpy.ndarray`. The decoder logic converts these back to `bytes` via `.tobytes()` before performing UTF-8 string decoding to ensure compatibility.

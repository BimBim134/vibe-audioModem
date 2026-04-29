# Plan: Implement TODO Chapter 2 (Audio Modem & HTTP Server Commands)

## User Clarifications
1. `POST /receive` restarts receiver with new `nb_workers` if already active
2. Port config changes require restarting `ModemController` ZMQ sockets (`config_pub_socket`, `messages_sub_socket`)
3. `GET /configuration` must include port config section

## Step 1: Refactor `ModemController` for Dynamic Lifecycle
**File**: `src/audioModem/audioModem.py`
- Remove static process dicts (lines 32-60: `AUDIO_INTERFACE`, `PEAK_DETECTOR`, `PACKET_DECODER`)
- Add to `__init__` (after line 73):
  - `self.receiver_active = False`
  - `self.receiver_nb_workers = 1` (default from TODO 2.1)
  - `self.receiver_processes = []` (tracks receiver subprocesses)
- Add new methods:
  - `_restart_zmq_sockets()`:
    - Close existing `config_pub_socket` (line 85) and `_messages_sub_socket` (line 88)
    - Rebind to updated `self.ports_conf.config_port`/`messages_port`
  - `_stop_receiver_processes()`:
    - Set `STOP_EVENT`, join all receiver processes, clear `STOP_EVENT`, reset `receiver_active`/`receiver_processes`
  - `_start_receiver_processes(nb_workers)`:
    - If `receiver_active`, call `_stop_receiver_processes()` first
    - Launch 3 receiver processes:
      - `AudioInterface`: target `start_audio_interface`, pass `STOP_EVENT`
      - `PeakDetector`: target `search_for_incomming_transmission`, pass `nb_workers` kwarg (matches `src/rx/peak_detector.py:112`)
      - `PacketDecoder`: target `listen_for_packets`, pass `STOP_EVENT`
    - Append to `self.receiver_processes`, set `self.receiver_active = True`
- Update `shutdown()` (line 316): Call `_stop_receiver_processes()` before existing ZMQ/thread cleanup

## Step 2: Add TODO-Mandated Handlers to `ModemController`
**File**: `src/audioModem/audioModem.py`
- `handle_receive(data)`: Read optional `nb_workers` (default 1), call `_start_receiver_processes(nb_workers)`, return status
- `handle_setup(data)`: Parse `signal`/`packet`/`port` JSON sections (TODO 2.1 lines 35-59), update configs, call `_restart_zmq_sockets()` if ports changed, restart receiver if active, return full config with ports
- `handle_stop(data)`: Accept `rx`/`tx` flags: `rx=True` calls `_stop_receiver_processes()`, `tx=True` calls existing `cancel_queue()` (line 300)
- `handle_quit(data)`: Set global `STOP_EVENT` to trigger full shutdown
- Update `handle_get_config` (line 272): Add `port` section with all `PortsConfig` fields

## Step 3: Overhaul HTTP Server to Match TODO Spec
**File**: `src/audioModem/http_server.py`
- **Add POST endpoints (TODO 2.1)**:
  - `POST /receive`: Forward to `handle_receive`, accept optional `nb_workers`
  - `POST /setup`: Forward request JSON to `handle_setup`
  - `POST /stop`: Forward to `handle_stop`, accept `rx`/`tx` flags
  - `POST /quit`: Forward to `handle_quit`
- **Update/Add GET endpoints (TODO 2.2)**:
  - Rename `GET /config` (line 26) to `GET /configuration`
  - Add `GET /fft`: Connect to `fft_port`, poll 1s for snapshot, return FFT data as list (snapshot only per user note)
  - Add `GET /logs`: Read last 100 lines of `audiomodem.log`, return as list
  - Keep existing `GET /messages` (line 54)
- **Remove non-TODO endpoints**: Delete `POST /preset`, `POST /carrier`, `POST /cancel`

## Step 4: Update `start_audiomodem` Entry Point
**File**: `src/audioModem/audioModem.py` (line 331)
- Remove static receiver process launch (lines 348-352)
- Keep flow: Init controller → set controller in HTTP server → start HTTP thread → wait for `STOP_EVENT` → call `controller.shutdown()`

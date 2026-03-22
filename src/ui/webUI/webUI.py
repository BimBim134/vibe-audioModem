import sys
import asyncio
import time
import os
import logging
import json
import threading

import zmq
import zmq.asyncio
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

from src.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
)
from src.config import (
    SignalConfig,
    PortsConfig,
    PacketConfig,
    MODULATION_PRESETS,
)
from src.tx.transmitter import send_data

import pmt
from datetime import datetime
from copy import copy, deepcopy

logger = logging.getLogger(__name__)

app = FastAPI()

# Configuration
SPECTROGRAM_REFRESH_RATE = 20

# Application state
signal_conf = deepcopy(DEFAULT_SIGNAL_CONFIG)
ports_conf = DEFAULT_PORTS_CONFIG
pkt_conf = DEFAULT_PACKET_CONFIG

# ZMQ Context for config publisher
ctx = zmq.Context()
config_pub_socket = None

# Shutdown event for graceful WebSocket closure
shutdown_event = None

# 1. On lit le fichier HTML depuis le dossier assets
current_dir = os.path.dirname(os.path.abspath(__file__))
index_path = os.path.join(current_dir, "assets", "index.html")

with open(index_path, "r", encoding="utf-8") as f:
    HTML_PAGE = f.read()


# 2. Les routes HTTP
@app.get("/")
async def get_webpage():
    return HTMLResponse(HTML_PAGE)


@app.get("/scripts.js")
async def get_scripts():
    return FileResponse(os.path.join(current_dir, "assets", "scripts.js"))


@app.get("/stylesheet.css")
async def get_stylesheet():
    return FileResponse(os.path.join(current_dir, "assets", "stylesheet.css"))


# 3. WebSocket bridge
async def listen_to_zmq(sock, websocket, prefix, transform=None):
    try:
        while True:
            raw_data = await sock.recv()
            if transform:
                data = transform(raw_data)
                if data is not None:
                    await websocket.send_bytes(prefix + data.tobytes())
            else:
                await websocket.send_bytes(prefix + raw_data)
    except Exception as e:
        logger.error(f"Error in listen_to_zmq ({prefix}): {e}")
    finally:
        sock.close()


# 4. HTTP endpoints for configuration
@app.post("/api/carrier_freq")
async def set_carrier_freq(request: Request):
    global signal_conf
    data = await request.json()
    carrier_freq = data.get("carrier_freq")
    if carrier_freq is not None:
        signal_conf.carrier_freq = float(carrier_freq)
        logger.info(f"Carrier frequency updated to {carrier_freq} Hz")
        return JSONResponse({"status": "ok", "carrier_freq": signal_conf.carrier_freq})
    return JSONResponse({"status": "error", "message": "carrier_freq required"}, status_code=400)


@app.post("/api/modulation_preset")
async def set_modulation_preset(request: Request):
    global signal_conf, config_pub_socket
    data = await request.json()
    preset_name = data.get("preset")
    
    if preset_name and preset_name in MODULATION_PRESETS:
        preset = MODULATION_PRESETS[preset_name]
        signal_conf.baudrate = preset.baudrate
        signal_conf.modulation_preset = preset_name
        
        # Broadcast preset to GNU Radio flowgraph
        if config_pub_socket:
            try:
                config_pub_socket.send_string(f"PRESET:{preset_name}")
            except Exception as e:
                logger.error(f"Failed to send preset: {e}")
        
        logger.info(f"Modulation preset updated to {preset_name}: baudrate={preset.baudrate}")
        return JSONResponse({"status": "ok", "preset": preset_name, "baudrate": preset.baudrate})
    
    return JSONResponse({"status": "error", "message": "Invalid preset"}, status_code=400)


@app.get("/api/config")
async def get_config():
    return JSONResponse({
        "carrier_freq": signal_conf.carrier_freq,
        "baudrate": signal_conf.baudrate,
        "modulation_preset": signal_conf.modulation_preset,
        "samp_rate": signal_conf.samp_rate,
    })


@app.post("/api/transmit")
async def transmit_message(request: Request):
    global signal_conf, pkt_conf, config_pub_socket
    data = await request.json()
    message_text = data.get("message", "")
    sender_name = data.get("sender_name", "Me")
    
    if not message_text:
        return JSONResponse({"status": "error", "message": "Message is required"}, status_code=400)
    
    logger.info(f"Starting transmission: {message_text} (Sender: {sender_name})")
    
    # Broadcast preset to GNU Radio flowgraph
    if config_pub_socket:
        try:
            config_pub_socket.send_string(f"PRESET:{signal_conf.modulation_preset}")
        except Exception as e:
            logger.error(f"Failed to send preset: {e}")
    
    # Run transmission in a separate thread
    def transmit():
        try:
            send_data(
                message_text, 
                pkt=pkt_conf, 
                sig=signal_conf, 
                sender_name=sender_name, 
                handle_signals=False
            )
            logger.info("Transmission finished")
        except Exception as e:
            logger.error(f"Transmission error: {e}")
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, transmit)
    
    # Return the message info for display
    date_str = datetime.now().strftime("%H:%M:%S")
    freq = f"{signal_conf.carrier_freq:.0f} Hz"
    
    return JSONResponse({
        "status": "ok",
        "message": message_text,
        "sender": sender_name,
        "meta": freq + " — " + date_str,
        "type": "sent"
    })


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global shutdown_event
    await websocket.accept()
    logger.info("Client web connecté.")

    ctx = zmq.asyncio.Context.instance()

    # FFT Socket
    fft_sock = ctx.socket(zmq.SUB)
    fft_sock.connect(f"tcp://127.0.0.1:{ports_conf.fft_port}")
    fft_sock.setsockopt(zmq.SUBSCRIBE, b"")

    # Messages Socket (for received messages)
    msg_sock = ctx.socket(zmq.SUB)
    msg_sock.connect(f"tcp://127.0.0.1:{ports_conf.messages_port}")
    msg_sock.setsockopt(zmq.SUBSCRIBE, b"")

    # Peak detector system messages Socket
    peak_system_sock = ctx.socket(zmq.SUB)
    peak_system_sock.connect(f"tcp://127.0.0.1:{ports_conf.peak_detector_system_port}")
    peak_system_sock.setsockopt(zmq.SUBSCRIBE, b"")

    last_spectro_time = 0.0

    async def fft_handler():
        nonlocal last_spectro_time
        try:
            while True:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    raw_data = await asyncio.wait_for(fft_sock.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                mag_array = np.frombuffer(raw_data, dtype=np.float32)

                if len(mag_array) != ports_conf.fft_size:
                    mag_array = mag_array[-ports_conf.fft_size :]

                mag_array = mag_array[ports_conf.half_fft_size :]
                db_array = 20 * np.log10(mag_array + 1e-12)

                # Type 0x01: FFT dB
                await websocket.send_bytes(b"\x01" + db_array.tobytes())

                # Type 0x02: Waterfall (Uint8)
                now = time.time()
                if now - last_spectro_time >= 1 / SPECTROGRAM_REFRESH_RATE:
                    last_spectro_time = now
                    v_min, v_max = -80, 80
                    fft_norm = np.clip(
                        (db_array - v_min) / (v_max - v_min) * 255, 0, 255
                    ).astype(np.uint8)
                    await websocket.send_bytes(b"\x02" + fft_norm.tobytes())
        except Exception as e:
            logger.error(f"Error in fft_handler: {e}")

    async def message_handler():
        try:
            while True:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    raw_data = await asyncio.wait_for(msg_sock.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                try:
                    payload = pmt.to_python(pmt.deserialize_str(raw_data))
                    if isinstance(payload, dict):
                        msg_json = json.dumps(payload)
                        msg_type = payload.get("type")
                        if msg_type == "system":
                            await websocket.send_bytes(b"\x03" + msg_json.encode('utf-8'))
                        elif msg_type == "data":
                            await websocket.send_bytes(b"\x04" + msg_json.encode('utf-8'))
                except Exception as e:
                    logger.error(f"Error in message_handler: {e}")
        except Exception as e:
            logger.error(f"Error in message_handler: {e}")

    async def peak_system_handler():
        try:
            while True:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    raw_data = await asyncio.wait_for(peak_system_sock.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                try:
                    payload = pmt.to_python(pmt.deserialize_str(raw_data))
                    if isinstance(payload, dict):
                        msg_json = json.dumps(payload)
                        if payload.get("type") == "system":
                            await websocket.send_bytes(b"\x03" + msg_json.encode('utf-8'))
                except Exception as e:
                    logger.error(f"Error in peak_system_handler: {e}")
        except Exception as e:
            logger.error(f"Error in peak_system_handler: {e}")

    async def sender():
        try:
            while True:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    data = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                # Handle incoming binary data if needed
                # Currently we use HTTP for sending, but could add WebSocket support
        except Exception as e:
            logger.error(f"Error in sender: {e}")

    try:
        await asyncio.gather(fft_handler(), message_handler(), peak_system_handler(), sender())
    except WebSocketDisconnect:
        logger.info("Client web déconnecté.")
    finally:
        fft_sock.close()
        msg_sock.close()
        peak_system_sock.close()


def start_dashboard(stop_event=None):
    """Lancement du serveur."""
    global config_pub_socket, shutdown_event
    
    # Initialize config publisher
    config_pub_socket = ctx.socket(zmq.PUB)
    try:
        config_pub_socket.bind(f"tcp://127.0.0.1:{ports_conf.config_port}")
        logger.info(f"Config publisher bound to port {ports_conf.config_port}")
    except Exception as e:
        logger.error(f"Failed to bind config publisher: {e}")
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    shutdown_event = asyncio.Event()

    if stop_event is not None:
        def monitor_stop_event():
            stop_event.wait()
            logger.info("WebUI: stop_event received, initiating shutdown")
            shutdown_event.set()
            server.should_exit = True
        monitor_thread = threading.Thread(target=monitor_stop_event, daemon=True)
        monitor_thread.start()

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("WebUI: KeyboardInterrupt received, shutting down")
        shutdown_event.set()
        server.should_exit = True


if __name__ == "__main__":
    start_dashboard()

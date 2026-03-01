import sys
import asyncio
import time
import os
import logging

import zmq
import zmq.asyncio
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse

from src.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
)
from src.config import (
    SignalConfig,
    PortsConfig,
    PacketConfig,
)

logger = logging.getLogger(__name__)

app = FastAPI()

# Configuration
SPECTROGRAM_REFRESH_RATE = 20

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


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
):
    await websocket.accept()
    logger.info("Client web connecté.")

    ctx = zmq.asyncio.Context.instance()

    # FFT Socket
    fft_sock = ctx.socket(zmq.SUB)
    fft_sock.connect(f"tcp://127.0.0.1:{ports_conf.fft_port}")
    fft_sock.setsockopt(zmq.SUBSCRIBE, b"")

    # Constellation Socket
    const_sock = ctx.socket(zmq.SUB)
    const_sock.connect(f"tcp://127.0.0.1:{ports_conf.constellation_port}")
    const_sock.setsockopt(zmq.SUBSCRIBE, b"")

    last_spectro_time = 0.0

    async def fft_handler():
        nonlocal last_spectro_time
        try:
            while True:
                raw_data = await fft_sock.recv()
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

    async def constellation_handler():
        try:
            while True:
                raw_data = await const_sock.recv()
                # Points are complex64 (2x float32)
                # We forward them directly as bytes with prefix 0x03
                await websocket.send_bytes(b"\x03" + raw_data)
        except Exception as e:
            logger.error(f"Error in constellation_handler: {e}")

    try:
        await asyncio.gather(fft_handler(), constellation_handler())
    except WebSocketDisconnect:
        logger.info("Client web déconnecté.")
    finally:
        fft_sock.close()
        const_sock.close()


def start_dashboard(stop_event=None):
    """Lancement du serveur."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    start_dashboard()

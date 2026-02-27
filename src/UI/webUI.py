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
SPECTROGRAM_REFRESH_RATE = 0.1

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
    sock = ctx.socket(zmq.SUB)
    sock.connect(f"tcp://127.0.0.1:{ports_conf.fft_port}")
    sock.setsockopt(zmq.SUBSCRIBE, b"")

    last_spectro_time = 0.0

    try:
        while True:
            raw_data = await sock.recv()

            # Conversion des données reçues (Magnitude brute)
            mag_array = np.frombuffer(raw_data, dtype=np.float32)

            # Résilience : si on reçoit plus d'une FFT (ex: deux messages concaténés), on ne garde que la dernière
            if len(mag_array) != ports_conf.fft_size:
                mag_array = mag_array[-ports_conf.fft_size :]

            # On ne garde que la partie positive du spectre (la seconde moitié)
            # car le bloc FFT de GNU Radio est décalé (fftshift=True).
            mag_array = mag_array[ports_conf.half_fft_size :]

            # Calcul du dB : 20 * log10(mag)
            db_array = 20 * np.log10(mag_array + 1e-12)

            # Message type 0x01: FFT en dB pour le scope
            await websocket.send_bytes(b"\x01" + db_array.tobytes())

            # Message type 0x02: Normalized FFT (Uint8) pour le waterfall (10Hz)
            now = time.time()
            if now - last_spectro_time >= SPECTROGRAM_REFRESH_RATE:
                last_spectro_time = now

                v_min = -120
                v_max = 0
                fft_norm = np.clip(
                    (db_array - v_min) / (v_max - v_min) * 255, 0, 255
                ).astype(np.uint8)
                await websocket.send_bytes(b"\x02" + fft_norm.tobytes())

    except WebSocketDisconnect:
        logger.info("Client web déconnecté.")
    finally:
        sock.close()


def start_dashboard(stop_event=None):
    """Lancement du serveur."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    start_dashboard()

import asyncio
import zmq
import zmq.asyncio
import numpy as np
import time
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import os

app = FastAPI()

# Configuration
ZMQ_URL = "tcp://127.0.0.1:5556"
SPECTROGRAM_REFRESH_RATE = 1.0

# 1. On lit le fichier HTML depuis le dossier assets
current_dir = os.path.dirname(os.path.abspath(__file__))
index_path = os.path.join(current_dir, "assets", "index.html")

with open(index_path, "r", encoding="utf-8") as f:
    HTML_PAGE = f.read()


# 2. La route HTTP classique : sert la page Web
@app.get("/")
async def get_webpage():
    return HTMLResponse(HTML_PAGE)


@app.get("/scripts.js")
async def get_scripts():
    return FileResponse(os.path.join(current_dir, "assets", "scripts.js"))


@app.get("/stylesheet.css")
async def get_stylesheet():
    return FileResponse(os.path.join(current_dir, "assets", "stylesheet.css"))


# 3. La route WebSocket : gère le pont ZMQ -> Web en temps réel
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client web connecté.")

    ctx = zmq.asyncio.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(ZMQ_URL)
    sock.setsockopt(zmq.SUBSCRIBE, b"")

    last_spectro_time = 0.0

    try:
        while True:
            raw_data = await sock.recv()

            # Envoi binaire rapide
            await websocket.send_bytes(b"\x01" + raw_data)

            # Traitement lent (1Hz)
            now = time.time()
            if now - last_spectro_time >= SPECTROGRAM_REFRESH_RATE:
                last_spectro_time = now
                fft_array = np.frombuffer(raw_data, dtype=np.float32)
                fft_norm = np.clip((fft_array + 100) / 100 * 255, 0, 255).astype(
                    np.uint8
                )
                await websocket.send_bytes(b"\x02" + fft_norm.tobytes())

    except WebSocketDisconnect:
        print("Client web déconnecté.")
    finally:
        sock.close()


def start_dashboard(stop_event=None):
    """Lancement du serveur unifié."""
    # Note: On ignore stop_event pour uvicorn car il bloque,
    # mais le parent s'occupera de tuer le process.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    start_dashboard()

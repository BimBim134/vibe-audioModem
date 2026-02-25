import asyncio
import zmq
import zmq.asyncio
import numpy as np
import time
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

# Configuration
ZMQ_URL = "tcp://127.0.0.1:5556"
SPECTROGRAM_REFRESH_RATE = 1.0

# 1. On stocke le HTML/JS dans une chaîne (ou on le lit depuis un fichier index.html)
# C'est le code exact de notre message précédent, j'ai juste mis à jour l'URL du WebSocket
HTML_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>SDR Web Display</title>
    <link rel="stylesheet" href="https://unpkg.com/uplot/dist/uPlot.min.css">
    <script src="https://unpkg.com/uplot/dist/uPlot.iife.min.js"></script>
    <style>
        body { font-family: sans-serif; background-color: #1e1e1e; color: #fff; padding: 20px; }
        .container { max-width: 1000px; margin: auto; }
        canvas { display: block; width: 100%; border: 1px solid #444; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Spectroscope (Temps Réel)</h2>
        <div id="spectroscope-div"></div>
        <h2>Spectrogramme (1 Hz)</h2>
        <canvas id="spectrogram-canvas" width="4096" height="300"></canvas>
    </div>
    <script>
        const FFT_SIZE = 4096;
        const xData = new Float32Array(FFT_SIZE);
        for(let i = 0; i < FFT_SIZE; i++) xData[i] = i;

        const uplotOpts = { width: 1000, height: 250, scales: { x: { time: false }, y: { min: -100, max: 0 } }, series: [ {}, { stroke: "#00ff00", width: 1 } ], axes: [ { stroke: "#ccc" }, { stroke: "#ccc" } ] };
        const spectroChart = new uPlot(uplotOpts, [xData, new Float32Array(FFT_SIZE)], document.getElementById("spectroscope-div"));

        const canvas = document.getElementById("spectrogram-canvas");
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.fillStyle = "#000000"; ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Connexion automatique au websocket sur le même host/port
        const ws = new WebSocket(`ws://${location.host}/ws`);
        ws.binaryType = "arraybuffer";

        ws.onmessage = (event) => {
            const buffer = event.data;
            const prefix = new DataView(buffer).getUint8(0);

            if (prefix === 1) {
                spectroChart.setData([xData, new Float32Array(buffer.slice(1))]);
            } else if (prefix === 2) {
                const intensities = new Uint8Array(buffer, 1);
                ctx.drawImage(canvas, 0, 0, canvas.width, canvas.height - 1, 0, 1, canvas.width, canvas.height - 1);
                const imgData = ctx.createImageData(FFT_SIZE, 1);
                for (let i = 0; i < FFT_SIZE; i++) {
                    const val = intensities[i];
                    const idx = i * 4;
                    imgData.data[idx] = val; imgData.data[idx+1] = val/2; imgData.data[idx+2] = 0; imgData.data[idx+3] = 255;
                }
                ctx.putImageData(imgData, 0, 0);
            }
        };
    </script>
</body>
</html>
"""

# 2. La route HTTP classique : sert la page Web
@app.get("/")
async def get_webpage():
    return HTMLResponse(HTML_PAGE)

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
            await websocket.send_bytes(b'\x01' + raw_data)
            
            # Traitement lent (1Hz)
            now = time.time()
            if now - last_spectro_time >= SPECTROGRAM_REFRESH_RATE:
                last_spectro_time = now
                fft_array = np.frombuffer(raw_data, dtype=np.float32)
                fft_norm = np.clip((fft_array + 100) / 100 * 255, 0, 255).astype(np.uint8)
                await websocket.send_bytes(b'\x02' + fft_norm.tobytes())
                
    except WebSocketDisconnect:
        print("Client web déconnecté.")
    finally:
        sock.close()

if __name__ == "__main__":
    # Lancement du serveur unifié (nécessite : pip install fastapi uvicorn pyzmq numpy)
    uvicorn.run(app, host="0.0.0.0", port=8000)
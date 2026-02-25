const FFT_SIZE = 4096;
const xData = new Float32Array(FFT_SIZE);
for (let i = 0; i < FFT_SIZE; i++) xData[i] = i;

const uplotOpts = { width: 1000, height: 250, scales: { x: { time: false }, y: { min: -100, max: 0 } }, series: [{}, { stroke: "#00ff00", width: 1 }], axes: [{ stroke: "#ccc" }, { stroke: "#ccc" }] };
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
            imgData.data[idx] = val; imgData.data[idx + 1] = val / 2; imgData.data[idx + 2] = 0; imgData.data[idx + 3] = 255;
        }
        ctx.putImageData(imgData, 0, 0);
    }
};
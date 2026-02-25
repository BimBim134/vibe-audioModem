let FFT_SIZE = 4096;
let xData = new Float32Array(FFT_SIZE);
for (let i = 0; i < FFT_SIZE; i++) xData[i] = i;

const uplotOpts = {
  width: document.getElementById("spectroscope-div").clientWidth || 1000,
  height: 250,
  scales: {
    x: { time: false },
    y: { range: [-80, 80] },
  },
  series: [{}, { stroke: "#00ff00", width: 1 }],
  axes: [
    {
      stroke: "#ccc",
      values: (self, ticks) =>
        ticks.map((v) =>
          v >= 1000 ? (v / 1000).toFixed(1) + " kHz" : v + " Hz",
        ),
    },
    { stroke: "#ccc", values: (self, ticks) => ticks.map((v) => v + " dB") },
  ],
};

const spectroChart = new uPlot(
  uplotOpts,
  [xData, new Float32Array(FFT_SIZE)],
  document.getElementById("spectroscope-div"),
);

const canvas = document.getElementById("spectrogram-canvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });
ctx.fillStyle = "#000000";
ctx.fillRect(0, 0, canvas.width, canvas.height);

window.addEventListener("resize", () => {
  spectroChart.setSize({
    width: document.getElementById("spectroscope-div").clientWidth,
    height: 250,
  });
});

const ws = new WebSocket(`ws://${location.host}/ws`);
ws.binaryType = "arraybuffer";

ws.onmessage = (event) => {
  const buffer = event.data;
  const view = new DataView(buffer);
  const prefix = view.getUint8(0);

  if (prefix === 1) {
    // SCOPE (Vert)
    const data = new Float32Array(buffer.slice(1));
    if (data.length !== FFT_SIZE) {
      FFT_SIZE = data.length;
      xData = new Float32Array(FFT_SIZE);
      const MAX_FREQ = 24000; // Fs=48000 => Nyquist=24000
      for (let i = 0; i < FFT_SIZE; i++) {
        xData[i] = (i / (FFT_SIZE - 1)) * MAX_FREQ;
      }
      canvas.width = FFT_SIZE;
    }
    spectroChart.setData([xData, data]);
  } else if (prefix === 2) {
    // WATERFALL (Niveaux de gris)
    const intensities = new Uint8Array(buffer, 1);
    const w = canvas.width;
    const h = canvas.height;

    // On décale tout vers le bas
    ctx.drawImage(canvas, 0, 0, w, h - 1, 0, 1, w, h - 1);

    // On dessine la nouvelle ligne en haut
    const imgData = ctx.createImageData(w, 1);
    for (let i = 0; i < w; i++) {
      const v = intensities[i];
      const idx = i * 4;
      imgData.data[idx] = v; // R
      imgData.data[idx + 1] = v; // G
      imgData.data[idx + 2] = v; // B
      imgData.data[idx + 3] = 255;
    }
    ctx.putImageData(imgData, 0, 0);
  }
};

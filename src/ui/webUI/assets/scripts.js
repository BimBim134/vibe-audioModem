let FFT_SIZE = 4096;
let xData = new Float32Array(FFT_SIZE);
for (let i = 0; i < FFT_SIZE; i++) xData[i] = i;

const rootStyles = getComputedStyle(document.documentElement);
const colors = {
  accentPrimary: rootStyles.getPropertyValue("--color-accent-primary").trim(),
  textMuted: rootStyles.getPropertyValue("--color-text-muted").trim(),
  bgPrimary: rootStyles.getPropertyValue("--color-bg-primary").trim(),
  bgSecondary: rootStyles.getPropertyValue("--color-bg-secondary").trim(),
};

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  } : { r: 0, g: 0, b: 0 };
}

const bgRgb = hexToRgb(colors.bgSecondary);
const accentRgb = hexToRgb(colors.accentPrimary);

function getChartDimensions() {
  const container = document.getElementById("spectroscope-div");
  return {
    width: container.clientWidth || 600,
    height: Math.max(100, (container.querySelector(".u-wrap")?.clientHeight || container.clientHeight || 300)),
  };
}

const initialDims = getChartDimensions();
const uplotOpts = {
  width: initialDims.width,
  height: initialDims.height,
  scales: {
    x: { time: false},
    y: { range: [-80, 80] },
  },
  series: [
    {
      label: "F",
      width: 1,
      value: (u, v) => (v == null ? "" : v.toFixed(1) + " Hz"),
    },
    {
      label: "A",
      stroke: colors.accentPrimary,
      width: 1,
      value: (u, v) => (v == null ? "" : v.toFixed(1) + " dB"),
    },
  ],
  axes: [
    {
      stroke: colors.textMuted,
      values: (self, ticks) =>
        ticks.map((v) =>
          v >= 1000 ? (v / 1000).toFixed(1) + " kHz" : v + " Hz",
        ),
    },
    {
      stroke: colors.textMuted,
      values: (self, ticks) => ticks.map((v) => v + " dB"),
    },
  ],
  legend: { show: true },
};

const spectroChart = new uPlot(
  uplotOpts,
  [xData, new Float32Array(FFT_SIZE)],
  document.getElementById("spectroscope-div"),
);

const canvas = document.getElementById("spectrogram-canvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });
ctx.fillStyle = colors.bgSecondary;
ctx.fillRect(0, 0, canvas.width, canvas.height);

const overlayCanvas = document.getElementById("spectrogram-overlay");
const overlayCtx = overlayCanvas.getContext("2d");

let overlayMessages = [];
let waterfallRowIndex = 0;

function resizeCharts() {
  const dims = getChartDimensions();
  spectroChart.setSize({ width: dims.width, height: dims.height });
  canvas.width = dims.width;
  canvas.height = canvas.parentElement.clientHeight;
  overlayCanvas.width = dims.width;
  overlayCanvas.height = canvas.parentElement.clientHeight;
}

const resizeObserver = new ResizeObserver(() => resizeCharts());
resizeObserver.observe(document.getElementById("spectroscope-div"));
resizeObserver.observe(document.getElementById("spectrogram-canvas").parentElement);

// WebSocket connection
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.binaryType = "arraybuffer";

ws.onmessage = (event) => {
  const buffer = event.data;
  const view = new DataView(buffer);
  const prefix = view.getUint8(0);

  if (prefix === 1) {
    // SCOPE (FFT spectrum in dB)
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
    // WATERFALL (Color gradient)
    const intensities = new Uint8Array(buffer, 1);
    const w = canvas.width;
    const h = canvas.height;

    waterfallRowIndex++;

    ctx.drawImage(canvas, 0, 0, w, h - 1, 0, 1, w, h - 1);

    const imgData = ctx.createImageData(w, 1);
    for (let i = 0; i < w; i++) {
      const v = intensities[i] / 255;
      const idx = i * 4;
      imgData.data[idx] = Math.round(bgRgb.r + (accentRgb.r - bgRgb.r) * v);
      imgData.data[idx + 1] = Math.round(bgRgb.g + (accentRgb.g - bgRgb.g) * v);
      imgData.data[idx + 2] = Math.round(bgRgb.b + (accentRgb.b - bgRgb.b) * v);
      imgData.data[idx + 3] = 255;
    }
    ctx.putImageData(imgData, 0, 0);

    renderOverlay();
  } else if (prefix === 4) {
    // MESSAGE (Received message JSON)
    const msgStr = new TextDecoder().decode(buffer.slice(1));
    try {
        const payload = JSON.parse(msgStr);
        displayReceivedMessage(payload);
    } catch (e) {
        console.error("Failed to parse message:", e);
    }
  } else if (prefix === 3) {
    // SYSTEM MESSAGE
    const sysMsg = new TextDecoder().decode(buffer.slice(1));
    const displayText = formatSystemMessage(sysMsg);
    overlayMessages.push({ text: displayText, rowIndex: waterfallRowIndex });
    displaySystemMessage(sysMsg);
  }
};

// DOM Elements
const carrierFreqInput = document.getElementById("carrier-freq");
const modulationSelect = document.getElementById("modulation-preset");
const senderNameInput = document.getElementById("sender-name");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const messagesBoard = document.getElementById("messages-board");

// Load initial config
fetch("/api/config")
  .then(res => res.json())
  .then(config => {
    carrierFreqInput.value = config.carrier_freq;
    modulationSelect.value = config.modulation_preset;
  })
  .catch(err => console.error("Failed to load config:", err));

// Carrier frequency change
carrierFreqInput.addEventListener("change", async () => {
  const carrierFreq = parseFloat(carrierFreqInput.value);
  try {
    await fetch("/api/carrier_freq", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ carrier_freq: carrierFreq })
    });
  } catch (err) {
    console.error("Failed to update carrier frequency:", err);
  }
});

// Modulation preset change
modulationSelect.addEventListener("change", async () => {
  const preset = modulationSelect.value;
  try {
    await fetch("/api/modulation_preset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset: preset })
    });
  } catch (err) {
    console.error("Failed to update modulation preset:", err);
  }
});

// Send message
async function sendMessage() {
  const message = messageInput.value.trim();
  if (!message) return;
  
  const senderName = senderNameInput.value || "Me";
  
  // Disable button during send
  sendButton.disabled = true;
  
  try {
    const response = await fetch("/api/transmit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        sender_name: senderName
      })
    });
    
    const result = await response.json();
    
    if (result.status === "ok") {
      // Display sent message
      displaySentMessage(result.message, result.sender, result.meta);
      messageInput.value = "";
    } else {
      console.error("Transmission failed:", result.message);
    }
  } catch (err) {
    console.error("Failed to send message:", err);
  } finally {
    sendButton.disabled = false;
  }
}

sendButton.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Display functions
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function displaySentMessage(content, sender, meta) {
  const msgDiv = document.createElement("div");
  msgDiv.className = "message sent";
  msgDiv.innerHTML = `
    <div class="message-header">
      <span class="sender">${escapeHtml(sender)}</span>
      <span class="meta">${escapeHtml(meta)}</span>
    </div>
    <div class="message-content">${escapeHtml(content)}</div>
  `;
  messagesBoard.appendChild(msgDiv);
  messagesBoard.scrollTop = messagesBoard.scrollHeight;
}

function displayReceivedMessage(payload) {
  const sender = payload.sender_name || "unknown";
  const carrierFreq = payload.carrier_freq;
  const freq = carrierFreq ? `${carrierFreq.toFixed(0)} Hz` : "RX";
  const dateStr = new Date().toLocaleTimeString("fr-FR");
  
  let content;
  if (payload.data) {
    if (typeof payload.data === "string") {
      try {
        const bytes = Uint8Array.from(atob(payload.data), c => c.charCodeAt(0));
        content = new TextDecoder().decode(bytes);
      } catch (e) {
        content = payload.data;
      }
    } else if (payload.data instanceof Uint8Array || Array.isArray(payload.data)) {
      const bytes = new Uint8Array(payload.data);
      content = new TextDecoder().decode(bytes);
    } else {
      content = JSON.stringify(payload.data);
    }
  } else {
    content = "Message reçu";
  }
  
  const msgDiv = document.createElement("div");
  msgDiv.className = "message received";
  msgDiv.innerHTML = `
    <div class="message-header">
      <span class="sender">${escapeHtml(sender)}</span>
      <span class="meta">${freq} — ${dateStr}</span>
    </div>
    <div class="message-content">${escapeHtml(content)}</div>
  `;
  messagesBoard.appendChild(msgDiv);
  messagesBoard.scrollTop = messagesBoard.scrollHeight;
}

function formatSystemMessage(content) {
  try {
    const payload = typeof content === "string" ? JSON.parse(content) : content;
    
    switch (payload.status) {
      case "preamble":
        return "Preamble";
      case "collecting":
        return `${payload.bytes_received} bytes received`;
      case "error":
        return payload.error || "Unknown error";
      case "deserialization_error":
        return "Deserialization error";
      case "dispatching":
        const workerId = payload.worker_id !== undefined ? `worker ${payload.worker_id}` : "";
        return workerId ? `TX → ${workerId}` : "TX";
      default:
        return JSON.stringify(payload);
    }
  } catch (e) {
    return content;
  }
}

function displaySystemMessage(content) {
  const msgDiv = document.createElement("div");
  msgDiv.className = "message system";
  
  const displayText = formatSystemMessage(content);
  
  msgDiv.innerHTML = `<div class="message-content">${escapeHtml(displayText)}</div>`;
  messagesBoard.appendChild(msgDiv);
  messagesBoard.scrollTop = messagesBoard.scrollHeight;
}

function renderOverlay() {
  const w = overlayCanvas.width;
  const h = overlayCanvas.height;
  overlayCtx.clearRect(0, 0, w, h);

  overlayCtx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
  overlayCtx.textBaseline = "middle";

  overlayMessages = overlayMessages.filter((msg) => {
    const y = waterfallRowIndex - msg.rowIndex;

    if (y >= h) return false;
    if (y < 0) return true;

    const text = msg.text.length > 50 ? msg.text.substring(0, 47) + "..." : msg.text;
    const padding = 6;
    const textWidth = overlayCtx.measureText(text).width;
    const pillWidth = textWidth + padding * 2;
    const pillHeight = 20;
    const margin = 10;
    const x = margin;
    const textY = y - pillHeight / 2;

    overlayCtx.fillStyle = colors.bgPrimary;
    overlayCtx.shadowColor = "rgba(0, 0, 0, 0.2)";
    overlayCtx.shadowBlur = 8;
    overlayCtx.shadowOffsetY = 3;
    overlayCtx.beginPath();
    overlayCtx.roundRect(x, textY, pillWidth, pillHeight, 4);
    overlayCtx.fill();
    overlayCtx.shadowBlur = 0;
    overlayCtx.shadowOffsetY = 0;

    overlayCtx.fillStyle = colors.accentPrimary;
    overlayCtx.fillText(text, x + padding, y);

    return true;
  });
}

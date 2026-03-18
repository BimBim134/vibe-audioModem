let FFT_SIZE = 4096;
let xData = new Float32Array(FFT_SIZE);
for (let i = 0; i < FFT_SIZE; i++) xData[i] = i;

const rootStyles = getComputedStyle(document.documentElement);
const colors = {
  accentPrimary: rootStyles.getPropertyValue("--color-accent-primary").trim(),
  textMuted: rootStyles.getPropertyValue("--color-text-muted").trim(),
  bgPrimary: rootStyles.getPropertyValue("--color-bg-primary").trim(),
};

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  } : { r: 0, g: 0, b: 0 };
}

const bgRgb = hexToRgb(colors.bgPrimary);
const accentRgb = hexToRgb(colors.accentPrimary);

const uplotOpts = {
  width: document.getElementById("spectroscope-div").clientWidth || 1000,
  height: 250,
  scales: {
    x: { time: false },
    y: { range: [-80, 80] },
  },
  series: [{}, { stroke: colors.accentPrimary, width: 1 }],
  axes: [
    {
      stroke: colors.textMuted,
      values: (self, ticks) =>
        ticks.map((v) =>
          v >= 1000 ? (v / 1000).toFixed(1) + " kHz" : v + " Hz",
        ),
    },
    { stroke: colors.textMuted, values: (self, ticks) => ticks.map((v) => v + " dB") },
  ],
};

const spectroChart = new uPlot(
  uplotOpts,
  [xData, new Float32Array(FFT_SIZE)],
  document.getElementById("spectroscope-div"),
);

const canvas = document.getElementById("spectrogram-canvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });
ctx.fillStyle = colors.bgPrimary;
ctx.fillRect(0, 0, canvas.width, canvas.height);

window.addEventListener("resize", () => {
  spectroChart.setSize({
    width: document.getElementById("spectroscope-div").clientWidth,
    height: 250,
  });
});

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
  } else if (prefix === 4) {
    // MESSAGE (Received message JSON)
    const msgStr = new TextDecoder().decode(buffer.slice(1));
    try {
        const payload = JSON.parse(msgStr);
        displayReceivedMessage(payload);
    } catch (e) {
        console.error("Failed to parse message:", e);
    }
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
      // Base64 encoded bytes - decode them
      try {
        const bytes = Uint8Array.from(atob(payload.data), c => c.charCodeAt(0));
        content = new TextDecoder().decode(bytes);
      } catch (e) {
        content = payload.data;
      }
    } else if (payload.data instanceof Uint8Array || Array.isArray(payload.data)) {
      // Convert bytes/array to string
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

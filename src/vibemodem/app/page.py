"""The page of the local application: plain HTML and JavaScript, no build step, works offline."""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vibe AudioModem</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 44rem; margin: 1.5rem auto; padding: 0 1rem; }
  fieldset { margin: 1rem 0; border: 1px solid #8886; border-radius: 6px; }
  legend { font-weight: 600; }
  label { display: inline-block; margin: 0.25rem 0.75rem 0.25rem 0; }
  textarea { width: 100%; box-sizing: border-box; font: inherit; }
  button { font: inherit; padding: 0.4rem 0.9rem; margin: 0.25rem 0.25rem 0.25rem 0; }
  #error { color: #b00020; min-height: 1.4em; }
  #info { min-height: 1.4em; }
  li { margin: 0.4rem 0; }
  .part { opacity: 0.8; }
  .gap { color: #b00020; }
</style>
</head>
<body>
<h1>Vibe AudioModem</h1>
<p id="error" role="alert"></p>
<p id="info" aria-live="polite"></p>

<fieldset>
  <legend>Settings</legend>
  <label>Preset
    <select id="preset">
      <option value="max-range">Maximum range (slowest)</option>
      <option value="standard" selected>Standard</option>
      <option value="fast">Fast</option>
    </select>
  </label>
  <label>Input <select id="input_device"><option value="">default</option></select></label>
  <label>Output <select id="output_device"><option value="">default</option></select></label>
  <button id="apply">Apply</button>
</fieldset>

<fieldset>
  <legend>Send</legend>
  <textarea id="text" rows="3" placeholder="Message"></textarea>
  <label>Copies <input id="copies" type="number" min="1" max="8" value="1" style="width:4rem"></label>
  <button id="send">Send</button>
  <button id="cancel">Cancel</button>
  <span id="sending"></span>
</fieldset>

<fieldset>
  <legend>Receive</legend>
  <button id="listen">Start listening</button>
  <span id="listening"></span>
  <ul id="received"></ul>
</fieldset>

<p><button id="quit">Quit</button></p>

<script>
const $ = (id) => document.getElementById(id);
const say = (id, text) => { $(id).textContent = text || ""; };
let state = { listening: false, sending: false };
let lastSettings = null;

async function call(path, method, body) {
  const options = { method: method || "GET" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const d = data.detail;
    const text = Array.isArray(d) ? d.map((e) => (e.loc ? e.loc.slice(1).join(".") + ": " : "") + e.msg).join("; ") : d;
    throw new Error(text || ("error " + response.status));
  }
  return data;
}
async function act(promise, then) {
  say("error", "");
  say("info", "");
  try { const data = await promise; if (then) then(data); }
  catch (error) { say("error", String(error.message || error)); }
  refresh();
}

function fillDevices(devices) {
  for (const [id, key] of [["input_device", "inputs"], ["output_device", "outputs"]]) {
    const select = $(id);
    if (select.options.length > 1) continue;
    for (const d of devices.filter((d) => d[key] > 0)) {
      const option = document.createElement("option");
      option.value = d.index; option.textContent = d.name; select.appendChild(option);
    }
  }
}
function deviceValue(id) {
  const value = $(id).value;
  return value === "" ? null : Number(value);
}

function showReceived(items) {
  const list = $("received");
  list.replaceChildren();
  for (const item of items) {
    const li = document.createElement("li");
    if (item.complete) {
      li.textContent = "#" + item.number + "  " + item.text;
    } else {
      li.className = "part";
      const label = document.createElement("strong");
      label.textContent = "Incomplete (" + item.parts.length + " part(s), Fragments missing: " +
        item.missing.join(", ") + " of " + item.total + ")";
      li.appendChild(label);
      for (const [offset, text] of item.parts) {
        const piece = document.createElement("div");
        piece.textContent = "from byte " + offset + ": " + text;
        li.appendChild(piece);
      }
    }
    list.appendChild(li);
  }
}

async function refresh() {
  try {
    state = await call("/api/status");
    say("sending", state.sending ? "sending..." : "");
    say("listening", state.listening ? "listening" + (state.blocks_lost ? " (" + state.blocks_lost + " blocks lost)" : "") : "");
    $("listen").textContent = state.listening ? "Stop listening" : "Start listening";
    const shown = JSON.stringify(state.settings);
    if (shown !== lastSettings) {  // only when they changed, so a choice not yet applied is kept
      lastSettings = shown;
      $("preset").value = state.settings.preset;
      $("input_device").value = state.settings.input_device === null ? "" : state.settings.input_device;
      $("output_device").value = state.settings.output_device === null ? "" : state.settings.output_device;
    }
    for (const id of ["preset", "input_device", "output_device", "apply"]) {
      $(id).disabled = state.sending || state.listening;
    }
    $("send").disabled = state.sending;
    $("cancel").disabled = !state.sending;
    if (state.last_error) say("error", state.last_error);
    showReceived((await call("/api/received")).received);
  } catch (error) { say("error", "The application does not answer."); }
}

$("apply").onclick = () => act(call("/api/settings", "POST", {
  preset: $("preset").value, input_device: deviceValue("input_device"),
  output_device: deviceValue("output_device"),
}), () => say("info", "Settings applied."));
$("send").onclick = () => act(call("/api/send", "POST", {
  text: $("text").value, copies: Number($("copies").value),
}), (sent) => say("info", "Sending " + sent.fragments + " Fragment(s), " +
  sent.copies + " cop" + (sent.copies > 1 ? "ies" : "y") + ", about " +
  Math.round(sent.airtime_seconds) + " s on the air."));
$("cancel").onclick = () => act(call("/api/cancel", "POST"), () => say("info", "Cancelled."));
$("listen").onclick = () => act(call(state.listening ? "/api/listen/stop" : "/api/listen/start", "POST"));
$("quit").onclick = async () => {
  await call("/api/quit", "POST").catch(() => {});
  say("info", "Stopped. You can close this tab.");
};

(async () => { fillDevices((await call("/api/devices")).devices); lastSettings = null; refresh(); })();
setInterval(refresh, 1500);
</script>
</body>
</html>
"""

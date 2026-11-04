const $ = (id) => document.getElementById(id);
const say = (id, text) => { $(id).textContent = text || ""; };

// The four colours are the ones of `style.css`: read from it, never repeated here.
const triple = (name, fallback) => {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim().split(/[\s,]+/).map(Number);
  return value.length === 3 && value.every((n) => n >= 0 && n <= 255) ? value : fallback;  // not "r g b"? then ours
};
const BG = triple("--bg", [21, 20, 25]), GREY = triple("--grey", [135, 135, 135]),
  TEXT = triple("--text", [251, 251, 251]), ACCENT = triple("--accent", [245, 110, 15]);
const rgb = (c, alpha = 1) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${alpha})`;
const mix = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));

let state = { listening: false, sending: false, settings: {} };
let asked = 0, refreshes = 0, wasListening = false, lastSettings = null;

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
// A failure is told where the person is looking: under the composer, or in the open dialog.
const showError = (text, where = "error") => say(where, text ? "! " + text : "");
async function act(promise, then, where = "error") {
  showError("", where);
  try { const data = await promise; if (then) then(data); }
  catch (error) { showError(String(error.message || error), where); }
  refresh();
}
// A click that cannot be undone asks for a second one (the browser's own dialogs ignore our colours).
// `warn`, when given, tells what the click will cost, while it waits for the second one.
function confirmed(button, label, action, warn) {
  const disarm = (warning) => {
    delete button.dataset.sure; button.textContent = label; button.classList.remove("sure");
    if (warning && $("settings-warning").textContent === warning) say("settings-warning", "");
  };
  button.onclick = () => {
    if (button.dataset.sure) { clearTimeout(Number(button.dataset.sure)); disarm(button.dataset.warning); action(); return; }
    const warning = warn ? warn() : "";
    button.dataset.warning = warning;
    if (warning) say("settings-warning", warning);  // its own line: refresh() writes to the note every second
    button.textContent = "Click again to confirm"; button.classList.add("sure");
    button.dataset.sure = setTimeout(() => disarm(warning), 4000);
  };
}

// The estimate, before sending ------------------------------------------------------------------
function sendBody() {  // what is estimated is what is sent
  const frequency = $("frequency").value;
  return { text: $("text").value, copies: Number($("copies").value), frequency_hz: frequency === "" ? null : Number(frequency) };
}
function duration(seconds) {
  const whole = Math.round(seconds);
  return whole < 60 ? whole + " s" : Math.floor(whole / 60) + " min " + (whole % 60) + " s";
}
let estimate = { fits: false, frequency_problem: null };  // Send waits for the first answer
let estimateTimer = null;
function canSend() {
  return !state.sending && estimate.fits && !estimate.frequency_problem && $("text").value.trim() !== "";
}
function askEstimate() {
  const mine = ++asked;  // any answer to an earlier question is stale from now on
  $("send").disabled = true;
  clearTimeout(estimateTimer);
  estimateTimer = setTimeout(async () => {
    let answer;
    try { answer = await call("/api/estimate", "POST", sendBody()); }
    catch (error) {
      if (mine !== asked) return;
      estimate = { fits: false, frequency_problem: null };
      $("estimate").className = "refused"; say("estimate", String(error.message || error));
      return;
    }
    if (mine !== asked) return;
    estimate = answer;
    const [low, high] = estimate.frequency_range_hz;
    signalWidthHz = estimate.signal_width_hz;
    $("frequency").min = low; $("frequency").max = high;
    if ($("frequency").value === "") $("frequency").placeholder = estimate.default_frequency_hz;
    say("range", low + " to " + high + " Hz");
    const line = $("estimate");
    const problem = !estimate.fits ? estimate.reason : estimate.frequency_problem;
    line.className = problem ? "refused" : "";
    line.textContent = problem || (estimate.fragments + (estimate.fragments > 1 ? " Fragments" : " Fragment") +
      " · about " + duration(estimate.airtime_seconds) + " on the air · up to " + estimate.max_bytes + " bytes here");
    $("send").disabled = !canSend();
    drawScope();
  }, 250);
}

// The conversation ------------------------------------------------------------------------------
const clock = (at) => new Date(at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const hz = (v) => Math.round(v) + " Hz";
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function partialText(item) {  // what was read of a Message, the gaps shown as "..."
  const pieces = item.parts.slice().sort((a, b) => a[0] - b[0]);
  let text = pieces.length && pieces[0][0] > 0 ? "… " : "";
  pieces.forEach(([offset, part], i) => { text += (i ? " … " : "") + part; });
  return text + (item.missing.includes(item.total - 1) ? " …" : "");
}
function bubble(item) {
  if (item.kind === "arriving") {  // the Preamble is heard: a Message is coming in at this frequency
    const row = element("div", "row in");
    const box = element("div", "bubble in coming", "Receiving a signal at " + hz(item.frequency_hz));
    const dots = element("span", "dots");
    dots.setAttribute("aria-hidden", "true");
    dots.append(element("i"), element("i"), element("i"));
    box.appendChild(dots);
    row.appendChild(box);
    return row;
  }
  if (item.kind === "lost") return element("div", "note", "Signal detected at " + hz(item.frequency_hz) + ", not decoded · " + clock(item.at));
  const row = element("div", "row " + (item.kind === "sent" ? "out" : "in"));
  const box = element("div", "bubble");
  row.appendChild(box);
  let meta = [];
  box.appendChild(element("span", "sr", item.kind === "sent" ? "You sent: " : "Received: "));
  if (item.kind === "sent") {
    box.classList.add(item.status === "failed" ? "failed" : "out");
    box.appendChild(document.createTextNode(item.text));
    const status = { sending: "sending…", sent: "sent", cancelled: "cancelled", failed: "failed" }[item.status];
    meta = [status, duration(item.airtime_seconds), hz(item.frequency_hz)];
    if (item.copies > 1) meta.push(item.copies + " copies");
    if (item.error) meta.push(item.error);
  } else if (item.kind === "incomplete") {
    box.classList.add("in", "part");
    const got = item.total - item.missing.length;
    box.appendChild(element("span", "head", "Incomplete · " + got + " of " + item.total + " fragments"));
    box.appendChild(document.createTextNode(partialText(item)));
    meta = [item.frequency_hz === null ? null : hz(item.frequency_hz)];
  } else {
    box.classList.add("in");
    box.appendChild(document.createTextNode(item.text));
    meta = [item.frequency_hz === null ? null : hz(item.frequency_hz), item.snr_db === null ? null : "SNR " + Math.round(item.snr_db) + " dB"];
  }
  box.appendChild(element("span", "meta", meta.filter(Boolean).concat(clock(item.at)).join(" · ")));
  return row;
}
// What is on screen, by identifier: a bubble is built once, rebuilt only when it changes (the
// text of a Message can be selected, a bubble does not play its arrival again), and only a new
// one arrives with a movement.
const shown = new Map();
let firstFill = true;
const everShown = new Set();  // a bubble that comes back after a filter does not arrive again
function showConversation(items, hidden = 0) {
  const box = $("conversation");
  const atBottom = firstFill || box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  const keep = new Set(items.map((item) => item.id));
  for (const [id, entry] of shown) if (!keep.has(id)) { entry.node.remove(); shown.delete(id); }
  const nodes = items.map((item) => {
    const signature = JSON.stringify(item), entry = shown.get(item.id);
    if (entry && entry.signature === signature) return entry.node;
    const node = bubble(item);
    if (!entry && !firstFill && !everShown.has(item.id)) {
      node.classList.add("fresh");
      node.addEventListener("animationend", () => node.classList.remove("fresh"), { once: true });  // a move later must not replay it
    }
    if (entry) entry.node.replaceWith(node);
    shown.set(item.id, { signature, node });
    everShown.add(item.id);
    return node;
  });
  box.querySelector(".empty")?.remove();
  nodes.forEach((node, i) => { if (box.children[i] !== node) box.insertBefore(node, box.children[i] || null); });
  if (!items.length) {
    const none = hidden ? "Nothing matches the filters." : "No messages yet. Press Listen to receive, or write one below.";
    box.appendChild(element("div", "empty", none));
  }
  if (atBottom) box.scrollTop = box.scrollHeight;
  firstFill = false;
}

// The filters of the conversation: what you sent is always shown; what was heard can be kept to a
// band (by the lowest tone of the Signal) and the Signals that were not decoded can be hidden.
let conversationNow = [];
const bound = (id) => { const text = $(id).value.trim(), value = Number(text); return text === "" || !Number.isFinite(value) ? null : value; };
const filtering = () => bound("filter_from") !== null || bound("filter_to") !== null || !$("filter_lost").checked;
function passes(item) {
  if (item.kind === "sent") return true;
  if (item.kind === "lost" && !$("filter_lost").checked) return false;
  if (item.frequency_hz === null) return true;  // no frequency known: nothing to filter on
  const from = bound("filter_from"), to = bound("filter_to");
  return (from === null || item.frequency_hz >= from) && (to === null || item.frequency_hz <= to);
}
function showFiltered() {
  const items = conversationNow.filter(passes), hidden = conversationNow.length - items.length;
  $("filter_reset").hidden = !filtering();
  $("filter_reset").textContent = hidden ? "Reset filters · " + hidden + " hidden" : "Reset filters";
  showConversation(items, hidden);
}
const FILTER_KEY = "vibemodem.filter.";
for (const id of ["filter_from", "filter_to", "filter_lost"]) {
  const box = $(id), checkbox = box.type === "checkbox";
  try {
    const saved = localStorage.getItem(FILTER_KEY + id);
    if (saved !== null) { if (checkbox) box.checked = saved === "1"; else box.value = saved; }
  } catch (error) { /* no storage: the page still works */ }
  box.addEventListener("input", () => {
    try { localStorage.setItem(FILTER_KEY + id, checkbox ? (box.checked ? "1" : "0") : box.value); } catch (error) { /* idem */ }
    showFiltered();
  });
}
$("filter_reset").onclick = () => {
  $("filter_from").focus();  // the button hides itself: the focus must not be lost with it
  $("filter_from").value = ""; $("filter_to").value = ""; $("filter_lost").checked = true;
  for (const id of ["filter_from", "filter_to", "filter_lost"]) $(id).dispatchEvent(new Event("input"));
};

// The spectrum and the waterfall ----------------------------------------------------------------
const MAX_ROWS = 120, MARKER_SECONDS = 60;
let lowHz = 300, highHz = 2700;  // the band of a row, told by the application with the rows
const FLOOR_DB = -100, CEILING_DB = -20;  // a fixed range: the same level is the same colour
let spectrumNext = 0, history = [], markers = [], signalWidthHz = 175;
// The waterfall, from the quietest to the loudest: dark lava, dusty grey, liquid lava, snow.
const RAMP = [[0, BG], [0.34, mix(BG, GREY, 0.4)], [0.7, ACCENT], [1, TEXT]];
function colour(t) {
  t = Number.isFinite(t) ? Math.max(0, Math.min(1, t)) : 0;
  const next = RAMP.findIndex(([at]) => at > t);  // the first stop above this level
  const i = next < 0 ? RAMP.length - 2 : next - 1;
  const [t0, c0] = RAMP[i], [t1, c1] = RAMP[i + 1];
  return mix(c0, c1, (t - t0) / (t1 - t0));
}
function transmitBand() {  // where the next Message would be sent: from the lowest tone up
  const typed = $("frequency").value;
  const start = typed === "" ? Number($("frequency").placeholder) || 1450 : Number(typed);
  return Number.isFinite(start) ? [start, start + signalWidthHz] : null;
}
let axisFor = "";
function drawAxis() {
  if (axisFor === lowHz + "-" + highHz) return;
  axisFor = lowHz + "-" + highHz;
  const axis = $("axis");
  axis.replaceChildren();
  const step = 300;
  for (let f = Math.ceil(lowHz / step) * step; f <= highHz; f += step) {
    const tick = element("span", "", f);
    tick.style.left = ((f - lowHz) / (highHz - lowHz) * 100) + "%";
    axis.appendChild(tick);
  }
}
const buffer = document.createElement("canvas");  // one pixel per cell, scaled when drawn
function fit(canvas) {  // as many pixels as the screen shows, so that lines stay thin
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(canvas.clientWidth * scale));
  canvas.height = Math.max(1, Math.round(canvas.clientHeight * scale));
}
function drawScope() {
  const water = $("waterfall"), wctx = water.getContext("2d");
  wctx.fillStyle = rgb(BG); wctx.fillRect(0, 0, water.width, water.height);
  const width = history.length ? history[0].length : 480;
  if (history.length) {
    buffer.width = width; buffer.height = MAX_ROWS;
    const bctx = buffer.getContext("2d");
    const image = bctx.createImageData(width, MAX_ROWS);
    history.slice().reverse().forEach((row, y) => {  // the newest at the top
      for (let x = 0; x < width; x++) {
        const [r, g, b] = colour((row[x] - FLOOR_DB) / (CEILING_DB - FLOOR_DB));
        const at = (y * width + x) * 4;
        image.data[at] = r; image.data[at + 1] = g; image.data[at + 2] = b; image.data[at + 3] = 255;
      }
    });
    bctx.putImageData(image, 0, 0);
    wctx.imageSmoothingEnabled = false;
    wctx.drawImage(buffer, 0, 0, width, MAX_ROWS, 0, 0, water.width, water.height);
  }
  const curve = $("spectrum"), cctx = curve.getContext("2d");
  cctx.clearRect(0, 0, curve.width, curve.height);
  const last = history[history.length - 1];
  const line = Math.max(1, window.devicePixelRatio || 1);
  if (last) {
    const curvePath = new Path2D();
    last.forEach((value, x) => {
      const level = Number.isFinite(value) ? Math.max(0, Math.min(1, (value - FLOOR_DB) / (CEILING_DB - FLOOR_DB))) : 0;
      const px = x / (last.length - 1) * curve.width, py = curve.height - 3 * line - level * (curve.height - 8 * line);
      x === 0 ? curvePath.moveTo(px, py) : curvePath.lineTo(px, py);
    });
    const fillPath = new Path2D(curvePath);
    fillPath.lineTo(curve.width, curve.height); fillPath.lineTo(0, curve.height); fillPath.closePath();
    cctx.fillStyle = rgb(ACCENT); cctx.fill(fillPath);
    cctx.strokeStyle = rgb(ACCENT); cctx.lineWidth = line; cctx.stroke(curvePath);
  }
  const span = highHz - lowHz;
  const band = transmitBand();
  if (band) {  // the Signal that would be sent: to choose a free place for it
    for (const [canvas, ctx] of [[curve, cctx], [water, wctx]]) {
      const x0 = (band[0] - lowHz) / span * canvas.width, x1 = (band[1] - lowHz) / span * canvas.width;
      ctx.fillStyle = rgb(ACCENT, 0.28); ctx.fillRect(x0, 0, Math.max(x1 - x0, 2 * line), canvas.height);
      ctx.fillStyle = rgb(ACCENT); ctx.fillRect(x0 - line / 2, 0, line, canvas.height);
    }
  }
  const now = Date.now() / 1000;
  for (const marker of markers) {  // where Messages were heard: on both drawings
    const fade = Math.min(1, Math.max(0, 1 - (now - marker.at) / MARKER_SECONDS));
    for (const [canvas, ctx] of [[curve, cctx], [water, wctx]]) {
      const x = (marker.hz - lowHz) / span * canvas.width;
      ctx.strokeStyle = rgb(TEXT, 0.9 * fade); ctx.lineWidth = line;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
  }
  drawAxis();
}
async function refreshSpectrum() {
  if (!state.listening) return;  // nothing new while it does not listen: the last picture stays
  try {
    const data = await call("/api/spectrum?since=" + spectrumNext);
    lowHz = data.low_hz; highHz = data.low_hz + data.bin_hz * (data.rows[0] ? data.rows[0].length : 480);
    if (data.next < spectrumNext) history = [];  // the application started again
    spectrumNext = data.next;
    if (!data.rows.length) return;
    history = history.concat(data.rows).slice(-MAX_ROWS);
    drawScope();
  } catch (error) { /* the next refresh will say if the application does not answer */ }
}
function fitAll() { fit($("spectrum")); fit($("waterfall")); drawScope(); }
window.addEventListener("resize", fitAll);

// Settings and storage --------------------------------------------------------------------------
function fillDevices(devices) {
  for (const [id, key] of [["input_device", "inputs"], ["output_device", "outputs"]]) {
    const select = $(id);
    if (select.options.length > 1) continue;
    for (const d of devices.filter((d) => d[key] > 0)) select.appendChild(new Option(d.name, d.index));
  }
}
const deviceValue = (id) => ($(id).value === "" ? null : Number($(id).value));
async function refreshStorage() {
  try {
    const info = await call("/api/storage");
    for (const id of ["keep", "limit", "clear"]) $(id).disabled = !info.available;
    if (!info.available) { say("usage", "Receptions cannot be kept: there is nowhere to keep them."); return; }
    if (document.activeElement !== $("limit")) $("limit").value = Math.round(info.limit_mb);
    $("keep").checked = info.keep;
    say("usage", info.count + " kept, " + info.used_mb.toFixed(1) + " MB of " + Math.round(info.limit_mb) + " MB, in " + info.directory);
  } catch (error) { /* refresh will say if the application does not answer */ }
}
const tabs = [$("tab-general"), $("tab-advanced")];
function showTab(tab) {
  for (const other of tabs) {
    const selected = other === tab;
    other.setAttribute("aria-selected", selected);
    other.tabIndex = selected ? 0 : -1;
    $(other.getAttribute("aria-controls")).hidden = !selected;
  }
}
for (const tab of tabs) {
  tab.onclick = () => showTab(tab);
  tab.addEventListener("keydown", (event) => {
    const index = tabs.indexOf(tab);
    let next;
    if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
    else if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
    else if (event.key === "Home") next = tabs[0];
    else if (event.key === "End") next = tabs[tabs.length - 1];
    else return;
    event.preventDefault();
    showTab(next);
    next.focus();
  });
}
let appliedTimer;
function showApplied() {
  const button = $("apply");
  button.textContent = "Applied.";
  clearTimeout(appliedTimer);
  appliedTimer = setTimeout(() => { button.textContent = "Apply"; }, 2000);
}
$("apply").onclick = () => act(call("/api/settings", "POST", {
  preset: $("preset").value, input_device: deviceValue("input_device"), output_device: deviceValue("output_device"),
}), showApplied, "settings-error");
$("keep").onchange = () => act(call("/api/storage", "POST", { keep: $("keep").checked }), refreshStorage, "settings-error");
$("limit").onchange = () => act(call("/api/storage", "POST", { limit_mb: Number($("limit").value) }), refreshStorage, "settings-error");
confirmed($("clear"), "Delete all stored receptions", () =>
  act(call("/api/storage/clear", "POST"), (done) => { say("usage", done.deleted + " deleted."); refreshStorage(); }, "settings-error"));
$("open-settings").onclick = () => $("settings").showModal();
$("close-settings").onclick = () => $("settings").close();
let quitting = false;
confirmed($("quit"), "Quit the application", async () => {
  quitting = true;  // the tab may be closed now without the browser asking
  await call("/api/quit", "POST").catch(() => {});
  $("settings").close();
  document.body.replaceChildren(element("p", "empty", "Stopped. You can close this tab."));
}, () => state.listening ? "It is still listening: quitting stops the listening, and nothing is received until the application is started again." : "");
// Closing the tab while listening: the browser asks first (it chooses the words itself). The listening
// goes on in the application, which only the Quit button stops.
window.addEventListener("beforeunload", (event) => {
  if (state.listening && !quitting) { event.preventDefault(); event.returnValue = ""; }
});

// Sending, listening ----------------------------------------------------------------------------
$("composer").onsubmit = (event) => {
  event.preventDefault();
  if (!canSend()) return;
  act(call("/api/send", "POST", sendBody()), () => { $("text").value = ""; grow(); askEstimate(); });
};
$("cancel").onclick = () => act(call("/api/cancel", "POST"));
$("listen").onclick = () => act(call(state.listening ? "/api/listen/stop" : "/api/listen/start", "POST"));
const grow = () => { $("text").style.height = "auto"; $("text").style.height = Math.min($("text").scrollHeight, 128) + "px"; };
$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("composer").requestSubmit(); }
});
// What is set for sending is kept for next time (if the browser allows it).
for (const id of ["copies", "frequency"]) {
  try { const saved = localStorage.getItem("vibemodem." + id); if (saved !== null) $(id).value = saved; } catch (error) { /* no storage: the page still works */ }
  $(id).addEventListener("input", () => { try { localStorage.setItem("vibemodem." + id, $(id).value); } catch (error) { /* idem */ } });
}
for (const id of ["text", "copies", "frequency"]) $(id).addEventListener("input", askEstimate);
$("text").addEventListener("input", grow);
$("frequency").addEventListener("input", drawScope);  // the band moves as it is typed
// A click on a chart puts the Signal there: the band is centred on the click.
for (const canvas of [$("spectrum"), $("waterfall")]) {
  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const clicked = lowHz + (event.clientX - rect.left) / rect.width * (highHz - lowHz);
    let start = clicked - signalWidthHz / 2;
    if (estimate.frequency_range_hz) start = Math.max(estimate.frequency_range_hz[0], Math.min(estimate.frequency_range_hz[1], start));
    $("frequency").value = Math.round(start);
    $("frequency").dispatchEvent(new Event("input"));  // saved, estimated, drawn
  });
}

async function refresh() {
  const mine = ++refreshes;  // an answer that comes after a newer one is not shown
  try {
    const status = await call("/api/status");
    const conversation = (await call("/api/conversation")).items;
    if (mine !== refreshes) return;
    state = status;
    $("dot").className = "dot" + (state.listening ? " on" : "");
    const lost = state.blocks_lost ? " · " + state.blocks_lost + " blocks of sound lost" : "";
    $("listening").className = state.blocks_lost ? "warn" : "";
    say("listening", state.listening ? "Listening" + lost : "Not listening");
    if (state.listening && !wasListening) history = [];  // a new waterfall
    wasListening = state.listening;
    $("listen").textContent = state.listening ? "Stop" : "Listen";
    const settings = JSON.stringify(state.settings);
    if (settings !== lastSettings) {  // only when they changed, so a choice not yet applied is kept
      lastSettings = settings;
      askEstimate();  // the Preset decides the airtime and the range of frequencies
      $("preset").value = state.settings.preset;
      $("input_device").value = state.settings.input_device === null ? "" : state.settings.input_device;
      $("output_device").value = state.settings.output_device === null ? "" : state.settings.output_device;
    }
    const busy = state.sending || state.listening;
    for (const id of ["preset", "input_device", "output_device", "apply"]) $(id).disabled = busy;
    if (busy) say("settings-note", "Stop listening and sending to change these.");
    else if ($("settings-note").textContent.startsWith("Stop listening")) say("settings-note", "");
    $("send").hidden = state.sending; $("cancel").hidden = !state.sending;
    $("send").disabled = !canSend();
    if (state.last_error) showError(state.last_error);
    refreshStorage();
    conversationNow = conversation;
    showFiltered();
    const now = Date.now() / 1000;
    markers = conversation
      .filter((m) => m.kind === "received" && m.frequency_hz !== null && now - m.at < MARKER_SECONDS)
      .map((m) => ({ hz: m.frequency_hz, at: m.at }));
    drawScope();
  } catch (error) { showError("The application does not answer."); }
}

fitAll();
(async () => { fillDevices((await call("/api/devices")).devices); lastSettings = null; refresh(); askEstimate(); grow(); })();
setInterval(refresh, 1000);
setInterval(refreshSpectrum, 500);

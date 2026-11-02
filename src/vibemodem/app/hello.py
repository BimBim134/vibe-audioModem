"""Hello application for the packaging spike (issue #3).

A loopback-only web page that lists audio inputs, records a few seconds of sound and runs
a small DSP self-test. It exists to prove that Python, NumPy/SciPy, an audio library and a
local web server can be packaged and run by a non-developer, not to be the real application.
"""

import argparse
import os
import socket
import sys
import threading
import webbrowser
from collections.abc import Callable

import numpy as np
import scipy.signal
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from vibemodem.io.audio import AudioError, AudioLibraryUnavailableError, SoundCard
from vibemodem.io.levels import check_level

SELFTEST_TONE_HZ = 1000
SELFTEST_SAMPLE_RATE = 48_000

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vibe AudioModem</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }
  button { font-size: 1rem; padding: 0.5rem 1rem; margin: 0.25rem 0.25rem 0.25rem 0; }
  pre { background: #f2f2f2; padding: 0.75rem; overflow-x: auto; }
</style>
</head>
<body>
<h1>Vibe AudioModem</h1>
<p>Packaging check. This page is served from your own computer only.</p>
<label>Audio input: <select id="device"><option value="">default</option></select></label>
<p>
  <button id="record">Record 5 seconds</button>
  <button id="selftest">DSP self-test</button>
  <button id="quit">Quit</button>
</p>
<pre id="out">Ready.</pre>
<script>
const out = document.getElementById("out");
const show = (x) => { out.textContent = typeof x === "string" ? x : JSON.stringify(x, null, 2); };
async function call(path, options) {
  const r = await fetch(path, options);
  return { ok: r.ok, body: await r.json() };
}
(async () => {
  const { body } = await call("/api/devices");
  const select = document.getElementById("device");
  for (const d of body.devices) {
    const o = document.createElement("option");
    o.value = d.index; o.textContent = d.name; select.appendChild(o);
  }
})();
document.getElementById("record").onclick = async () => {
  show("Recording for 5 seconds...");
  const device = document.getElementById("device").value;
  const { body } = await call("/api/record", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seconds: 5, device: device === "" ? null : Number(device) }),
  });
  show(body);
};
document.getElementById("selftest").onclick = async () => show((await call("/api/selftest")).body);
document.getElementById("quit").onclick = async () => {
  await call("/api/quit", { method: "POST" });
  show("Stopped. You can close this tab.");
};
</script>
</body>
</html>
"""


class RecordRequest(BaseModel):
    seconds: float = Field(5.0, gt=0, le=30)
    device: int | None = None


def _selftest_detected_hz() -> float:
    t = np.arange(2 * SELFTEST_SAMPLE_RATE) / SELFTEST_SAMPLE_RATE
    tone = np.sin(2 * np.pi * SELFTEST_TONE_HZ * t)
    freqs, power = scipy.signal.welch(tone, fs=SELFTEST_SAMPLE_RATE, nperseg=SELFTEST_SAMPLE_RATE)
    return float(freqs[np.argmax(power)])


def create_app(
    *,
    record: Callable[..., np.ndarray],
    list_devices: Callable[[], list[dict]],
    on_quit: Callable[[], None],
) -> FastAPI:
    app = FastAPI(title="Vibe AudioModem (packaging spike)")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/devices")
    def devices() -> dict:
        try:
            return {"devices": list_devices(), "audio_library": "ok"}
        except AudioLibraryUnavailableError as exc:
            return {"devices": [], "audio_library": f"unavailable: {exc}"}
        except AudioError:
            return {"devices": [], "audio_library": "ok"}

    @app.post("/api/record")
    def record_audio(request: RecordRequest) -> dict:
        try:
            samples = record(request.seconds, device=request.device)
        except AudioError as exc:
            raise HTTPException(status_code=503, detail=f"No usable audio input: {exc}") from exc
        return {
            "seconds": request.seconds,
            "samples": int(samples.size),
            "rms": float(np.sqrt(np.mean(np.square(samples)))),
            "peak": float(np.max(np.abs(samples))),
            "warnings": check_level(samples).messages,
        }

    @app.get("/api/selftest")
    def selftest() -> dict:
        return {"tone_hz": SELFTEST_TONE_HZ, "detected_hz": _selftest_detected_hz()}

    @app.post("/api/quit")
    def quit_app() -> dict:
        on_quit()
        return {"status": "stopping"}

    return app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ensure_std_streams() -> None:
    # A windowed (no console) packaged app has no stdout/stderr; some libraries crash on None.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115


def _open_browser_when_ready(server: uvicorn.Server, url: str) -> None:
    while not server.started:
        if server.should_exit:
            return
        threading.Event().wait(0.1)
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Vibe AudioModem packaging check")
    parser.add_argument("--port", type=int, default=0, help="loopback port (default: a free one)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)

    _ensure_std_streams()
    port = args.port or _free_port()

    def on_quit() -> None:
        server.should_exit = True

    card = SoundCard()

    def list_inputs() -> list[dict]:
        return [
            {"index": d.index, "name": d.name, "max_input_channels": d.inputs}
            for d in card.list_devices()
            if d.inputs
        ]

    app = create_app(record=card.record, list_devices=list_inputs, on_quit=on_quit)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    if not args.no_browser:
        url = f"http://127.0.0.1:{port}/"
        threading.Thread(target=_open_browser_when_ready, args=(server, url), daemon=True).start()
    server.run()

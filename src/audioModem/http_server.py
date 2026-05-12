import logging
from typing import Optional, TYPE_CHECKING, List
import time

import uvicorn
from fastapi import FastAPI, Request
import zmq

if TYPE_CHECKING:
    from src.audioModem.audioModem import ModemController

logger = logging.getLogger(__name__)

app = FastAPI(title="Vibe AudioModem")
_controller: Optional["ModemController"] = None


def set_controller(controller: "ModemController"):
    global _controller
    _controller = controller


@app.get("/status")
async def get_status():
    return _controller.handle_get_status()


@app.get("/configuration")
async def get_configuration():
    return _controller.handle_get_config()


@app.get("/messages")
async def get_messages():
    messages = _controller.get_received_messages()
    return {"messages": messages}


@app.get("/fft")
async def get_fft_snapshot():
    """Return a single FFT snapshot from the fft_port."""
    try:
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        socket.connect(f"tcp://127.0.0.1:{_controller.ports_conf.fft_port}")
        socket.setsockopt(zmq.RCVTIMEO, 1000)
        try:
            msg = socket.recv()
            import numpy as np
            data = np.frombuffer(msg, dtype=np.float32).tolist()
            return {"status": "ok", "fft": data}
        except zmq.Again:
            return {"status": "error", "error": "No FFT data available within timeout"}
        finally:
            socket.close()
            context.term()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/logs")
async def get_logs(lines: int = 100):
    """Return the last N lines of audiomodem.log."""
    try:
        with open("audiomodem.log", "r") as f:
            content = f.readlines()
        return {"status": "ok", "logs": content[-lines:]}
    except FileNotFoundError:
        return {"status": "error", "error": "Log file not found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/receive")
async def receive(request: Request):
    data = await request.json()
    return _controller.handle_receive(data)


@app.post("/setup")
async def setup(request: Request):
    data = await request.json()
    return _controller.handle_setup(data)


@app.post("/transmit")
async def transmit(request: Request):
    data = await request.json()
    return _controller.handle_transmit(data)


@app.post("/stop")
async def stop(request: Request):
    data = await request.json()
    return _controller.handle_stop(data)


@app.post("/quit")
async def quit_modem():
    return _controller.handle_quit()


@app.post("/test")
async def set_test_mode(request: Request):
    data = await request.json()
    return _controller.handle_test(data)


def run_http_server(host: str = "0.0.0.0", port: int = 8000, stop_event=None):
    logger.info(f"Starting HTTP server on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s: %(processName)s: %(levelname)s: %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.FileHandler",
                    "filename": "audiomodem.log",
                },
            },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"propagate": False},
        },
        },
    )

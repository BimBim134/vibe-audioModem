import logging
from typing import Optional, TYPE_CHECKING

import uvicorn
from fastapi import FastAPI, Request

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


@app.get("/config")
async def get_config():
    return _controller.handle_get_config()


@app.post("/transmit")
async def transmit(request: Request):
    data = await request.json()
    return _controller.handle_transmit(data)


@app.post("/preset")
async def set_preset(request: Request):
    data = await request.json()
    return _controller.handle_set_preset(data)


@app.post("/carrier")
async def set_carrier_freq(request: Request):
    data = await request.json()
    return _controller.handle_set_carrier_freq(data)


@app.post("/cancel")
async def cancel_queue():
    return _controller.handle_cancel_queue({})


@app.get("/messages")
async def get_messages():
    messages = _controller.get_received_messages()
    return {"messages": messages}


def run_http_server(host: str = "0.0.0.0", port: int = 8000, stop_event=None):
    logger.info(f"Starting HTTP server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

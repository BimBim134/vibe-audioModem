"""The local HTTP API and its page: a thin layer over `ModemService`."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from vibemodem.app.page import PAGE
from vibemodem.app.service import BusyError, Cancelled, ModemService, SettingsError
from vibemodem.core.message import MAX_MESSAGE_BYTES
from vibemodem.core.transmission import MAX_COPIES, MessageTooLong
from vibemodem.io.audio import AudioError, AudioLibraryUnavailableError

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=4 * MAX_MESSAGE_BYTES)
    copies: int = Field(1, ge=1, le=MAX_COPIES)
    frequency_hz: float | None = None


class SendRequest(EstimateRequest):
    """What it takes to send is what it takes to estimate."""


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: str | None = None
    input_device: int | str | None = None
    output_device: int | str | None = None


def create_app(service: ModemService, *, on_quit: Callable[[], None] = lambda: None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app):
        yield
        service.close()  # the server is stopping: free the sound card and the threads

    app = FastAPI(title="Vibe AudioModem", lifespan=lifespan)

    @app.middleware("http")
    async def only_this_computer(request: Request, call_next):
        # A web page open in the browser must not be able to make this one transmit: the Host
        # must be a loopback name (against DNS rebinding) and an Origin, if any, our own.
        header = request.headers.get("host") or ""
        host = header.split("]")[0] + "]" if header.startswith("[") else header.split(":")[0]
        if host not in LOOPBACK_HOSTS:
            return JSONResponse({"detail": "this address is not allowed"}, status_code=421)
        # A browser always sends the Origin of a cross-site POST, so a request without one is
        # not a web page's: another program on this computer, which is trusted anyway.
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
            return JSONResponse({"detail": "cross-site requests are refused"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(SettingsError)
    @app.exception_handler(MessageTooLong)
    async def invalid(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.exception_handler(Cancelled)
    @app.exception_handler(BusyError)
    async def busy(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(AudioError)
    async def audio_trouble(_request, error):
        return JSONResponse({"detail": f"audio problem: {error}"}, status_code=503)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/status")
    def status() -> dict:
        return service.status()

    @app.get("/api/devices")
    def devices() -> dict:
        try:
            found = [asdict(d) for d in service.devices()]
        except AudioLibraryUnavailableError as error:
            return {"devices": [], "audio_library": f"unavailable: {error}"}
        except AudioError as error:
            return {"devices": [], "audio_library": "ok", "error": str(error)}
        return {"devices": found, "audio_library": "ok"}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return service.status()["settings"]

    @app.post("/api/settings")
    def set_settings(request: SettingsRequest) -> dict:
        changes = {name: getattr(request, name) for name in request.model_fields_set}
        service.apply_settings(**changes)
        return service.status()["settings"]

    @app.post("/api/send")
    def send(request: SendRequest) -> dict:
        try:
            sent = service.send(
                request.text, copies=request.copies, frequency_hz=request.frequency_hz
            )
            return asdict(sent)
        except (SettingsError, MessageTooLong, BusyError, AudioError):
            raise
        except ValueError as error:  # what the service refuses in the request itself
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/estimate")
    def estimate(request: EstimateRequest) -> dict:
        return asdict(service.estimate(request.text, request.copies, request.frequency_hz))

    @app.post("/api/cancel")
    def cancel() -> dict:
        return {"cancelled": service.cancel()}

    @app.post("/api/listen/start")
    def start_listening() -> dict:
        service.start_listening()
        return {"listening": True}

    @app.post("/api/listen/stop")
    def stop_listening() -> dict:
        return {"listening": False, "was_listening": service.stop_listening()}

    @app.get("/api/received")
    def received() -> dict:
        return {"received": [asdict(item) for item in service.received()]}

    @app.get("/api/selftest")
    def selftest() -> dict:
        return {"roundtrip_ok": service.selftest()}

    @app.post("/api/quit")
    def quit_app() -> dict:
        on_quit()
        return {"status": "stopping"}

    return app

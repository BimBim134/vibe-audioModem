"""The local HTTP API and its page: a thin layer over `ModemService`."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from vibemodem.app.service import BusyError, Cancelled, ModemService, SettingsError
from vibemodem.core.message import MAX_MESSAGE_BYTES
from vibemodem.core.spectrum import BAND_HZ, BIN_HZ
from vibemodem.core.transmission import MAX_COPIES, MessageTooLong
from vibemodem.io.audio import AudioError, AudioLibraryUnavailableError

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
# Next to this module, also in the packaged application (see packaging/vibemodem.spec). It is read
# at each request, so that a change to the page (its colours, for instance) shows on reload.
PAGE_FILE = Path(__file__).with_name("page.html")


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=4 * MAX_MESSAGE_BYTES)
    copies: int = Field(1, ge=1, le=MAX_COPIES)
    frequency_hz: float | None = None


class SendRequest(EstimateRequest):
    """What it takes to send is what it takes to estimate."""


class StorageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep: bool | None = None
    limit_mb: int | None = None


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
        return PAGE_FILE.read_text(encoding="utf-8")

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

    @app.get("/api/storage")
    def get_storage() -> dict:
        return service.storage()

    @app.post("/api/storage")
    def set_storage(request: StorageRequest) -> dict:
        return service.set_storage(request.keep, request.limit_mb)

    @app.post("/api/storage/clear")
    def clear_storage() -> dict:
        return {"deleted": service.clear_receptions()}

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
        return {
            "received": [asdict(item) for item in service.received()],
            "undecoded": [asdict(item) for item in service.undecoded()],
        }

    @app.get("/api/conversation")
    def conversation() -> dict:
        return {"items": service.conversation()}

    @app.get("/api/spectrum")
    def spectrum(since: int = Query(0, ge=0)) -> dict:
        rows = service.spectrum(since)
        return {**asdict(rows), "low_hz": BAND_HZ[0], "bin_hz": BIN_HZ}

    @app.get("/api/selftest")
    def selftest() -> dict:
        return {"roundtrip_ok": service.selftest()}

    @app.post("/api/quit")
    def quit_app() -> dict:
        on_quit()
        return {"status": "stopping"}

    return app

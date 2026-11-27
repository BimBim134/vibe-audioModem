"""Start the local application: a web page on the loopback interface, served by one process."""

import argparse
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from vibemodem.app import logs
from vibemodem.app.api import create_app
from vibemodem.app.history import History
from vibemodem.app.service import DEFAULT_LIMIT_MB, MEGABYTE, ModemService
from vibemodem.app.settings_file import SettingsFile
from vibemodem.app.store import ReceptionStore, default_directory
from vibemodem.io.audio import SoundCard


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ensure_std_streams() -> None:
    # A windowed (no console) packaged app has no stdout/stderr; some libraries crash on None.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115


def make_server(service: ModemService, port: int) -> uvicorn.Server:
    """A server for the service on the loopback interface only; `should_exit` stops it."""

    def on_quit() -> None:
        server.should_exit = True

    app = create_app(service, on_quit=on_quit)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    return server


def _open_browser_when_ready(server: uvicorn.Server, url: str) -> None:
    while not server.started:
        if server.should_exit:
            return
        threading.Event().wait(0.1)
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Vibe AudioModem")
    parser.add_argument("--port", type=int, default=0, help="loopback port (default: a free one)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument(
        "--receptions-dir",
        type=Path,
        default=default_directory(),
        help="where receptions are kept when the page asks for it (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning"],
        default="info",
        help="how much the log file tells (default: %(default)s); debug is for finding a bug",
    )
    args = parser.parse_args(argv)

    _ensure_std_streams()
    logs.setup(args.receptions_dir, args.log_level)
    logs.banner(sys.argv[1:] if argv is None else argv)
    port = args.port or free_port()
    store = ReceptionStore(args.receptions_dir, DEFAULT_LIMIT_MB * MEGABYTE)
    settings_file = SettingsFile(args.receptions_dir / "settings.json")
    history = History(args.receptions_dir / "history.sqlite3")
    service = ModemService(SoundCard(), store=store, settings_file=settings_file, history=history)
    server = make_server(service, port)
    if not args.no_browser:
        url = f"http://127.0.0.1:{port}/"
        threading.Thread(target=_open_browser_when_ready, args=(server, url), daemon=True).start()
    try:
        server.run()
        logs.log.info("stopped")
    except KeyboardInterrupt:
        logs.log.info("stopped with Ctrl+C")
        # Ctrl+C: uvicorn has already stopped the server and the service is closed with it; it
        # only raises the interruption again at the end, which would print a traceback.
        print("Stopped.", file=sys.stderr)

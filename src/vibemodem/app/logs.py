"""The log file: what the application did and what went wrong, to find the cause of a bug.

It is `vibemodem.log` in the data folder, cut into a few files of bounded size, and holds no
sound and no text of a Message. Warnings and errors are also written to the terminal.
"""

import logging
import logging.handlers
import platform
import sys
import threading
from pathlib import Path

from vibemodem import version

NAME = "vibemodem.log"
MAX_BYTES = 1_000_000
BACKUPS = 4
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

log = logging.getLogger("vibemodem")
_handlers: list[logging.Handler] = []
_hooks: dict = {}
_file: list[Path] = []  # the log file now written, if any


def setup(
    directory: Path, level: str = "INFO", max_bytes: int = MAX_BYTES, backups: int = BACKUPS
) -> Path | None:
    """Write the log in `directory`. Returns the file, or None if it cannot be written (the
    application then goes on, with the terminal only)."""
    teardown()
    log.setLevel(getattr(logging, level.upper()))
    formatter = logging.Formatter(FORMAT)
    path: Path | None = Path(directory) / NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        _handlers.append(handler)
        _file.append(path)
    except OSError as error:
        path = None
        print(f"the log file cannot be written: {error}", file=sys.stderr)
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(formatter)
        _handlers.append(console)
    for handler in _handlers:
        log.addHandler(handler)
    _hooks["thread"], _hooks["main"] = threading.excepthook, sys.excepthook
    threading.excepthook = _thread_failed
    sys.excepthook = _main_failed
    return path


def teardown() -> None:
    """Close the log and put the error hooks back."""
    for handler in _handlers:
        log.removeHandler(handler)
        handler.close()
    _handlers.clear()
    _file.clear()
    if _hooks:
        threading.excepthook, sys.excepthook = _hooks["thread"], _hooks["main"]
        _hooks.clear()


def _thread_failed(args) -> None:
    log.critical(
        "a thread (%s) ended with an error",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    _hooks["thread"](args)


def _main_failed(kind, error, trace) -> None:
    log.critical("the application ended with an error", exc_info=(kind, error, trace))
    _hooks["main"](kind, error, trace)


def banner(arguments: list[str]) -> None:
    """What a report needs to be understood: the version, the machine and the sound libraries."""
    info = version.describe()
    log.info("Vibe AudioModem %s%s", info["version"], f" ({info['git']})" if info["git"] else "")
    log.info("Python %s, system: %s", platform.python_version(), platform.platform())
    log.info("arguments: %s", " ".join(arguments) or "(none)")
    try:
        import sounddevice as sd

        log.info("sounddevice %s, %s", sd.__version__, sd.get_portaudio_version()[1])
        for number, api in enumerate(sd.query_hostapis()):
            log.info(
                "audio host %d: %s, default output %s",
                number,
                api["name"],
                api["default_output_device"],
            )
        for number, device in enumerate(sd.query_devices()):
            log.info(
                "audio device %d: %s (in %d, out %d, %.0f Hz, host %d)",
                number,
                device["name"],
                device["max_input_channels"],
                device["max_output_channels"],
                device["default_samplerate"],
                device["hostapi"],
            )
    except Exception as error:  # a missing library is itself what the report must say
        log.warning("the sound library cannot be read: %s", error)


def read_all() -> bytes | None:
    """The whole log, oldest part first; None if no log file is written."""
    if not _file:
        return None
    base = _file[0]
    backups = sorted(
        (p for p in base.parent.glob(NAME + ".*") if p.suffix[1:].isdigit()),
        key=lambda p: -int(p.suffix[1:]),
    )
    return b"".join(p.read_bytes() for p in [*backups, base] if p.is_file())

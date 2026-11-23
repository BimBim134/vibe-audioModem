"""Ctrl+C in the terminal stops the application cleanly: no traceback, and it exits normally."""

import signal
import subprocess
import sys
import time
import urllib.request

import pytest

from vibemodem.app.main import free_port


@pytest.mark.skipif(sys.platform == "win32", reason="a console signal is not sent this way")
def test_ctrl_c_stops_the_application_without_a_traceback(tmp_path):
    port = free_port()
    app = subprocess.Popen(
        [sys.executable, "-m", "vibemodem.app", "--port", str(port), "--no-browser",
         "--receptions-dir", str(tmp_path)],
        stderr=subprocess.PIPE,
        text=True,
    )  # fmt: skip
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        app.send_signal(signal.SIGINT)
        assert app.wait(timeout=20) == 0
        assert "Traceback" not in app.stderr.read()
    finally:
        if app.poll() is None:
            app.kill()
        app.stderr.close()

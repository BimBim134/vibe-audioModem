"""Start a packaged build, check it serves its page and runs DSP, then stop it.

Usage: python packaging/smoke_test.py <path-to-packaged-executable> [--require-audio-library]

It cannot check sending or listening through a real sound card: CI machines have no audio.
That part is verified by hand on a clean machine (see docs/packaging/procedure-packaging-check.md).
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def get(path, method="GET"):
    request = urllib.request.Request(BASE + path, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode()


def wait_until_up(process, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"packaged app exited early with code {process.returncode}")
        try:
            if get("/api/health")[0] == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.5)
    raise SystemExit("packaged app did not start in time")


def main(executable, require_audio_library):
    process = subprocess.Popen([executable, "--no-browser", "--port", str(PORT)])
    try:
        wait_until_up(process)
        status, page = get("/")
        assert status == 200 and "Vibe AudioModem" in page, "page not served"
        assert 'id="send"' in page and 'id="listen"' in page, "page has no send or listen"
        # The modem against itself without noise: NumPy, SciPy and the whole core are bundled.
        assert json.loads(get("/api/selftest")[1])["roundtrip_ok"], "modem self-test failed"
        assert json.loads(get("/api/status")[1])["listening"] is False
        audio = json.loads(get("/api/devices")[1])["audio_library"]
        # CI has no microphone, but the bundled audio library must still load.
        assert audio == "ok" or not require_audio_library, f"audio library: {audio}"
        get("/api/quit", method="POST")
        process.wait(timeout=20)
    finally:
        if process.poll() is None:
            process.kill()
    print("smoke test passed")


if __name__ == "__main__":
    # On Linux the audio library comes from the system, so only Windows/macOS builds require it.
    main(sys.argv[1], require_audio_library="--require-audio-library" in sys.argv)

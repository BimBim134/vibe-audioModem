"""Start a packaged build, check it serves its page and runs DSP, then stop it.

Usage: python packaging/smoke_test.py <path-to-packaged-executable> [--require-audio-library]

It cannot check recording from a real microphone: CI machines have no audio input.
That part is verified by hand on a clean machine (see docs/packaging-spike.md).
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
        assert status == 200 and "Record 5 seconds" in page, "page not served"
        detected = json.loads(get("/api/selftest")[1])["detected_hz"]
        assert abs(detected - 1000) <= 1, f"DSP self-test failed: {detected}"
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

import cmd
import requests
import sys
import threading
import time

try:
    import readline
except ImportError:
    pass


class ModemCLI(cmd.Cmd):
    intro = "\n=== vibe-audio-modem CLI ===\nType 'help' for commands.\n"

    prompt = "Vibe Audiomodem >> "

    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.base_url = base_url
        self._message_poller = None
        self._stop_poller = threading.Event()

    def _poll_messages(self):
        while not self._stop_poller.is_set():
            try:
                resp = requests.get(f"{self.base_url}/messages", timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data.get("messages", [])
                    for msg in messages:
                        self._display_message(msg)
            except Exception:
                pass
            self._stop_poller.wait(1.0)

    def _display_message(self, msg: dict):
        sender = msg.get("sender_name", "unknown")
        msg_type = msg.get("type", "unknown")
        if msg_type == "data":
            data = msg.get("data", "")
            if isinstance(data, str):
                print(f"\n[Received from {sender}]: {data}\n{self.prompt}", end="")
            else:
                print(
                    f"\n[Received from {sender}]: (binary data)\n{self.prompt}", end=""
                )
        else:
            print(f"\n[System message]: {msg}\n{self.prompt}", end="")

    def start_message_polling(self):
        self._stop_poller.clear()
        self._message_poller = threading.Thread(target=self._poll_messages, daemon=True)
        self._message_poller.start()

    def stop_message_polling(self):
        self._stop_poller.set()
        if self._message_poller:
            self._message_poller.join(timeout=2.0)

    def _api_get(self, endpoint: str) -> dict:
        try:
            resp = requests.get(f"{self.base_url}{endpoint}", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            print("Error: Cannot connect to modem. Is the server running?")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def _api_post(self, endpoint: str, data: dict) -> dict:
        try:
            resp = requests.post(f"{self.base_url}{endpoint}", json=data, timeout=2)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            print("Error: Cannot connect to modem. Is the server running?")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def cmdloop(self, intro=None):
        self.preloop()
        if intro is not None:
            self.intro = intro
        if self.intro:
            print(self.intro)
        while True:
            try:
                line = input(self.prompt)
                line = self.precmd(line)
                stop = self.onecmd(line)
                stop = self.postcmd(stop, line)
                if stop:
                    break
            except SystemExit:
                break
        except KeyboardInterrupt:
            self.intr = None
            print("^C")
            self._api_post("/quit", {})
            print("Goodbye!")
            break
        except EOFError:
            print("^D")
            self._api_post("/quit", {})
            print("Goodbye!")
            break
        self.postloop()

    def do_send(self, arg):
        """send <message> - Send a message"""
        if not arg:
            print("Usage: send <message>")
            return
        result = self._api_post("/transmit", {"message": arg})
        if result:
            print(f"Queued: {arg}")

    def do_receive(self, arg):
        """receive [-n NB_WORKERS] - Start receiver with N workers (default: 1)"""
        import re

        nb_workers = 1
        match = re.search(r"-n\s+(\d+)", arg)
        if match:
            nb_workers = int(match.group(1))
        result = self._api_post("/receive", {"nb_workers": nb_workers})
        if result:
            if result.get("status") == "ok":
                print(f"Receiver started with {result.get('nb_workers')} workers")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

    def do_status(self, arg):
        """Show modem status"""
        result = self._api_get("/status")
        if result:
            print(f"is_transmitting: {result.get('is_transmitting', 'N/A')}")
            print(f"queue_size: {result.get('queue_size', 'N/A')}")

    def do_setup(self, arg):
        """setup <json_file_or_inline_json> - Full modem reset with config"""
        if not arg:
            print("Usage: setup <json_file_or_inline_json>")
            return
        import json
        import os

        # Check if arg is a file path
        if os.path.exists(arg.strip()):
            try:
                with open(arg.strip(), "r") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Error reading file: {e}")
                return
        else:
            try:
                data = json.loads(arg)
            except json.JSONDecodeError:
                print("Error: Invalid JSON or file not found")
                return
        result = self._api_post("/setup", data)
        if result:
            if result.get("status") == "ok":
                print("Modem setup complete")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

    def do_stop(self, arg):
        """stop [-rx] [-tx] - Stop receiver (-rx) and/or transmitter (-tx)"""
        rx = "-rx" in arg
        tx = "-tx" in arg
        if not rx and not tx:
            print("Usage: stop -rx and/or -tx")
            return
        result = self._api_post("/stop", {"rx": rx, "tx": tx})
        if result:
            if result.get("status") == "ok":
                print(f"Stopped: {', '.join(result.get('stopped', []))}")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

    def do_config(self, arg):
        """Show current configuration"""
        result = self._api_get("/configuration")
        if result:
            sig = result.get("signal", {})
            pkt = result.get("packet", {})
            port = result.get("port", {})
            print("Signal config:")
            print(f"  samp_rate: {sig.get('samp_rate')}")
            print(f"  carrier_freq: {sig.get('carrier_freq')}")
            print(f"  baudrate: {sig.get('baudrate')}")
            print(f"  constellation: {sig.get('constellation_name')}")
            print("Packet config:")
            print(f"  total_packets_len: {pkt.get('total_packets_len')}")
            print(f"  preamble_packets: {pkt.get('preamble_packets')}")
            print(f"  postamble_packets: {pkt.get('postamble_packets')}")
            print(f"  error_correction_len: {pkt.get('error_correction_len')}")
            print("Port config:")
            for key, val in port.items():
                print(f"  {key}: {val}")

    def do_fft(self, arg):
        """fft - Get FFT snapshot for monitoring"""
        result = self._api_get("/fft")
        if result:
            if result.get("status") == "ok":
                fft_data = result.get("fft", [])
                print(f"FFT snapshot: {len(fft_data)} points")
                if len(fft_data) > 10:
                    print(f"  First 5: {fft_data[:5]}")
                    print(f"  Last 5: {fft_data[-5:]}")
            else:
                print(f"Error: {result.get('error', 'No FFT data available')}")

    def do_logs(self, arg):
        """logs [lines] - Show last N lines of logs (default: 20)"""
        lines = 20
        if arg:
            try:
                lines = int(arg)
            except ValueError:
                print("Error: lines must be a number")
                return
        result = self._api_get(f"/logs?lines={lines}")
        if result:
            if result.get("status") == "ok":
                for line in result.get("logs", []):
                    print(line.rstrip())
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

    def do_exit(self, arg):
        """exit - Shutdown modem and exit CLI"""
        self._api_post("/quit", {})
        print("Goodbye!")
        return True

    def do_clear(self, arg):
        """Clear the screen"""
        print("\033[2J\033[H", end="")

    def emptyline(self):
        pass


def start_cli(base_url: str = "http://localhost:8000", cli_exit_event=None):
    sys.stdin = sys.__stdin__
    cli = ModemCLI(base_url=base_url)
    cli.start_message_polling()
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\nExiting CLI...")
    except SystemExit:
        pass
    finally:
        cli.stop_message_polling()
    if cli_exit_event:
        cli_exit_event.set()

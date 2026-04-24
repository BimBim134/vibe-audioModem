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

    prompt = "modem> "

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
                print(f"\n[Received from {sender}]: (binary data)\n{self.prompt}", end="")
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
                break
            except EOFError:
                print("^D")
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

    def do_status(self, arg):
        """Show modem status"""
        result = self._api_get("/status")
        if result:
            print(f"is_transmitting: {result.get('is_transmitting', 'N/A')}")
            print(f"queue_size: {result.get('queue_size', 'N/A')}")

    def do_config(self, arg):
        """Show current configuration"""
        result = self._api_get("/config")
        if result:
            sig = result.get("signal", {})
            print("Signal config:")
            print(f"  samp_rate: {sig.get('samp_rate')}")
            print(f"  carrier_freq: {sig.get('carrier_freq')}")
            print(f"  baudrate: {sig.get('baudrate')}")
            print(f"  constellation: {sig.get('constellation_name')}")

    def do_preset(self, arg):
        """preset <FAST|MEDIUM|SLOW> - Set modulation preset"""
        if not arg:
            print("Usage: preset <FAST|MEDIUM|SLOW>")
            return
        result = self._api_post("/preset", {"preset": arg.upper()})
        if result:
            if result.get("status") == "ok":
                print(f"Preset set: {result.get('preset')} (baudrate={result.get('baudrate')})")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

    def do_carrier(self, arg):
        """carrier <freq> - Set carrier frequency (Hz)"""
        if not arg:
            print("Usage: carrier <frequency>")
            return
        try:
            freq = float(arg)
        except ValueError:
            print("Error: Frequency must be a number")
            return
        result = self._api_post("/carrier", {"frequency": freq})
        if result:
            if result.get("status") == "ok":
                print(f"Carrier set to: {result.get('frequency')} Hz")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

    def do_exit(self, arg):
        """Exit the CLI (cancels queue and stops backend)"""
        self._api_post("/cancel", {})
        print("Goodbye!")
        return True

    def do_quit(self, arg):
        """Exit the CLI (same as exit)"""
        self._api_post("/cancel", {})
        print("Goodbye!")
        return True

    def do_EOF(self, arg):
        """Handle Ctrl+D"""
        print()
        self._api_post("/cancel", {})
        print("Goodbye!")
        return True

    def do_clear(self, arg):
        """Clear the screen"""
        print("\033[2J\033[H", end="")

    def do_cancel(self, arg):
        """Cancel pending and in-progress transmissions"""
        result = self._api_post("/cancel", {})
        if result:
            print("Transmission queue cancelled")

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

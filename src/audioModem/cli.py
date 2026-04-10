import cmd
import requests
import sys

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
            resp = requests.post(f"{self.base_url}{endpoint}", json=data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            print("Error: Cannot connect to modem. Is the server running?")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

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
        return self.do_exit(arg)

    def do_EOF(self, arg):
        """Handle Ctrl+D"""
        print()
        return self.do_exit(arg)

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


def start_cli(base_url: str = "http://localhost:8000"):
    sys.stdin = sys.__stdin__
    cli = ModemCLI(base_url=base_url)
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\nExiting CLI...")

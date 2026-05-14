import click
import json
import os
import shlex
import requests
import sys
import threading

try:
    import readline
except ImportError:
    pass


PROMPT = "Vibe Audiomodem >> "


class ModemState:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._message_poller = None
        self._stop_poller = threading.Event()

    def _poll_messages(self):
        while not self._stop_poller.is_set():
            try:
                resp = requests.get(f"{self.base_url}/messages", timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    for msg in data.get("messages", []):
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
                click.echo(f"\n[Received from {sender}]: {data}")
            else:
                click.echo(f"\n[Received from {sender}]: (binary data)")
        else:
            click.echo(f"\n[System message]: {msg}")

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
            click.echo("Error: Cannot connect to modem. Is the server running?")
            return None
        except Exception as e:
            click.echo(f"Error: {e}")
            return None

    def _api_post(self, endpoint: str, data: dict) -> dict:
        try:
            resp = requests.post(f"{self.base_url}{endpoint}", json=data, timeout=2)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            click.echo("Error: Cannot connect to modem. Is the server running?")
            return None
        except Exception as e:
            click.echo(f"Error: {e}")
            return None


@click.group()
def cli():
    """vibe-audio-modem CLI"""


@cli.command()
@click.argument("message")
@click.pass_obj
def send(state, message):
    """Send a message"""
    result = state._api_post("/transmit", {"message": message})
    if result:
        click.echo(f"Queued: {message}")


@cli.command()
@click.option("-n", "--nb-workers", default=1, type=int, help="Number of workers")
@click.pass_obj
def receive(state, nb_workers):
    """Start receiver with N workers"""
    result = state._api_post("/receive", {"nb_workers": nb_workers})
    if result:
        if result.get("status") == "ok":
            click.echo(f"Receiver started with {result.get('nb_workers')} workers")
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}")


@cli.command()
@click.pass_obj
def status(state):
    """Show modem status"""
    result = state._api_get("/status")
    if result:
        click.echo(f"is_transmitting: {result.get('is_transmitting', 'N/A')}")
        click.echo(f"queue_size: {result.get('queue_size', 'N/A')}")


@cli.command()
@click.argument("config")
@click.pass_obj
def setup(state, config):
    """Full modem reset with config (JSON file path or inline JSON)"""
    if os.path.exists(config.strip()):
        try:
            with open(config.strip()) as f:
                data = json.load(f)
        except Exception as e:
            click.echo(f"Error reading file: {e}")
            return
    else:
        try:
            data = json.loads(config)
        except json.JSONDecodeError:
            click.echo("Error: Invalid JSON or file not found")
            return
    result = state._api_post("/setup", data)
    if result:
        if result.get("status") == "ok":
            click.echo("Modem setup complete")
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}")


@cli.command()
@click.option("-rx", "stop_rx", is_flag=True, help="Stop receiver")
@click.option("-tx", "stop_tx", is_flag=True, help="Stop transmitter")
@click.pass_obj
def stop(state, stop_rx, stop_tx):
    """Stop receiver (-rx) and/or transmitter (-tx)"""
    if not stop_rx and not stop_tx:
        click.echo("Usage: stop -rx and/or -tx")
        return
    result = state._api_post("/stop", {"rx": stop_rx, "tx": stop_tx})
    if result:
        if result.get("status") == "ok":
            click.echo(f"Stopped: {', '.join(result.get('stopped', []))}")
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}")


@cli.command()
@click.pass_obj
def config(state):
    """Show current configuration"""
    result = state._api_get("/configuration")
    if result:
        sig = result.get("signal", {})
        pkt = result.get("packet", {})
        port = result.get("port", {})
        click.echo("Signal config:")
        click.echo(f"  samp_rate: {sig.get('samp_rate')}")
        click.echo(f"  carrier_freq: {sig.get('carrier_freq')}")
        click.echo(f"  baudrate: {sig.get('baudrate')}")
        click.echo(f"  constellation: {sig.get('constellation_name')}")
        click.echo("Packet config:")
        click.echo(f"  total_packets_len: {pkt.get('total_packets_len')}")
        click.echo(f"  preamble_packets: {pkt.get('preamble_packets')}")
        click.echo(f"  postamble_packets: {pkt.get('postamble_packets')}")
        click.echo(f"  error_correction_len: {pkt.get('error_correction_len')}")
        click.echo("Port config:")
        for key, val in port.items():
            click.echo(f"  {key}: {val}")


@cli.command()
@click.pass_obj
def fft(state):
    """Get FFT snapshot for monitoring"""
    result = state._api_get("/fft")
    if result:
        if result.get("status") == "ok":
            fft_data = result.get("fft", [])
            click.echo(f"FFT snapshot: {len(fft_data)} points")
            if len(fft_data) > 10:
                click.echo(f"  First 5: {fft_data[:5]}")
                click.echo(f"  Last 5: {fft_data[-5:]}")
        else:
            click.echo(f"Error: {result.get('error', 'No FFT data available')}")


@cli.command()
@click.argument("lines", default=20, type=int)
@click.pass_obj
def logs(state, lines):
    """Show last N lines of logs (default: 20)"""
    result = state._api_get(f"/logs?lines={lines}")
    if result:
        if result.get("status") == "ok":
            for line_ in result.get("logs", []):
                click.echo(line_.rstrip())
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}")


@cli.command(name="exit")
@click.pass_obj
def exit_cmd(state):
    """Shutdown modem and exit CLI"""
    state._api_post("/quit", {})
    click.echo("Goodbye!")
    sys.exit(0)


@cli.command()
def clear():
    """Clear the screen"""
    click.echo("\033[2J\033[H", nl=False)


@cli.command(name="help")
@click.argument("command", required=False)
@click.pass_context
def help_cmd(ctx, command):
    """Show help for commands"""
    if command:
        cmd_obj = cli.get_command(ctx, command)
        if cmd_obj:
            click.echo(cmd_obj.get_help(ctx))
        else:
            click.echo(f"No such command: {command}")
    else:
        click.echo(cli.get_help(ctx))


def interactive_loop(state):
    click.echo("\n=== vibe-audio-modem CLI ===")
    click.echo("Type 'help' for commands.")
    while True:
        try:
            line = input(PROMPT)
            if not line.strip():
                continue
            args = shlex.split(line)
            try:
                cli.main(args=args, obj=state, standalone_mode=False)
            except click.ClickException as e:
                click.echo(f"Error: {e.format_message()}")
            except SystemExit:
                break
        except KeyboardInterrupt:
            state._api_post("/quit", {})
            click.echo("\nGoodbye!")
            break
        except EOFError:
            state._api_post("/quit", {})
            click.echo("\nGoodbye!")
            break


def start_cli(base_url: str = "http://localhost:8000", cli_exit_event=None):
    sys.stdin = sys.__stdin__
    state = ModemState(base_url=base_url)
    state.start_message_polling()
    try:
        interactive_loop(state)
    except KeyboardInterrupt:
        click.echo("\nExiting CLI...")
    except SystemExit:
        pass
    finally:
        state.stop_message_polling()
    if cli_exit_event:
        cli_exit_event.set()

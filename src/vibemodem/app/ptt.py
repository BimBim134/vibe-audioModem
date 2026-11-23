"""Push to talk through Hamlib: the application asks `rigctld`, over TCP, to key the radio.

`rigctld` is started by the operator (`rigctld -m <rig number> -r <port> ...`); it can also key
a serial line (RTS or DTR), which is how an interface such as the Digirig keys a radio. One short
connection is made for each command, so a `rigctld` that is restarted between two Transmissions
costs nothing.
"""

import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4532  # the port rigctld listens on unless told otherwise
DEFAULT_BEFORE_MS = 100  # from the PTT on to the first sound
DEFAULT_AFTER_MS = 100  # from the last sound to the PTT off
MAX_DELAY_MS = 5_000
TIMEOUT_SECONDS = 3.0


class PttError(RuntimeError):
    pass


def check_flag(value) -> None:
    if not isinstance(value, bool):
        raise ValueError("the PTT setting must be true or false")


def check_host(value) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 253
        or any(c.isspace() for c in value)
    ):
        raise ValueError("the rigctld address must be a host name or an IP address")


def check_port(value) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65_535:
        raise ValueError("the rigctld port must be a whole number from 1 to 65535")


def check_delay(value) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_DELAY_MS:
        raise ValueError(f"a PTT delay must be a whole number of ms, 0 to {MAX_DELAY_MS}")


class RigctldPtt:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host, self.port = host, port

    def key(self, on: bool) -> None:
        """Key the radio (`on`) or release it. Raises `PttError` and says what went wrong."""
        command = f"T {1 if on else 0}\n"
        where = f"rigctld at {self.host}:{self.port}"
        try:
            with socket.create_connection((self.host, self.port), timeout=TIMEOUT_SECONDS) as link:
                link.settimeout(TIMEOUT_SECONDS)
                link.sendall(command.encode())
                answer = link.makefile("r").readline().strip()
        except OSError as error:
            raise PttError(f"PTT: cannot talk to {where} ({error}); is rigctld running?") from error
        if answer != "RPRT 0":
            raise PttError(f"PTT: {where} answered {answer or 'nothing'!r} to {command.strip()!r}")

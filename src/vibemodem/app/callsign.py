"""The Callsign of the station that sends a Message, written in front of its text.

The protocol has no field for it yet: the application adds `CALLSIGN: ` (the callsign, a colon, a
space) before the text of each Message the operator sends, and `callsign_of` reads it back from a
received text. To be reviewed when the protocol is reworked.
"""

import re

MIN_LENGTH, MAX_LENGTH = 3, 12
_BODY = r"[A-Z0-9]+(?:/[A-Z0-9]+)*"  # letters and digits, with a slash for a portable callsign
_CALLSIGN = re.compile(_BODY)
_PREFIX = re.compile(rf"({_BODY}): ")


def normalise(callsign: object) -> str | None:
    """The callsign in capitals, or None when there is none; ValueError if it cannot be one."""
    if callsign is None:
        return None
    if not isinstance(callsign, str):
        raise ValueError(f"the callsign is a text, got {callsign!r}")
    text = callsign.strip()
    if not text:
        return None
    text = text.upper() if text.isascii() else text
    if not MIN_LENGTH <= len(text) <= MAX_LENGTH or not _CALLSIGN.fullmatch(text):
        raise ValueError(
            f"{callsign!r} is not a callsign: {MIN_LENGTH} to {MAX_LENGTH} letters and digits, "
            "with a slash for a portable one such as F4JBO/P"
        )
    return text


def prefix(callsign: str | None) -> bytes:
    """What goes in front of the text of a Message sent by this callsign."""
    return b"" if callsign is None else f"{callsign}: ".encode("ascii")


def callsign_of(text: str) -> str | None:
    """The callsign a received text starts with, or None when it does not start with one."""
    found = _PREFIX.match(text)
    if found and MIN_LENGTH <= len(found[1]) <= MAX_LENGTH:
        return found[1]
    return None

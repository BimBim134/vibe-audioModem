"""Settings given on a command line as name=value."""

import json


def parse_settings(assignments: list[str]) -> dict:
    """ "name=value" pairs, each value a JSON literal (7, 0.9, "text"), as keyword arguments."""
    settings = {}
    for assignment in assignments:
        name, equals, text = assignment.partition("=")
        if not equals or not name:
            raise ValueError(f"expected name=value, got {assignment!r}")
        try:
            settings[name] = json.loads(text)
        except ValueError as error:
            raise ValueError(f"the value of {name} is not a JSON literal: {text!r}") from error
    return settings


def describe_settings(modem, options: dict) -> dict:
    """What a result file records about the settings given to a modem: nothing if none were."""
    if not options:
        return {}
    return {"modem_options": options, "modem_parameters": getattr(modem, "parameters", None)}

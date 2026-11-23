"""The settings kept between two runs of the application: a small JSON file.

What is read from it is not trusted: a missing or damaged file gives nothing, and the service
checks each value. Writing replaces the file in one step, and a failure to write is not an error
for the application: the settings then last until it quits.
"""

import json
import os
from pathlib import Path


class SettingsFile:
    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> dict:
        """What the file holds, or nothing when it is missing, unreadable or not an object."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def update(self, **values) -> None:
        """Set these values and keep whatever else the file holds."""
        data = self.read()
        data.update(values)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)  # a new installation has no folder
            temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

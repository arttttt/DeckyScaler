"""~/deckyscaler/patched.json: the directories the plugin has patched, what to call each, and for one on a removable
drive, which drive it is on.

It lets the library say which games use a version without searching every game's files.
Each directory's marker stays the truth about its patch; the index only says where to look. The plugin and the
launch wrappers write it from their own processes, one change at a time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from deckyscaler.infrastructure.files import locked, read_json, replace_json


@dataclass(frozen=True)
class Indexed:
    name: str
    """What to call the directory."""
    drive: str | None = None
    """The identity of the removable drive it is on (infrastructure/drives); None for one that isn't, or one indexed
    before drives were kept."""


def _indexed(value: object) -> Indexed:
    if isinstance(value, dict):
        drive = value.get("drive")
        return Indexed(str(value.get("name") or ""), drive if isinstance(drive, str) else None)
    return Indexed(str(value))  # before drives were kept: the name alone


class PatchIndex:
    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")

    def entries(self) -> dict[str, Indexed]:
        """Patched directory → what the index keeps of it."""
        return {str(directory): _indexed(value) for directory, value in read_json(self.path).items()}

    def add(self, directory: Path, name: str, drive: str | None = None) -> None:
        with locked(self.lock_path):
            self._write({**self.entries(), str(directory): Indexed(name, drive)})

    def remove(self, directory: Path) -> None:
        with locked(self.lock_path):
            index = self.entries()
            if index.pop(str(directory), None) is not None:
                self._write(index)

    def _write(self, index: dict[str, Indexed]) -> None:
        replace_json(self.path, {directory: asdict(entry) for directory, entry in index.items()})

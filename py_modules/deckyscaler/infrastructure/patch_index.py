"""~/deckyscaler/patched.json: the directories the plugin has patched, and what to call each.

It lets the library say which games use a version without searching every game's files.
Each directory's marker stays the truth about its patch; the index only says where to look.
"""

from __future__ import annotations

from pathlib import Path

from deckyscaler.infrastructure.files import read_json, replace_json


class PatchIndex:
    def __init__(self, path: Path):
        self.path = path

    def directories(self) -> dict[str, str]:
        """Patched directory → the name to show for it."""
        return {str(directory): str(name) for directory, name in read_json(self.path).items()}

    def add(self, directory: Path, name: str) -> None:
        self._write({**self.directories(), str(directory): name})

    def remove(self, directory: Path) -> None:
        index = self.directories()
        if index.pop(str(directory), None) is not None:
            self._write(index)

    def _write(self, index: dict[str, str]) -> None:
        replace_json(self.path, index)

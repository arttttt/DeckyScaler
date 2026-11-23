"""~/deckyscaler/patched.json: the directories the plugin has patched, and what to call each.

It lets the library say which games use a version without searching every game's files.
Each directory's marker stays the truth about its patch; the index only says where to look. The plugin and the
launch wrappers write it from their own processes, one change at a time.
"""

from __future__ import annotations

from pathlib import Path

from deckyscaler.infrastructure.files import locked, read_json, replace_json


class PatchIndex:
    def __init__(self, path: Path):
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")

    def directories(self) -> dict[str, str]:
        """Patched directory → the name to show for it."""
        return {str(directory): str(name) for directory, name in read_json(self.path).items()}

    def add(self, directory: Path, name: str) -> None:
        with locked(self.lock_path):
            replace_json(self.path, {**self.directories(), str(directory): name})

    def remove(self, directory: Path) -> None:
        with locked(self.lock_path):
            index = self.directories()
            if index.pop(str(directory), None) is not None:
                replace_json(self.path, index)

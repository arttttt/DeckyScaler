"""The user's libraries on disk: ~/deckyscaler/libraries/{entries,.partial}, and which of them go into games
(~/deckyscaler/settings/libraries.json)."""

from __future__ import annotations

from pathlib import Path

from deckyscaler.domain import library_choice, user_libraries
from deckyscaler.infrastructure.entry_store import EntryStore
from deckyscaler.infrastructure.files import read_json, replace_json


class UserLibraryStore(EntryStore):
    def __init__(self, root: Path):
        super().__init__(root, "entries", user_libraries.ENTRY_FILENAME)

    def installed(self) -> list[user_libraries.Library]:
        """Every library on disk with a readable entry; nothing else counts."""
        found = []
        for name, data in self.entries():
            parsed = user_libraries.parse_entry(data)
            if parsed is not None and parsed.id == name:
                found.append(parsed)
        return found

    def files_dir(self, library_id: str) -> Path:
        return self.item_dir(library_id) / user_libraries.FILES_DIRNAME

    def commit(self, stage: Path, library: user_libraries.Library) -> None:
        """Write the library's entry inside the staged library, then move it in by one rename."""
        self.commit_entry(stage, library.id, user_libraries.entry_json(library))


class LibraryChoicesStore:
    """The one file keeping which libraries go into games, written whole."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> library_choice.Choices:
        return library_choice.parse(read_json(self.path))

    def write(self, choices: library_choice.Choices) -> None:
        replace_json(self.path, library_choice.to_json(choices))

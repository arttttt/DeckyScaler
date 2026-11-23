"""The user's libraries on disk: ~/deckyscaler/libraries/{entries,.partial}, and which of them go into games
(~/deckyscaler/settings/libraries.json)."""

from __future__ import annotations

from pathlib import Path

from deckyscaler.domain import library_choice, user_libraries
from deckyscaler.infrastructure.entry_store import EntryStore
from deckyscaler.infrastructure.files import read_json, replace_json


class UserLibraryStore(EntryStore[user_libraries.Library]):
    """A library is whole only with every file its entry lists. One whose files went missing would fail every patch
    it goes into, the launch wrapper's too: it isn't on the device, and the games that have it lose it at their next
    patch."""

    def __init__(self, root: Path):
        super().__init__(root, "entries", user_libraries.ENTRY_FILENAME)

    def parse(self, data: object) -> user_libraries.Library | None:
        return user_libraries.parse_entry(data)

    def complete(self, entry: user_libraries.Library) -> bool:
        files = self.files_dir(entry.id)
        return all((files / path).is_file() for path in entry.files)

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

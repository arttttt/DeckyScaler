"""The user's libraries on disk: ~/deckyscaler/libraries/{entries,.partial}, and which of them go into games
(~/deckyscaler/settings/libraries.json)."""

from __future__ import annotations

import shutil
from pathlib import Path

from deckyscaler.domain import library_choice, user_libraries
from deckyscaler.infrastructure.entry_store import EntryStore
from deckyscaler.infrastructure.files import read_json, replace_json


class UserLibraryStore(EntryStore):
    def __init__(self, root: Path):
        super().__init__(root, "entries", user_libraries.ENTRY_FILENAME)

    def _scan(self) -> list[tuple[str, user_libraries.Library | None, bool]]:
        """Each directory in the store: its name, the library its entry describes (None when the entry doesn't read)
        and whether that library is whole: the directory's own, with every file it lists."""
        if not self.items_dir.is_dir():
            return []
        found = []
        for directory in sorted(path for path in self.items_dir.iterdir() if path.is_dir()):
            entry = user_libraries.parse_entry(read_json(directory / self.entry_filename))
            whole = entry is not None and entry.id == directory.name and self._complete(entry)
            found.append((directory.name, entry, whole))
        return found

    def installed(self) -> list[user_libraries.Library]:
        """Every whole library; nothing else counts. A library whose files went missing would fail every patch it
        goes into, the launch wrapper's too: it isn't on the device, and the games that have it lose it at their
        next patch."""
        return [entry for _, entry, whole in self._scan() if whole and entry is not None]

    def damaged(self) -> list[tuple[str, user_libraries.Library | None]]:
        """What is left of the libraries that aren't whole (their files or their entry gone, as an interrupted
        removal leaves them): each directory's name and what its entry still says, for Manage libraries to remove."""
        return [(name, entry) for name, entry, whole in self._scan() if not whole]

    def listed(self) -> set[str]:
        """Every directory's name, whole or damaged: the ids a removal may take, and nothing outside the store."""
        return {name for name, _, _ in self._scan()}

    def _complete(self, library: user_libraries.Library) -> bool:
        files = self.files_dir(library.id)
        return all((files / path).is_file() for path in library.files)

    def files_dir(self, library_id: str) -> Path:
        return self.item_dir(library_id) / user_libraries.FILES_DIRNAME

    def commit(self, stage: Path, library: user_libraries.Library) -> None:
        """Write the library's entry inside the staged library, then move it in by one rename, over what is left of
        a library of that id that isn't on the device any more."""
        shutil.rmtree(self.item_dir(library.id), ignore_errors=True)
        self.commit_entry(stage, library.id, user_libraries.entry_json(library))


class LibraryChoicesStore:
    """The one file keeping which libraries go into games, written whole."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> library_choice.Choices:
        return library_choice.parse(read_json(self.path))

    def write(self, choices: library_choice.Choices) -> None:
        replace_json(self.path, library_choice.to_json(choices))

"""Things the plugin keeps on the device as <root>/<items>/<id>/ with an entry file describing each: assembled in
<root>/.partial first, then moved in by one rename, so an interrupted download or unpack never leaves half an item.

Every directory in <items> is either a whole item (its entry reads, names that directory, and the store finds the
item complete) or what is left of a damaged one, listed so that it can be removed. Directories named with a dot are
a store's own working state (a version set aside while it is replaced), never an item."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from deckyscaler.infrastructure.files import read_json, write_json


class Entry(Protocol):
    @property
    def id(self) -> str: ...


E = TypeVar("E", bound=Entry)


class EntryStore(Generic[E]):
    def __init__(self, root: Path, items_dirname: str, entry_filename: str):
        self.root = root
        self.items_dir = root / items_dirname
        self.partial_dir = root / ".partial"
        self.entry_filename = entry_filename

    def item_dir(self, item_id: str) -> Path:
        return self.items_dir / item_id

    # ── what is on the device ────────────────────────────────────────────────

    def parse(self, data: object) -> E | None:
        """An entry file's item, or None when the file isn't one."""
        raise NotImplementedError

    def complete(self, entry: E) -> bool:
        """Whether an item whose entry reads has everything it needs on the device."""
        return True

    def _scan(self) -> list[tuple[str, E | None, bool]]:
        """Each item directory: its name, the item its entry describes (None when the entry doesn't read), and
        whether the item is whole: the directory's own, and complete."""
        if not self.items_dir.is_dir():
            return []
        found = []
        for directory in sorted(path for path in self.items_dir.iterdir() if path.is_dir() and not path.name.startswith(".")):
            entry = self.parse(read_json(directory / self.entry_filename))
            whole = entry is not None and entry.id == directory.name and self.complete(entry)
            found.append((directory.name, entry, whole))
        return found

    def installed(self) -> list[E]:
        """Every whole item; nothing else counts."""
        return [entry for _, entry, whole in self._scan() if whole and entry is not None]

    def damaged(self) -> list[tuple[str, E | None]]:
        """What is left of the items that aren't whole (an entry that doesn't read or names another item, files
        gone, no entry at all, as an interrupted removal leaves it): each directory's name and what its entry still
        says, for the plugin's pages to offer removing."""
        return [(name, entry) for name, entry, whole in self._scan() if not whole]

    def listed(self) -> set[str]:
        """Every item directory's name, whole or damaged: the ids a removal may take, and nothing outside the
        store."""
        return {name for name, _, _ in self._scan()}

    def size(self, item_id: str) -> int:
        return sum(path.stat().st_size for path in self.item_dir(item_id).rglob("*") if path.is_file())

    def free_bytes(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.root).free

    # ── putting an item in, taking one out ───────────────────────────────────

    def clear_partial(self) -> None:
        """Remove what an interrupted install left behind."""
        shutil.rmtree(self.partial_dir, ignore_errors=True)

    def staging(self, item_id: str) -> Path:
        """An empty directory, on the store's filesystem, to assemble an item in."""
        stage = self.partial_dir / item_id
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        return stage

    def commit_entry(self, stage: Path, item_id: str, entry: dict) -> None:
        """Write the entry inside the staged item, then move it into the store in one rename, over what is left of a
        damaged item of that id: a rename can't land on a directory that isn't empty. Callers never commit over a
        whole item: installing refuses an installed id, and replacing sets the old copy aside first."""
        write_json(stage / self.entry_filename, entry)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.item_dir(item_id), ignore_errors=True)
        stage.replace(self.item_dir(item_id))

    def remove(self, item_id: str) -> None:
        shutil.rmtree(self.item_dir(item_id))

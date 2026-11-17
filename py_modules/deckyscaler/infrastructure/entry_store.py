"""Things the plugin keeps on the device as <root>/<items>/<id>/ with an entry file describing each: assembled in
<root>/.partial first, then moved in by one rename, so an interrupted download or unpack never leaves half an item."""

from __future__ import annotations

import shutil
from pathlib import Path

from deckyscaler.infrastructure.files import read_json, write_json


class EntryStore:
    def __init__(self, root: Path, items_dirname: str, entry_filename: str):
        self.root = root
        self.items_dir = root / items_dirname
        self.partial_dir = root / ".partial"
        self.entry_filename = entry_filename

    def item_dir(self, item_id: str) -> Path:
        return self.items_dir / item_id

    def entries(self) -> list[tuple[str, object]]:
        """Each item's directory name and its entry file's contents; a directory without one isn't an item."""
        if not self.items_dir.is_dir():
            return []
        return [(path.parent.name, read_json(path)) for path in sorted(self.items_dir.glob(f"*/{self.entry_filename}"))]

    def size(self, item_id: str) -> int:
        return sum(path.stat().st_size for path in self.item_dir(item_id).rglob("*") if path.is_file())

    def free_bytes(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(self.root).free

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
        """Write the entry inside the staged item, then move it into the store in one rename."""
        write_json(stage / self.entry_filename, entry)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        stage.replace(self.item_dir(item_id))

    def remove(self, item_id: str) -> None:
        shutil.rmtree(self.item_dir(item_id))

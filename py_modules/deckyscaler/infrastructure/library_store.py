"""The OptiScaler library on disk: ~/deckyscaler/library/{versions,.partial}."""

from __future__ import annotations

import shutil
from pathlib import Path

from deckyscaler.domain import library
from deckyscaler.infrastructure.entry_store import EntryStore
from deckyscaler.infrastructure.files import files_under


class LibraryStore(EntryStore[library.Installed]):
    def __init__(self, root: Path):
        super().__init__(root, "versions", library.ENTRY_FILENAME)

    def parse(self, data: object) -> library.Installed | None:
        return library.parse_entry(data)

    def version_dir(self, version_id: str) -> Path:
        return self.item_dir(version_id)

    def files_of(self, version_id: str) -> frozenset[str]:
        """Every file a version holds now, relative to its files' directory."""
        return files_under(self.version_dir(version_id) / library.FILES_DIRNAME)

    # ── staging an install ───────────────────────────────────────────────────

    def clear_partial(self) -> None:
        """Remove what an interrupted install left behind, and settle an interrupted replace:
        an old copy set aside comes back when no new copy took its place."""
        super().clear_partial()
        if not self.items_dir.is_dir():
            return
        for aside in self.items_dir.glob(".*.old"):
            current = self.version_dir(aside.name[1 : -len(".old")])
            if current.exists():
                shutil.rmtree(aside, ignore_errors=True)
            else:
                aside.replace(current)

    def commit(self, stage: Path, installed: library.Installed) -> None:
        """Write the version's entry inside the staged version, then move it into the library in one rename."""
        self.commit_entry(stage, installed.id, library.entry_json(installed))

    def replace(self, stage: Path, installed: library.Installed) -> None:
        """Commit a fresh copy of a version that is already in the library. The old copy is moved
        aside first and comes back if the new one can't be moved in."""
        current = self.version_dir(installed.id)
        # Beside the versions, not in .partial: clearing .partial must never take the old copy.
        aside = self.items_dir / f".{installed.id}.old"
        shutil.rmtree(aside, ignore_errors=True)
        current.replace(aside)
        try:
            self.commit(stage, installed)
        except OSError:
            aside.replace(current)
            raise
        shutil.rmtree(aside, ignore_errors=True)

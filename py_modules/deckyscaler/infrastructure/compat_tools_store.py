"""A Steam install's compatibilitytools.d on disk: the tools in it, and putting one in or taking one out.

Every decision comes from domain.proton_builds; this only reads and moves files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from deckyscaler.domain import compat_tools, keyvalues
from deckyscaler.domain.proton_builds import Tool

MANIFEST = "compatibilitytool.vdf"
TOOL_MANIFEST = "toolmanifest.vdf"

PARTIAL_DIRNAME = ".deckyscaler-partial"
"""Where an install is assembled, inside compatibilitytools.d so the finished tool moves in with one rename. It
stays once made: Steam needs a restart when compatibilitytools.d itself changes, and making or removing this
directory would change it."""


def _declared(manifest: Path) -> frozenset[str]:
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()
    return frozenset(compat_tools.custom_tools(keyvalues.parse(text)))


def _modified(directory: Path) -> float:
    try:
        return directory.stat().st_mtime
    except OSError:
        return 0.0


def _scan(directory: Path, system: bool) -> list[Tool]:
    if not directory.is_dir():
        return []
    return [
        Tool(manifest.parent.name, _declared(manifest), system, _modified(manifest.parent))
        for manifest in sorted(directory.glob(f"*/{MANIFEST}"))
        if not manifest.parent.name.startswith(".")
    ]


class CompatToolsStore:
    def __init__(self, tools_dir: Path, system_dir: Path | None = None):
        self.tools_dir = tools_dir
        self.system_dir = system_dir
        """Tools installed for every user: listed, never changed."""
        self.partial_dir = tools_dir / PARTIAL_DIRNAME

    def installed(self) -> list[Tool]:
        """Every tool Steam would find, whoever put it there: this install's own, then the system's."""
        return _scan(self.tools_dir, system=False) + (_scan(self.system_dir, system=True) if self.system_dir else [])

    def others(self) -> list[str]:
        """The device's own folders in compatibilitytools.d that aren't tools Steam would find, because they have
        no compatibilitytool.vdf: what a broken install or a folder copied by hand leaves. They are listed so that
        they can be removed. A dot-folder (the plugin's own staging) or a link never counts."""
        if not self.tools_dir.is_dir():
            return []
        return sorted(
            path.name
            for path in self.tools_dir.iterdir()
            if path.is_dir() and not path.is_symlink() and not path.name.startswith(".") and not (path / MANIFEST).exists()
        )

    def _own(self, folder: str) -> Path:
        """A tool's directory in compatibilitytools.d; anything that would point elsewhere is refused."""
        if not folder or folder.startswith(".") or "/" in folder or "\\" in folder:
            raise ValueError(f"Not a tool in {self.tools_dir}: {folder!r}")
        return self.tools_dir / folder

    def size(self, tool: Tool) -> int:
        """What a tool takes on disk; its symlinks count as themselves."""
        root = (self.system_dir if tool.system and self.system_dir else self.tools_dir) / tool.folder
        total = 0
        for directory, _dirs, names in os.walk(root):
            for name in names:
                try:
                    total += os.lstat(os.path.join(directory, name)).st_size
                except OSError:
                    pass
        return total

    def free_bytes(self) -> int:
        """Free space where builds are unpacked and installed."""
        existing = next(path for path in (self.tools_dir, *self.tools_dir.parents) if path.exists())
        return shutil.disk_usage(existing).free

    def changed_at(self) -> float | None:
        """When a tool last came or went: a directory's modification time moves whenever an entry is added,
        removed or renamed in it; None when there is no compatibilitytools.d."""
        try:
            return self.tools_dir.stat().st_mtime
        except OSError:
            return None

    # ── installing ───────────────────────────────────────────────────────────

    def clear_partial(self) -> None:
        """Remove what an interrupted install left, keeping the staging directory itself."""
        if not self.partial_dir.is_dir():
            return
        for leftover in self.partial_dir.iterdir():
            if leftover.is_dir() and not leftover.is_symlink():
                shutil.rmtree(leftover, ignore_errors=True)
            else:
                leftover.unlink(missing_ok=True)

    def staging(self, name: str) -> Path:
        """An empty directory on compatibilitytools.d's filesystem to download and unpack a build in."""
        stage = self.partial_dir / name
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        return stage

    @staticmethod
    def top_entries(directory: Path) -> list[str]:
        return sorted(entry.name for entry in directory.iterdir())

    @staticmethod
    def manifests(tool_dir: Path) -> tuple[bool, bool, frozenset[str]]:
        """Whether an unpacked tool has compatibilitytool.vdf and toolmanifest.vdf, and the names it declares."""
        manifest = tool_dir / MANIFEST
        return manifest.is_file(), (tool_dir / TOOL_MANIFEST).is_file(), _declared(manifest)

    def commit(self, unpacked: Path, folder: str) -> None:
        """Move an unpacked tool into compatibilitytools.d in one rename; a tool already there is never replaced."""
        target = self._own(folder)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"{folder} is already in {self.tools_dir}")
        unpacked.rename(target)

    def remove(self, folder: str) -> None:
        """Delete a tool from compatibilitytools.d; a link, or anything outside it, is refused."""
        path = self._own(folder)
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"{folder} is not a tool directory in {self.tools_dir}")
        shutil.rmtree(path)

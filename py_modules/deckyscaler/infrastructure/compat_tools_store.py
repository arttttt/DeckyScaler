"""A Steam install's compatibilitytools.d on disk: the tools in it, and putting one in or taking one out.

Every decision comes from domain.proton_builds; this only reads and moves files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from deckyscaler.domain import compat_tools, keyvalues
from deckyscaler.domain.proton_builds import Tool
from deckyscaler.infrastructure.staging import Staging

MANIFEST = "compatibilitytool.vdf"
TOOL_MANIFEST = "toolmanifest.vdf"

PARTIAL_DIRNAME = ".deckyscaler-partial"
"""Where an install is assembled, inside compatibilitytools.d so the finished tool moves in with one rename. It
stays once made: Steam needs a restart when compatibilitytools.d itself changes, and making or removing this
directory would change it."""


def _read(manifest: Path) -> keyvalues.KeyValues | None:
    try:
        return keyvalues.parse(manifest.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def _declared(manifest: Path) -> frozenset[str]:
    parsed = _read(manifest)
    return frozenset(compat_tools.custom_tools(parsed)) if parsed is not None else frozenset()


def _missing(folder: Path) -> str | None:
    """What a tool misses to start a game: for each tool its compatibilitytool.vdf declares, the toolmanifest.vdf in
    its install path, which says what Steam runs (an archive without one isn't installed either), then that file. None
    when every tool has both, or a toolmanifest names nothing to run (nothing proves the tool broken)."""
    manifest = _read(folder / MANIFEST)
    for install_path in (compat_tools.custom_tools(manifest).values() if manifest is not None else ()):
        tool_dir = folder / install_path
        tool_manifest = _read(tool_dir / TOOL_MANIFEST)
        if tool_manifest is None:
            return TOOL_MANIFEST
        target = compat_tools.launch_target(tool_manifest)
        if target is not None and not (tool_dir / target).exists():
            return target
    return None


def _modified(directory: Path) -> float:
    try:
        return directory.stat().st_mtime
    except OSError:
        return 0.0


def _folders(directory: Path) -> list[Path]:
    """The folders in a compatibilitytools.d, by name, linked ones too (a build kept elsewhere, as on an SD card, is
    linked in: it is listed, never removed); none named with a dot (the plugin's own staging), and none when the
    directory can't be read."""
    try:
        return sorted(path for path in directory.iterdir() if path.is_dir() and not path.name.startswith("."))
    except OSError:
        return []


def _plain_files(directory: Path) -> list[Path]:
    """The plain files in a compatibilitytools.d (an archive, a note), none a link or named with a dot; a .vdf
    there may register a tool kept elsewhere, so it is never one."""
    try:
        return sorted(
            path for path in directory.iterdir()
            if path.is_file() and not path.is_symlink() and not path.name.startswith(".") and path.suffix.lower() != ".vdf"
        )
    except OSError:
        return []


def _tool(folder: Path, system: bool) -> Tool | None:
    """The tool a folder is, as Steam finds one: a compatibilitytool.vdf that declares a tool. Anything else, a
    missing, unreadable or empty manifest included, is no tool Steam would list."""
    names = _declared(folder / MANIFEST)
    return Tool(folder.name, names, system, _modified(folder), folder.is_symlink(), _missing(folder)) if names else None


def _scan(directory: Path, system: bool) -> list[Tool]:
    return [tool for folder in _folders(directory) if (tool := _tool(folder, system)) is not None]


class CompatToolsStore(Staging):
    def __init__(self, tools_dir: Path, system_dir: Path | None = None):
        self.tools_dir = tools_dir
        self.system_dir = system_dir
        """Tools installed for every user: listed, never changed."""
        self.partial_dir = tools_dir / PARTIAL_DIRNAME
        self.lock_dir = self.partial_dir
        """The staging directory stays once made: compatibilitytools.d doesn't change for an install's lock."""

    def installed(self) -> list[Tool]:
        """Every tool Steam would find, whoever put it there: this install's own, then the system's."""
        return _scan(self.tools_dir, system=False) + (_scan(self.system_dir, system=True) if self.system_dir else [])

    def others(self) -> list[Tool]:
        """The device's own folders in compatibilitytools.d that aren't tools Steam would find (`_tool`), and its plain
        files: what a broken install, a folder copied by hand or a downloaded archive leaves. They are listed so that
        they can be removed, as tools that declare no names. A link never counts: it isn't removed here."""
        folders = [
            Tool(folder.name, frozenset(), modified=_modified(folder))
            for folder in _folders(self.tools_dir)
            if not folder.is_symlink() and _tool(folder, system=False) is None
        ]
        return folders + [Tool(path.name, frozenset(), modified=_modified(path)) for path in _plain_files(self.tools_dir)]

    def _own(self, folder: str) -> Path:
        """A tool's directory in compatibilitytools.d; anything that would point elsewhere is refused."""
        if not folder or folder.startswith(".") or "/" in folder or "\\" in folder:
            raise ValueError(f"Not a tool in {self.tools_dir}: {folder!r}")
        return self.tools_dir / folder

    def size(self, tool: Tool) -> int:
        """What a tool takes on disk; its symlinks count as themselves."""
        root = (self.system_dir if tool.system and self.system_dir else self.tools_dir) / tool.folder
        if root.is_file() and not root.is_symlink():
            return root.stat().st_size
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

    def taken(self, folder: str) -> bool:
        """Whether something already holds a tool's name in compatibilitytools.d, a folder, a link or a file: a tool
        moved in can't land there."""
        target = self._own(folder)
        return target.exists() or target.is_symlink()

    def commit(self, unpacked: Path, folder: str) -> None:
        """Move an unpacked tool into compatibilitytools.d in one rename; whatever holds its name is never replaced."""
        if self.taken(folder):
            raise FileExistsError(f"{folder} is already in {self.tools_dir}")
        unpacked.rename(self._own(folder))

    def remove(self, folder: str) -> None:
        """Delete a tool, or a plain file, from compatibilitytools.d; a link, or anything outside it, is refused."""
        path = self._own(folder)
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError(f"{folder} is not a tool directory in {self.tools_dir}")
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)

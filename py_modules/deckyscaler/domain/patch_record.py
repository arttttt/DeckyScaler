"""What a patch did to a game directory, recorded in its marker before the first file lands.

Unpatching undoes exactly that record: it removes the files the patch placed, restores the
backups it made and removes the directories it created. It touches nothing else, so it works
for any OptiScaler layout and for versions no longer in the library. A file the game has
replaced since (an update) is the game's: it stays, and the backup it superseded is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from . import bundle
from .patch_plan import (
    BACKUP_SUFFIX,
    INI_FILENAME,
    Copy,
    DeleteFile,
    Link,
    Move,
    Operation,
    RemoveTree,
)

LINK_PREFIX = "link:"
"""What identifies a placed symlink in place of a sha256: `link:` and the path it points to. A link is
ours while it points where we pointed it, whether or not its target still exists."""

FORMAT = 2
"""Markers without this format come from plugin versions before the record existed."""


@dataclass(frozen=True)
class Placed:
    path: str
    sha256: str | None
    """The content placed (a link's is its target, see LINK_PREFIX); None for a file a program rewrites
    (OptiScaler's ini, a library's settings), which is ours whatever it holds."""


@dataclass(frozen=True)
class Backup:
    original: str
    backup: str


@dataclass(frozen=True)
class PatchRecord:
    placed: tuple[Placed, ...]
    backups: tuple[Backup, ...]
    created_dirs: tuple[str, ...]
    owned_dirs: tuple[str, ...] = ()
    """Directories the patch created whose every file is the patch's, whoever wrote it (a library provider's
    folder, its logs too): unpatching removes them whole."""


@dataclass(frozen=True)
class RemoveDirIfEmpty:
    name: str


def record(
    operations: tuple[Operation, ...],
    entries: frozenset[str],
    bundle_hashes: dict[str, str],
    carried_over: frozenset[str] = frozenset(),
    rewritten: frozenset[str] = frozenset(),
    owned_dirs: tuple[str, ...] = (),
) -> PatchRecord:
    """The record of a patch plan, made before it runs.

    `entries` is the game directory before the patch; `bundle_hashes` maps every bundle file the
    plan copies to its sha256. `carried_over` names files a
    previous patch placed that this one keeps as they are (the user's OptiScaler.ini settings).
    `rewritten` names placed files a program rewrites besides OptiScaler.ini, and `owned_dirs` directories
    whose every file is the patch's: only those the patch creates are recorded as its own.
    """
    placed: dict[str, Placed] = {path: Placed(path, None) for path in sorted(carried_over)}
    backups: list[Backup] = []
    for operation in operations:
        match operation:
            case Move(source, destination) if destination == source + BACKUP_SUFFIX:
                backups.append(Backup(source, destination))
            case Copy(source, destination) | Link(source, destination):
                sha = None if destination == INI_FILENAME or destination in rewritten else bundle_hashes[source]
                placed[destination] = Placed(destination, sha)
    # A backup beside a file the patch places, the file itself gone, was set aside by a patch whose record was lost:
    # it is the original this patch restores.
    backups += [
        Backup(path, f"{path}{BACKUP_SUFFIX}") for path in placed if path not in entries and f"{path}{BACKUP_SUFFIX}" in entries
    ]
    created = sorted(
        {
            str(parent)
            for item in placed
            for parent in PurePosixPath(item).parents
            if str(parent) != "." and str(parent).split("/")[0] not in entries
        },
        key=lambda path: (-path.count("/"), path),
    )
    owned = tuple(directory for directory in owned_dirs if directory in created)
    return PatchRecord(tuple(placed.values()), tuple(backups), tuple(created), owned)


def made_by_the_plugin(links: dict[str, str], plugin_home: str) -> tuple[str, ...]:
    """The links in a game (`links` maps a link's path to its target) pointing into the plugin's home: only a patch of
    the plugin's makes one, a backup's name included."""
    return tuple(sorted(path for path, target in links.items() if PurePosixPath(target).is_relative_to(plugin_home)))


def left_behind(links: tuple[str, ...], dirs: tuple[str, ...] = ()) -> tuple[Operation | RemoveDirIfEmpty, ...]:
    """What a patch whose record is gone left in a game, to clear before patching it again: its links
    (`made_by_the_plugin`), the folders only the plugin's libraries fill (`dirs`, whole), then the directories that
    held them, deepest first, should nothing else be in them."""
    holding = {str(parent) for path in (*links, *dirs) for parent in PurePosixPath(path).parents if str(parent) != "."}
    return (
        *(DeleteFile(path) for path in links),
        *(RemoveTree(path) for path in dirs),
        *(RemoveDirIfEmpty(path) for path in sorted(holding, key=lambda path: (-path.count("/"), path))),
    )


def to_json(patch: PatchRecord, complete: bool) -> dict:
    return {
        "format": FORMAT,
        "complete": complete,
        "placed": [{"path": p.path, "sha256": p.sha256} for p in patch.placed],
        "backups": [{"original": b.original, "backup": b.backup} for b in patch.backups],
        "created_dirs": list(patch.created_dirs),
        "owned_dirs": list(patch.owned_dirs),
    }


def parse(marker: dict) -> PatchRecord | None:
    """The record in a marker; None for one with no record that reads: the original Decky Framegen's, or damaged."""
    if marker.get("format") != FORMAT:
        return None
    try:
        return PatchRecord(
            tuple(Placed(str(p["path"]), None if p["sha256"] is None else str(p["sha256"])) for p in marker["placed"]),
            tuple(Backup(str(b["original"]), str(b["backup"])) for b in marker["backups"]),
            tuple(str(d) for d in marker["created_dirs"]),
            # Records from before libraries own no directory whole.
            tuple(str(d) for d in marker.get("owned_dirs", [])),
        )
    except (KeyError, TypeError):
        return None


OK = "ok"
INCOMPLETE = "incomplete"
UPSTREAM = "upstream"
DAMAGED = "damaged"


def state(marker: dict) -> str:
    """What the plugin's marker says of its patch: OK; INCOMPLETE when the patch stopped before its last file (its
    record still undoes what landed); DAMAGED when it holds no record that reads (a write cut short, an edit by
    hand): the patch is the plugin's, but how to undo it is lost, and patching again makes a new one."""
    if parse(marker) is None:
        return DAMAGED
    return OK if marker.get("complete", True) else INCOMPLETE


def state_of(name: str, marker: dict) -> str:
    """What a game's marker says: a record that reads goes by itself, whatever the file is called (a few early builds
    wrote theirs under the original's name, FRAMEGEN_PATCH, and it undoes their patch exactly); with none, the
    original Decky Framegen's marker is UPSTREAM, undone by a reset, and the plugin's own is DAMAGED."""
    if parse(marker) is None and name == bundle.UPSTREAM_MARKER_FILENAME:
        return UPSTREAM
    return state(marker)


def placed_by(patch: PatchRecord | None, path: str) -> bool:
    """Whether a recorded patch placed `path` (a file the directory had before is someone else's)."""
    return patch is not None and any(item.path == path for item in patch.placed)


def intact(patch: PatchRecord, current: dict[str, str | None]) -> bool:
    """Whether everything the patch placed is still there as it placed it (OptiScaler.ini, which
    OptiScaler rewrites, only has to be there)."""
    return all(
        item.path in current and (item.sha256 is None or current[item.path] == item.sha256) for item in patch.placed
    )


FILE = "file"
"""What a placed path is now when it is a file of its own, told without reading it (game_directory.placed_kinds)."""


def changed(patch: PatchRecord, now: dict[str, str | None]) -> tuple[str, ...]:
    """The files a patch placed that aren't as it placed them, told without reading any (`now` maps each placed path
    to a link's identity while its target is there, FILE for a file, None when it is gone): gone, a link leading
    nowhere, a link replaced by a file (a game update put its own there), or a link pointing elsewhere. A copy, or a
    file a program rewrites, only has to be there."""
    return tuple(
        item.path
        for item in patch.placed
        if now.get(item.path) is None
        or (item.sha256 is not None and item.sha256.startswith(LINK_PREFIX) and now[item.path] != item.sha256)
    )


def covers(patch: PatchRecord, paths: frozenset[str]) -> bool:
    """Whether the patch placed every one of `paths`: a version's files that came back after it was patched while
    some were gone (`version_placement.linked_files`) are not in the game until it is patched again."""
    return paths <= {item.path for item in patch.placed}


def plan_unpatch(
    patch: PatchRecord, current: dict[str, str | None], keep: frozenset[str] = frozenset(), marker: str = bundle.MARKER_FILENAME
) -> tuple[Operation | RemoveDirIfEmpty, ...]:
    """Undo a recorded patch. `current` maps every placed path and backup still present to its sha256 now.
    Directories the patch owns go whole, with what their programs wrote into them since.

    A placed file someone replaced since stays when nothing was backed up for it. When something was,
    the backup comes back over it: Unpatch returns the directory to how it was before the patch, and
    a file put over a patched one after patching is its owner's to keep track of.
    `keep` names placed files to leave where they are, for a repatch that carries them over. `marker` is the file
    the record is in, taken last.
    """
    operations: list[Operation | RemoveDirIfEmpty] = []
    backed_up = {backup.original for backup in patch.backups if backup.backup in current}
    for item in patch.placed:
        if item.path not in current or item.path in keep:
            continue
        replaced = item.sha256 is not None and current[item.path] != item.sha256
        if replaced and item.path not in backed_up:
            continue
        operations.append(DeleteFile(item.path))
    for backup in patch.backups:
        if backup.backup in current:
            operations.append(Move(backup.backup, backup.original))
    operations += [RemoveTree(path) for path in patch.owned_dirs]
    operations += [RemoveDirIfEmpty(path) for path in patch.created_dirs]
    operations.append(DeleteFile(marker))
    return tuple(operations)

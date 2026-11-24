"""Small filesystem helpers shared by the services."""

from __future__ import annotations

import fcntl
import filecmp
import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_match(file_a: Path, file_b: Path) -> bool:
    """True when both files exist and have identical content."""
    try:
        return file_a.exists() and file_b.exists() and filecmp.cmp(file_a, file_b, shallow=False)
    except OSError:
        return False


def files_under(directory: Path) -> frozenset[str]:
    """Every file under `directory`, as paths relative to it with '/'."""
    return frozenset(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())


def copy_files(source: Path, paths: tuple[str, ...], destination: Path) -> None:
    """Copy files, by their paths relative to `source`, to the same paths under `destination`."""
    for path in paths:
        (destination / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / path, destination / path)


def read_json(path: Path) -> dict:
    """The JSON object stored at `path`, or {} when it is missing, unreadable or not an object."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def staged(path: Path) -> Path:
    """Where replace_json writes a file before moving it over the old one; a stop in between leaves it there."""
    return path.with_name(path.name + ".new")


def replace_json(path: Path, payload: dict) -> None:
    """Write a JSON file the plugin keeps (settings, indexes, a game's patch marker) in one step: written beside it,
    then moved over it, so an interrupted write leaves the old content rather than half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(staged(path), payload)
    staged(path).replace(path)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold a file kept beside what it guards, for one read-modify-write at a time between threads and processes (the
    plugin and the launch wrapper): each holder opens it on its own, and a holder that dies lets it go. A file
    replaced by a rename can't hold its own lock, the rename leaving the lock on the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read_text(path: Path) -> str:
    """A text file as it is, its line endings kept."""
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def read_text_or_empty(path: Path) -> str:
    """A text file as it is, or "" when it isn't there or can't be read: for what the system may or may not say (sysfs,
    Steam's config)."""
    try:
        return read_text(path)
    except OSError:
        return ""


def rewrite_text(path: Path, transform: Callable[[str], str]) -> bool:
    """Apply `transform` to a text file's content; write it back only if it changed.

    Returns whether the file changed.
    """
    # newline="": the text keeps its own line endings both ways (OptiScaler.ini ships with CRLF).
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        content = f.read()
    updated = transform(content)
    if updated == content:
        return False
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(updated)
    return True

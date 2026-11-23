"""Removable drives: SD cards and USB drives, which SteamOS has udisks mount under /run/media (/run/media/deck/<label>,
and for a card also a link at the older /run/media/<label> or /run/media/mmcblk0p1). Taking a drive out removes its
mount point, so what was on it isn't there, just as if it had been deleted. Two cards with one label are mounted at the
same place, one at a time: a drive's identity, its filesystem's UUID, tells them apart.

What is mounted where is read from the kernel's own list, never guessed from the directories: a btrfs subvolume is
a directory of its own device, though nothing is mounted there."""

from __future__ import annotations

import re
from pathlib import Path

from deckyscaler.infrastructure.files import read_text

REMOVABLE_MEDIA = (Path("/run/media"), Path("/media"))
"""Where udisks mounts the drives it is asked to."""
MOUNTS = Path("/proc/self/mountinfo")
"""What is mounted where, from which device: the kernel's list."""
BY_UUID = Path("/dev/disk/by-uuid")
"""udev's name for every device holding a filesystem, by that filesystem's UUID (whatever the filesystem: ext4, btrfs,
exFAT and FAT's serial, NTFS's)."""


def _unescaped(field: str) -> str:
    """A mountinfo field as it is: a space and other such bytes are written there as octal escapes."""
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), field)


def mounts(mountinfo: str) -> dict[Path, str | None]:
    """Every mount point a /proc/self/mountinfo text lists, with the device it is mounted from (None when it names
    none): the fifth field is the mount point, the second after the lone "-" the source. Of mounts stacked on one
    point the last listed is the one seen there."""
    found: dict[Path, str | None] = {}
    for line in mountinfo.splitlines():
        fields = line.split(" ")
        if len(fields) < 5 or "-" not in fields:
            continue
        source = fields.index("-") + 2
        found[Path(_unescaped(fields[4]))] = _unescaped(fields[source]) if source < len(fields) else None
    return found


def _drive(path: Path) -> tuple[bool, Path | None, str | None]:
    """Whether a path is under one of REMOVABLE_MEDIA; the drive's mount point between that base and it (None when
    none is mounted there), the innermost one; and the device it is mounted from. The path is followed through links
    first (a card's older path is one); the link an unmount leaves behind leads nowhere mounted."""
    resolved = path.resolve()
    for base in (media.resolve() for media in REMOVABLE_MEDIA):
        if resolved != base and resolved.is_relative_to(base):
            listed = mounts(read_text(MOUNTS)) if MOUNTS.is_file() else {}
            holding = [point for point in listed if point != base and point.is_relative_to(base) and resolved.is_relative_to(point)]
            mount = max(holding, key=lambda point: len(point.parts), default=None)
            return True, mount, None if mount is None else listed[mount]
    return False, None, None


def _identity(source: str | None) -> str | None:
    """The UUID of the filesystem on a device: the name udev gives it."""
    if source is None or not BY_UUID.is_dir():
        return None
    device = Path(source).resolve()
    return next((link.name for link in BY_UUID.iterdir() if link.resolve() == device), None)


def identity(path: Path) -> str | None:
    """The identity of the removable drive a path is on, kept with what the plugin patched there; None for a path that
    isn't on one, whose drive isn't mounted, or whose filesystem has no UUID."""
    _, _, source = _drive(path)
    return _identity(source)


def on_unmounted_drive(path: Path, drive: str | None = None) -> bool:
    """Whether a path is on a removable drive that isn't mounted now: none is where the path is, or another one is
    (`drive`, the identity kept when the path was patched there, isn't the mounted one's)."""
    removable, mount, source = _drive(path)
    if not removable:
        return False
    return mount is None or (drive is not None and _identity(source) != drive)

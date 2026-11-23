"""Removable drives: SD cards and USB drives, which SteamOS has udisks mount under /run/media (/run/media/deck/<label>,
and for a card also a link at the older /run/media/<label> or /run/media/mmcblk0p1). Taking a drive out removes its
mount point, so what was on it isn't there, just as if it had been deleted. Two cards with one label are mounted at the
same place, one at a time: a drive's identity, its filesystem's UUID, tells them apart."""

from __future__ import annotations

import re
from os.path import ismount
from pathlib import Path

from deckyscaler.infrastructure.files import read_text

REMOVABLE_MEDIA = (Path("/run/media"), Path("/media"))
"""Where udisks mounts the drives it is asked to."""
MOUNTS = Path("/proc/self/mountinfo")
"""What is mounted where, from which device: the kernel's list."""
BY_UUID = Path("/dev/disk/by-uuid")
"""udev's name for every device holding a filesystem, by that filesystem's UUID (whatever the filesystem: ext4, btrfs,
exFAT and FAT's serial, NTFS's)."""


def _drive(path: Path) -> tuple[bool, Path | None]:
    """Whether a path is under one of REMOVABLE_MEDIA, and the mount point between that base and it (None when none
    is). The path is followed through links first (a card's older path is one); the link an unmount leaves behind
    leads nowhere mounted."""
    resolved = path.resolve()
    for base in (media.resolve() for media in REMOVABLE_MEDIA):
        if resolved != base and resolved.is_relative_to(base):
            steps = (step for step in (resolved, *resolved.parents) if step != base and step.is_relative_to(base))
            return True, next((step for step in steps if ismount(step)), None)
    return False, None


def mounted_from(mountinfo: str, mount: Path) -> str | None:
    """The device a mount point is mounted from, as a /proc/self/mountinfo text lists it: the fifth field is the mount
    point (a space and other such bytes written as octal escapes), the second after the lone "-" the source."""
    for line in mountinfo.splitlines():
        fields = line.split(" ")
        if len(fields) > 4 and re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4]) == str(mount) and "-" in fields:
            source = fields.index("-") + 2
            return fields[source] if source < len(fields) else None
    return None


def _identity(mount: Path) -> str | None:
    """The UUID of the filesystem mounted at a mount point: the name udev gives the device it is mounted from."""
    source = mounted_from(read_text(MOUNTS), mount) if MOUNTS.is_file() else None
    if source is None or not BY_UUID.is_dir():
        return None
    device = Path(source).resolve()
    return next((link.name for link in BY_UUID.iterdir() if link.resolve() == device), None)


def identity(path: Path) -> str | None:
    """The identity of the removable drive a path is on, kept with what the plugin patched there; None for a path that
    isn't on one, whose drive isn't mounted, or whose filesystem has no UUID."""
    _, mount = _drive(path)
    return None if mount is None else _identity(mount)


def on_unmounted_drive(path: Path, drive: str | None = None) -> bool:
    """Whether a path is on a removable drive that isn't mounted now: none is where the path is, or another one is
    (`drive`, the identity kept when the path was patched there, isn't the mounted one's)."""
    removable, mount = _drive(path)
    if not removable:
        return False
    return mount is None or (drive is not None and _identity(mount) != drive)

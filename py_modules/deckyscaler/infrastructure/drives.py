"""Removable drives: SD cards and USB drives, which SteamOS has udisks mount under /run/media (/run/media/deck/<label>,
and for a card also a link at the older /run/media/<label> or /run/media/mmcblk0p1). Taking a drive out removes its
mount point, so what was on it isn't there, just as if it had been deleted."""

from __future__ import annotations

from os.path import ismount
from pathlib import Path

REMOVABLE_MEDIA = (Path("/run/media"), Path("/media"))
"""Where udisks mounts the drives it is asked to."""


def on_unmounted_drive(path: Path) -> bool:
    """Whether a path is on a removable drive that isn't mounted now: under one of REMOVABLE_MEDIA, with no mount point
    between that base and it. The path is followed through links first (a card's older path is one); the link an
    unmount leaves behind leads nowhere mounted."""
    resolved = path.resolve()
    for base in (media.resolve() for media in REMOVABLE_MEDIA):
        if resolved != base and resolved.is_relative_to(base):
            return not any(ismount(step) for step in (resolved, *resolved.parents) if step != base and step.is_relative_to(base))
    return False

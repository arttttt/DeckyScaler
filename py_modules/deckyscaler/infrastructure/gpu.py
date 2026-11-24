"""Which GPU games render on, read from sysfs."""

from __future__ import annotations

from pathlib import Path

from deckyscaler.domain import fsr4
from deckyscaler.infrastructure import files

SYSFS = Path("/sys")


def amd_gpu() -> bool:
    """Whether the GPU games render on is AMD's: the boot VGA device when the machine says which, else any GPU."""
    cards = [
        card / "device"
        for card in sorted(SYSFS.glob("class/drm/card*"))
        if card.name[4:].isdigit() and (card / "device" / "vendor").is_file()  # not connectors like card1-DP-1
    ]
    boot = [card for card in cards if files.read_text_or_empty(card / "boot_vga").strip() == "1"]
    return any(fsr4.is_amd(files.read_text_or_empty(card / "vendor")) for card in boot or cards)

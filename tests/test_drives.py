"""Telling a directory on a drive that isn't mounted from one that is gone (integration, against a fake /run/media)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from deckyscaler.infrastructure import drives


@dataclass
class Media:
    """A fake /run/media; its mount points are the directories in `mounted`."""

    base: Path
    mounted: set[Path] = field(default_factory=set)

    def mount(self, name: str) -> Path:
        point = self.base / "deck" / name
        point.mkdir(exist_ok=True)
        self.mounted.add(point.resolve())
        return point

    def take_out(self, point: Path) -> None:
        self.mounted.discard(point.resolve())
        point.rmdir()


@pytest.fixture
def media(tmp_path, monkeypatch) -> Media:
    fake = Media(tmp_path / "run" / "media")
    (fake.base / "deck").mkdir(parents=True)
    monkeypatch.setattr(drives, "REMOVABLE_MEDIA", (fake.base,))
    monkeypatch.setattr(drives, "ismount", lambda path: Path(path) in fake.mounted)
    return fake


def test_a_directory_gone_from_a_mounted_drive_is_gone(media):
    card = media.mount("SD")

    assert not drives.on_unmounted_drive(card / "steamapps" / "common" / "Game" / "bin")


def test_a_directory_on_a_drive_taken_out_is_on_an_unmounted_drive(media):
    game = media.base / "deck" / "SD" / "steamapps" / "common" / "Game"

    assert drives.on_unmounted_drive(game)  # the mount point went with the drive
    (media.base / "deck" / "SD").mkdir()
    assert drives.on_unmounted_drive(game)  # a mount point left behind isn't the drive


def test_a_cards_older_path_is_followed_to_the_drive(media):
    card = media.mount("SD")
    (media.base / "mmcblk0p1").symlink_to(card)
    game = media.base / "mmcblk0p1" / "steamapps" / "common" / "Game"

    assert not drives.on_unmounted_drive(game)
    media.take_out(card)
    assert drives.on_unmounted_drive(game)  # the link leads nowhere mounted


def test_the_media_base_mounted_itself_isnt_a_drive(media):
    media.mounted.add(media.base.resolve())

    assert drives.on_unmounted_drive(media.base / "deck" / "SD" / "Game")


def test_a_directory_outside_removable_media_is_never_on_an_unmounted_drive(media, tmp_path):
    assert not drives.on_unmounted_drive(tmp_path / "home" / "deck" / "Games" / "Game")
    assert not drives.on_unmounted_drive(media.base)


def test_a_directory_that_is_the_drive_itself_is_on_a_mounted_drive(media):
    usb = media.mount("USB")  # a game unpacked at the top of a USB drive

    assert not drives.on_unmounted_drive(usb)


def test_a_media_base_that_is_a_link_is_the_place_it_leads_to(media, tmp_path, monkeypatch):
    link = tmp_path / "media"
    link.symlink_to(media.base)  # as /media is a link to /run/media on some systems
    monkeypatch.setattr(drives, "REMOVABLE_MEDIA", (link,))

    assert drives.on_unmounted_drive(media.base / "deck" / "SD" / "Game")

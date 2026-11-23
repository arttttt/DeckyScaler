"""Telling a directory on a drive that isn't mounted from one that is gone, and one drive from another mounted in its
place (integration, against a fake /run/media, mount list and udev)."""

from __future__ import annotations

from pathlib import Path

from deckyscaler.infrastructure import drives


def test_a_directory_gone_from_a_mounted_drive_is_gone(media):
    card = media.put_in("SD", "a1b2c3d4-0000-4000-8000-000000000001")

    assert not drives.on_unmounted_drive(card / "steamapps" / "common" / "Game" / "bin")


def test_a_directory_on_a_drive_taken_out_is_on_an_unmounted_drive(media):
    game = media.base / "deck" / "SD" / "steamapps" / "common" / "Game"

    assert drives.on_unmounted_drive(game)  # the mount point went with the drive
    (media.base / "deck" / "SD").mkdir()
    assert drives.on_unmounted_drive(game)  # a mount point left behind isn't the drive


def test_a_cards_older_path_is_followed_to_the_drive(media):
    card = media.put_in("SD", "a1b2c3d4-0000-4000-8000-000000000001")
    (media.base / "mmcblk0p1").symlink_to(card)
    game = media.base / "mmcblk0p1" / "steamapps" / "common" / "Game"

    assert not drives.on_unmounted_drive(game)
    media.take_out(card)
    assert drives.on_unmounted_drive(game)  # the link leads nowhere mounted


def test_the_media_base_mounted_itself_isnt_a_drive(media):
    media.mount_at(media.base, "sda1")

    assert drives.on_unmounted_drive(media.base / "deck" / "SD" / "Game")


def test_a_game_in_a_btrfs_subvolume_is_on_its_cards_drive(media):
    card = media.put_in("SD", "5d6e7f80-0000-4000-8000-000000000003", filesystem="btrfs")
    game = card / "@games" / "Hades"  # a subvolume: a device of its own to stat, though nothing is mounted there
    game.mkdir(parents=True)

    assert drives.identity(game) == "5d6e7f80-0000-4000-8000-000000000003"
    assert not drives.on_unmounted_drive(game, "5d6e7f80-0000-4000-8000-000000000003")


def test_the_innermost_mount_holding_a_path_is_its_drive(media):
    usb = media.put_in("USB", "0F1E-2D3C", device="sda1", filesystem="exfat")
    media.mount_at(usb / "inner", "sdb1")
    (media.by_uuid / "9A8B-7C6D").symlink_to(media.devices / "sdb1")
    (media.devices / "sdb1").touch()

    assert drives.identity(usb / "inner" / "Hades") == "9A8B-7C6D"
    assert drives.identity(usb / "Hades") == "0F1E-2D3C"


def test_a_directory_outside_removable_media_is_never_on_an_unmounted_drive(media, tmp_path):
    assert not drives.on_unmounted_drive(tmp_path / "home" / "deck" / "Games" / "Game")
    assert not drives.on_unmounted_drive(media.base)


def test_a_directory_that_is_the_drive_itself_is_on_a_mounted_drive(media):
    usb = media.put_in("USB", "0F1E-2D3C", device="sda1", filesystem="exfat")  # a game unpacked at the top of a USB drive

    assert not drives.on_unmounted_drive(usb)


def test_a_media_base_that_is_a_link_is_the_place_it_leads_to(media, tmp_path, monkeypatch):
    link = tmp_path / "media"
    link.symlink_to(media.base)  # as /media is a link to /run/media on some systems
    monkeypatch.setattr(drives, "REMOVABLE_MEDIA", (link,))

    assert drives.on_unmounted_drive(media.base / "deck" / "SD" / "Game")


def test_a_drive_is_known_by_its_filesystems_uuid_whatever_the_filesystem(media, tmp_path):
    card = media.put_in("SD", "a1b2c3d4-0000-4000-8000-000000000001")
    usb = media.put_in("My Games", "0F1E-2D3C", device="sda1", filesystem="exfat")  # a label with a space
    ntfs = media.put_in("Windows", "6A5B4C3D2E1F0A9B", device="sdb1", filesystem="fuseblk")

    assert drives.identity(card / "Games" / "Hades") == "a1b2c3d4-0000-4000-8000-000000000001"
    assert drives.identity(usb / "Hades") == "0F1E-2D3C"
    assert drives.identity(ntfs / "Hades") == "6A5B4C3D2E1F0A9B"
    assert drives.identity(tmp_path / "home" / "Games" / "Hades") is None  # not on a removable drive
    media.take_out(card)
    assert drives.identity(card / "Games" / "Hades") is None  # not mounted


def test_another_card_with_the_same_label_isnt_the_one_a_game_was_patched_on(media):
    card = media.put_in("SD", "a1b2c3d4-0000-4000-8000-000000000001")
    game = card / "Games" / "Hades"
    patched_on = drives.identity(game)
    media.take_out(card)

    media.put_in("SD", "ffffffff-0000-4000-8000-000000000002")  # mounted where the first one was

    assert drives.on_unmounted_drive(game, patched_on)
    assert not drives.on_unmounted_drive(game, "ffffffff-0000-4000-8000-000000000002")
    assert not drives.on_unmounted_drive(game)  # indexed before drives were kept: the path alone decides
    media.take_out(card)
    media.put_in("SD", "a1b2c3d4-0000-4000-8000-000000000001")
    assert not drives.on_unmounted_drive(game, patched_on)


def test_what_is_mounted_where_is_read_from_the_kernels_list():
    mountinfo = (
        "22 1 0:21 / / rw - ext4 /dev/nvme0n1p8 rw\n"
        "41 22 179:1 / /run/media/deck/SD rw,nosuid shared:30 master:1 - ext4 /dev/mmcblk0p1 rw\n"
        "42 22 8:1 / /run/media/deck/My\\040Games rw - exfat /dev/sda1 rw,uid=1000\n"
        "43 22 0:50 /@games /run/media/deck/Sub rw - btrfs /dev/sdb1 rw,subvol=/@games\n"
        "44 22 0:51 / /run/media/deck/odd rw -\n"
        "broken line\n"
        "45 22 - cut\n"
        "46 41 179:2 / /run/media/deck/SD rw - ext4 /dev/mmcblk0p2 rw\n"  # stacked on the first: the one seen there
        "47 22 7:0 / /run/media/deck/Image rw - squashfs /home/deck/My\\040Image.sqfs ro\n"
    )

    assert drives.mounts(mountinfo) == {
        Path("/"): "/dev/nvme0n1p8",
        Path("/run/media/deck/SD"): "/dev/mmcblk0p2",
        Path("/run/media/deck/My Games"): "/dev/sda1",
        Path("/run/media/deck/Sub"): "/dev/sdb1",
        Path("/run/media/deck/odd"): None,  # no source listed
        Path("/run/media/deck/Image"): "/home/deck/My Image.sqfs",
    }
    assert drives.mounts("") == {}

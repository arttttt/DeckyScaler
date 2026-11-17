"""Steam library metadata: pure parsing (unit) and discovery on a real filesystem (integration)."""

import os
from pathlib import Path

import pytest

from conftest import put_tools_on_path, write
from deckyscaler.domain import steam
from deckyscaler.infrastructure import steam as steam_library

LIBRARY_FOLDERS = '''"libraryfolders"
{
\t"0"
\t{
\t\t"path"\t\t"/home/deck/.local/share/Steam"
\t\t"apps"\t\t{ }
\t}
\t"1"
\t{
\t\t"path"\t\t"/run/media/mmcblk0p1"
\t}
}
'''


def manifest(appid: str, name: str, installdir: str) -> str:
    return f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"installdir"\t\t"{installdir}"\n}}\n'


# ── unit: parsing and rules ──────────────────────────────────────────────────


def test_parse_library_folders_lists_every_path():
    assert steam.parse_library_folders(LIBRARY_FOLDERS) == ["/home/deck/.local/share/Steam", "/run/media/mmcblk0p1"]


def test_parse_library_folders_unescapes_windows_style_separators():
    assert steam.parse_library_folders('\t"path"\t\t"D:\\\\Games\\\\Steam"\n') == ["D:/Games/Steam"]


def test_parse_app_manifest_reads_appid_name_and_installdir():
    assert steam.parse_app_manifest(manifest("1091500", "Cyberpunk 2077", "Cyberpunk 2077")) == steam.AppManifest(
        "1091500", "Cyberpunk 2077", "Cyberpunk 2077"
    )


def test_parse_app_manifest_leaves_missing_fields_empty():
    assert steam.parse_app_manifest('"AppState"\n{\n\t"appid"\t\t"5"\n}\n') == steam.AppManifest("5", "", "")


def test_is_game_rejects_incomplete_manifests_and_steam_tools():
    assert steam.is_game(steam.AppManifest("1", "Hades", "Hades"))
    assert not steam.is_game(steam.AppManifest("", "Hades", "Hades"))
    assert not steam.is_game(steam.AppManifest("1", "", "Hades"))
    assert not steam.is_game(steam.AppManifest("1493710", "Proton Experimental", "Proton - Experimental"))
    assert not steam.is_game(steam.AppManifest("1628350", "Steam Linux Runtime 3.0 (sniper)", "SteamLinuxRuntime_sniper"))


def test_steam_root_candidates_cover_native_and_flatpak_installs():
    roots = [p.as_posix() for p in steam.steam_root_candidates(Path("/home/deck"))]

    assert "/home/deck/.local/share/Steam" in roots
    assert "/home/deck/.var/app/com.valvesoftware.Steam/data/Steam" in roots  # Flatpak's own, flathub's wrapper
    assert "/home/deck/.var/app/com.valvesoftware.Steam/home/.local/share/Steam" in roots


@pytest.mark.parametrize(
    ("command_line", "root"),
    [
        ("/home/deck/.local/share/Steam/ubuntu12_32/steam -steamdeck -steamos3 -gamepadui", "/home/deck/.local/share/Steam"),
        ("/home/deck/.local/share/Steam/ubuntu12_64/steam", "/home/deck/.local/share/Steam"),
        ("/home/deck/.var/app/com.valvesoftware.Steam/data/Steam/ubuntu12_32/steam -no-cef-sandbox",
         "/home/deck/.var/app/com.valvesoftware.Steam/data/Steam"),
        ("/home/deck/.local/share/Steam/ubuntu12_64/steamwebhelper -lang=en_US", None),
        ("/home/deck/.local/share/Steam/ubuntu12_32/reaper SteamLaunch AppId=730 -- "
         "/home/deck/.local/share/Steam/ubuntu12_32/steam-launch-wrapper -- game.exe", None),
        ("bash /home/deck/.local/share/Steam/steam.sh -steamdeck", None),
        ("/usr/bin/steam", None),
        ("", None),
    ],
)
def test_the_steam_client_is_known_by_the_install_it_runs_from(command_line, root):
    found = steam.client_root(command_line)

    assert (found.as_posix() if found else None) == root


NATIVE, FLATPAK = Path("/home/deck/.local/share/Steam"), Path("/home/deck/.var/app/com.valvesoftware.Steam/data/Steam")


@pytest.mark.parametrize(
    ("configured", "running", "expected"),
    [
        ([NATIVE, FLATPAK], [FLATPAK], steam.ActiveRoot(FLATPAK)),  # the running one wins
        ([NATIVE], [], steam.ActiveRoot(NATIVE)),  # else the only one that ever ran
        ([NATIVE], [Path("/opt/elsewhere")], steam.ActiveRoot(NATIVE)),  # a client from no install found here
        ([NATIVE, FLATPAK], [], steam.ActiveRoot(None, steam.SEVERAL_STEAMS)),
        ([], [], steam.ActiveRoot(None, steam.NO_STEAM)),
        ([], [NATIVE], steam.ActiveRoot(None, steam.NO_STEAM)),  # running but never written a config yet
    ],
)
def test_the_install_to_work_with_is_the_running_one_else_the_only_one_that_ran(configured, running, expected):
    assert steam.active_root(configured, running) == expected


# ── integration: discovery on disk ───────────────────────────────────────────


def test_installed_games_spans_native_flatpak_and_extra_libraries(tmp_path):
    home = tmp_path / "home"
    native = home / ".local/share/Steam"
    flatpak = home / ".var/app/com.valvesoftware.Steam/home/.local/share/Steam"
    sd_card = tmp_path / "sdcard"
    write(native / "steamapps/libraryfolders.vdf", f'\t"path"\t\t"{sd_card}"\n'.encode())
    write(native / "steamapps/appmanifest_10.acf", manifest("10", "beta", "Beta").encode())
    write(flatpak / "steamapps/appmanifest_20.acf", manifest("20", "Alpha", "Alpha").encode())
    write(sd_card / "steamapps/appmanifest_30.acf", manifest("30", "Gamma", "Gamma").encode())
    write(sd_card / "steamapps/appmanifest_40.acf", manifest("40", "Proton 9.0", "Proton 9.0").encode())

    games = steam_library.installed_games(home)

    assert [(g.appid, g.name) for g in games] == [("20", "Alpha"), ("10", "beta"), ("30", "Gamma")]
    assert games[2].install_path == sd_card / "steamapps/common/Gamma"
    assert games[2].library_path == sd_card


def test_find_game_and_duplicate_appids_resolve_to_the_last_library(tmp_path):
    home = tmp_path / "home"
    native = home / ".local/share/Steam"
    sd_card = tmp_path / "sdcard"
    write(native / "steamapps/libraryfolders.vdf", f'\t"path"\t\t"{sd_card}"\n'.encode())
    write(native / "steamapps/appmanifest_10.acf", manifest("10", "Moved Game", "Old").encode())
    write(sd_card / "steamapps/appmanifest_10.acf", manifest("10", "Moved Game", "New").encode())

    game = steam_library.find_game(home, "10")

    assert game is not None
    assert game.install_path == sd_card / "steamapps/common/New"
    assert steam_library.find_game(home, "999") is None


def test_executables_finds_exe_files_recursively(tmp_path):
    root = tmp_path / "Game"
    write(root / "Game.exe", b"")
    write(root / "Binaries/Win64/Game-Win64-Shipping.exe", b"")
    write(root / "readme.txt", b"")
    (root / "folder.exe").mkdir()

    found = sorted(p.relative_to(root).as_posix() for p in steam_library.executables(root))

    assert found == ["Binaries/Win64/Game-Win64-Shipping.exe", "Game.exe"]
    assert steam_library.executables(tmp_path / "missing") == []


def test_one_install_seen_through_links_is_one_steam(tmp_path):
    home = tmp_path / "home"
    native = home / ".local/share/Steam"
    native.mkdir(parents=True)
    (home / ".steam").mkdir()
    os.symlink(native, home / ".steam" / "steam")
    os.symlink(native, home / ".steam" / "root")
    flatpak = home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
    flatpak.mkdir(parents=True)
    os.symlink(flatpak.parent, home / ".var/app/com.valvesoftware.Steam/data")  # what flathub's wrapper leaves

    assert steam_library.steam_roots(home) == [native.resolve(), flatpak.resolve()]


def ps_printing(lines: list[str]) -> dict[str, str]:
    body = "".join(f"echo '{line}'\n" for line in lines)
    return {"ps": f"#!/bin/sh\n{body}"}


def configured(root: Path) -> Path:
    write(root / "config" / "config.vdf", b'"InstallConfigStore" { }')
    return root.resolve()


def test_the_running_steam_is_the_one_to_work_with(tmp_path, monkeypatch):
    home = tmp_path / "home"
    native = configured(home / ".local/share/Steam")
    flatpak = configured(home / ".var/app/com.valvesoftware.Steam/data/Steam")

    put_tools_on_path(monkeypatch, tmp_path / "bin", ps_printing(["/sbin/init", f"{flatpak}/ubuntu12_32/steam -no-cef-sandbox"]))
    assert steam_library.active_root(home) == steam.ActiveRoot(flatpak)

    put_tools_on_path(monkeypatch, tmp_path / "bin", ps_printing(["/sbin/init"]))
    assert steam_library.active_root(home) == steam.ActiveRoot(None, steam.SEVERAL_STEAMS)

    (flatpak / "config" / "config.vdf").unlink()
    assert steam_library.active_root(home) == steam.ActiveRoot(native)


def test_apps_are_named_from_every_librarys_manifests_and_every_users_shortcuts(tmp_path):
    from test_binary_keyvalues import encode

    home = tmp_path / "home"
    native = home / ".local/share/Steam"
    sd_card = tmp_path / "sdcard"
    write(native / "steamapps/libraryfolders.vdf", f'\t"path"\t\t"{sd_card}"\n'.encode())
    write(native / "steamapps/appmanifest_10.acf", manifest("10", "Beta", "Beta").encode())
    write(sd_card / "steamapps/appmanifest_1493710.acf", manifest("1493710", "Proton Experimental", "Proton").encode())
    write(native / "userdata/1/config/shortcuts.vdf", encode({"shortcuts": {"0": {"appid": -5, "AppName": "Mine"}}}))
    write(native / "userdata/2/config/shortcuts.vdf", encode({"shortcuts": {"0": {"appid": 99, "AppName": "Theirs"}}}))
    write(native / "userdata/3/config/shortcuts.vdf", b"\x05broken")

    assert steam_library.app_names(home) == {"10": "Beta", "1493710": "Proton Experimental"}
    assert steam_library.shortcut_names(native.resolve()) == {str(2**32 - 5): "Mine", "99": "Theirs"}

"""The user's libraries end to end: downloaded from a fake GitHub, added from what the user picks, chosen, applied to
patched games and removed (integration, through the plugin's RPCs where they exist)."""

from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile

import pytest

from conftest import NIGHTLY, FakeDownload, make_game_dir, run, write
from deckyscaler.application import patcher as patcher_module
from deckyscaler.application.user_libraries import UserLibraries
from deckyscaler.domain import release_assets
from deckyscaler.domain import user_libraries as ul

FG, UP = ul.FRAME_GENERATION, ul.UPSCALER
ANR = "Apex Neural Rendering FG"


def zip_of(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


ADDON = zip_of({f"{ANR}/dlssg/nvngx_dlssg.dll": b"anr", f"{ANR}/dlssg/nr_fg.ini": b"[nr]", "install.sh": b"#!/bin/sh"})


def listing(content: bytes = ADDON, state: str = "uploaded") -> list[dict]:
    name = "anr-fg-V.B19-addon.zip"
    return [{
        "tag_name": "FG-V.B19", "published_at": "2026-11-17T00:20:54Z", "prerelease": False, "draft": False,
        "assets": [{
            "name": name, "state": state, "size": len(content),
            "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
            "browser_download_url": f"https://github.com/apex-compute/ANR/releases/download/FG-V.B19/{name}",
        }],
    }]


def owner(home, content: bytes = ADDON, published: list[dict] | None = None, reports: list | None = None) -> UserLibraries:
    return UserLibraries(
        home, lambda repository: published if published is not None else listing(), FakeDownload(content),
        lambda *args: reports.append(args) if reports is not None else None,
    )


def pe_with_version(high: int, low: int) -> bytes:
    """A DLL whose resources record a file version."""
    dos = bytearray(0x40)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 0, 0)
    resources = b"\0" * 8 + struct.pack("<IIII", 0xFEEF04BD, 0x00010000, high, low)
    section = b".rsrc\0\0\0" + struct.pack("<IIII", len(resources), 0x1000, len(resources), 0x40 + len(coff) + 40) + bytes(16)
    return bytes(dos) + coff + section + resources


# ── downloading ──────────────────────────────────────────────────────────────


def test_a_download_keeps_the_provider_alone_and_lists_it(home, plugin_home):
    reports = []
    libraries = owner(home, reports=reports)

    result = libraries.install(ul.ANR, "anr-v-b19")

    assert result == {"status": "success", "id": "anr-v-b19", "in_menu": True, "message": "Apex Neural Rendering FG V.B19 is downloaded."}
    files = libraries.store.files_dir("anr-v-b19")
    assert sorted(p.relative_to(files).as_posix() for p in files.rglob("*") if p.is_file()) == [
        f"{ANR}/dlssg/nr_fg.ini", f"{ANR}/dlssg/nvngx_dlssg.dll",
    ]
    assert reports[-1] == ("anr-v-b19", len(ADDON), len(ADDON))
    listed = libraries.installed()
    assert [(item["id"], item["slots"], item["games"]) for item in listed["libraries"]] == [("anr-v-b19", [FG], [])]
    assert listed["slots"] == [UP, FG]
    rows = libraries.versions(ul.ANR)["versions"]
    assert (rows[0]["id"], rows[0]["state"]) == ("anr-v-b19", release_assets.INSTALLED)


def test_a_download_that_doesnt_match_its_checksum_adds_nothing(home, plugin_home):
    libraries = owner(home, content=b"tampered", published=listing())

    result = libraries.install(ul.ANR, "anr-v-b19")

    assert result["status"] == "error" and "checksum" in result["message"]
    assert libraries.store.installed() == [] and not libraries.store.partial_dir.exists()


@pytest.mark.parametrize(
    ("published", "release_id", "message"),
    [
        (listing(state="starter"), "anr-v-b19", "can't be downloaded now"),
        (listing(), "anr-v-b01", "no longer published"),
    ],
)
def test_a_release_that_cant_be_downloaded_says_why(home, plugin_home, published, release_id, message):
    assert message in owner(home, published=published).install(ul.ANR, release_id)["message"]


# ── adding the user's own ────────────────────────────────────────────────────


def test_a_zip_a_folder_or_a_dll_the_user_picked_is_added_once(home, plugin_home, tmp_path):
    libraries = owner(home)
    sdk = write(tmp_path / "XeSS_SDK_3.0.2.zip", zip_of({"bin/libxess.dll": b"x", "bin/libxess_fg.dll": b"f", "doc/a.pdf": b"d"}))
    folder = tmp_path / "Uniscaler"
    write(folder / "Uniscaler" / "ffx" / "u.dll", b"u")
    dll = write(tmp_path / "Downloads" / "libxess.dll", pe_with_version((2 << 16) | 0, (2 << 16) | 68))

    assert libraries.add(str(sdk))["id"] == "xess-sdk-3-0-2"
    assert libraries.add(str(folder))["id"] == "uniscaler"
    assert libraries.add(str(dll)) == {
        "status": "success", "id": "libxess-dll-2-0-2-68", "in_menu": False, "message": "libxess.dll 2.0.2.68 is added.",
    }
    assert libraries.add(str(sdk)) == {"status": "error", "reason": ul.ALREADY_ADDED}
    assert sorted(p.name for p in libraries.store.files_dir("xess-sdk-3-0-2").rglob("*") if p.is_file()) == ["libxess.dll", "libxess_fg.dll"]


def test_what_isnt_a_library_is_refused_with_why(home, plugin_home, tmp_path):
    libraries = owner(home)
    junk = write(tmp_path / "junk.zip", zip_of({"README.txt": b"hi"}))

    assert libraries.add(str(junk)) == {"status": "error", "reason": ul.NOTHING_KNOWN}
    assert libraries.add(str(tmp_path / "gone.zip"))["status"] == "error"
    assert libraries.store.installed() == []


# ── choosing, applying, removing ─────────────────────────────────────────────


def test_a_slot_takes_only_a_library_that_serves_it(plugin, home, plugin_home):
    owner(home).install(ul.ANR, "anr-v-b19")

    assert run(plugin.user_library_choose("global", FG, "anr-v-b19")) == {"status": "success", "to_apply": []}
    assert run(plugin.user_library_choose("global", UP, "anr-v-b19"))["status"] == "error"
    assert run(plugin.user_library_choose("not-a-game", FG, None))["status"] == "error"
    assert run(plugin.user_library_choose("620", FG, "none")) == {"status": "success", "to_apply": []}
    assert run(plugin.user_library_game_choice("620")) == {
        "status": "success", "own": {FG: "none"}, "resolved": {}, "left_out": [], "missing": [], "pending": False,
    }
    assert run(plugin.user_library_game_choice("570"))["resolved"] == {FG: "anr-v-b19"}
    assert run(plugin.user_libraries_installed())["global"] == {FG: "anr-v-b19"}
    assert run(plugin.user_libraries_installed())["left_out"] == []


def test_a_pick_whose_provider_an_earlier_slots_library_names_is_said_to_be_left_out(plugin, home, plugin_home, tmp_path):
    libraries = owner(home)
    write(tmp_path / "bundle" / "X" / "ffx" / "a.dll", b"a")
    write(tmp_path / "bundle" / "Y" / "dlssg" / "b.dll", b"b")
    write(tmp_path / "other" / "X" / "dlssg" / "c.dll", b"c")
    assert libraries.add(str(tmp_path / "bundle"))["id"] == "bundle"
    assert libraries.add(str(tmp_path / "other"))["id"] == "x"
    run(plugin.user_library_choose("global", UP, "bundle"))
    run(plugin.user_library_choose("global", FG, "x"))

    assert run(plugin.user_libraries_installed())["left_out"] == [FG]
    assert run(plugin.user_library_game_choice("620"))["left_out"] == [FG]
    assert run(plugin.user_library_choose("620", UP, "none"))["status"] == "success"
    assert run(plugin.user_library_game_choice("620"))["left_out"] == []


def test_a_new_choice_is_applied_to_patched_games_and_a_running_one_is_left_alone(plugin, home, plugin_home, tmp_path, monkeypatch):
    owner(home).install(ul.ANR, "anr-v-b19")
    game = make_game_dir(tmp_path / "games" / "Game")
    running = make_game_dir(tmp_path / "games" / "Running")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    run(plugin.manual_patch_directory(str(running), "dxgi.dll", NIGHTLY))
    chosen = run(plugin.user_library_choose("global", FG, "anr-v-b19"))
    assert sorted(chosen["to_apply"]) == sorted([str(game), str(running)])  # what the change reaches, said at once
    assert sorted(run(plugin.user_libraries_installed())["to_apply"]) == sorted([str(game), str(running)])
    monkeypatch.setattr(patcher_module.processes, "command_lines", lambda: [f"wine {running / 'Game.exe'}"])

    result = run(plugin.user_libraries_apply())

    assert result["applied"] == [{"name": str(game), "appid": "", "launch_options": None}]
    assert result["skipped"] == [str(running)] and result["failed"] == []
    assert json.loads((game / "DECKYSCALER_PATCH").read_text())["libraries"][0]["id"] == "anr-v-b19"
    assert run(plugin.user_libraries_installed())["to_apply"] == [str(running)]


def test_a_library_downloaded_after_a_patch_reaches_the_patched_games_unpicked(plugin, home, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))

    owner(home).install(ul.ANR, "anr-v-b19")

    assert run(plugin.user_libraries_installed())["to_apply"] == [str(game)]
    assert run(plugin.user_libraries_apply())["applied"][0]["name"] == str(game)
    assert json.loads((game / "DECKYSCALER_PATCH").read_text())["libraries"] == [
        {"slot": None, "id": "anr-v-b19", "label": "Apex Neural Rendering FG V.B19"},
    ]
    listed = run(plugin.user_libraries_installed())
    assert listed["to_apply"] == [] and listed["libraries"][0]["games"] == [str(game)]


def test_removing_a_library_says_who_has_it_and_they_keep_their_copy(plugin, home, plugin_home, tmp_path):
    owner(home).install(ul.ANR, "anr-v-b19")
    run(plugin.user_library_choose("global", FG, "anr-v-b19"))
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))

    assert run(plugin.user_library_removal("anr-v-b19")) == {"status": "success", "games": [str(game)], "global": True}
    assert run(plugin.user_library_remove("anr-v-b19")) == {"status": "success"}

    listed = run(plugin.user_libraries_installed())
    assert listed["libraries"] == [] and listed["global"] == {}
    assert (game / "OptiScaler" / "custom" / ANR / "dlssg" / "nvngx_dlssg.dll").exists()
    assert listed["to_apply"] == [str(game)]  # patching it again would leave the library out
    assert run(plugin.user_library_remove("anr-v-b19"))["status"] == "error"


def test_whats_left_of_a_damaged_library_is_listed_with_what_it_takes_and_can_be_removed(plugin, home, plugin_home):
    libraries = owner(home)
    libraries.install(ul.ANR, "anr-v-b19")
    run(plugin.user_library_choose("global", FG, "anr-v-b19"))
    (libraries.store.files_dir("anr-v-b19") / ANR / "dlssg" / "nvngx_dlssg.dll").unlink()
    size = libraries.store.size("anr-v-b19")

    listed = run(plugin.user_libraries_installed())
    assert listed["libraries"] == []
    assert listed["damaged"] == [{"id": "anr-v-b19", "label": "Apex Neural Rendering FG V.B19", "size": size}]
    assert listed["installed_bytes"] == size > 0
    assert listed["missing"] == [FG] and listed["left_out"] == []  # still picked, yet nothing goes in for it
    assert run(plugin.user_library_game_choice("620"))["missing"] == [FG]
    assert run(plugin.user_library_removal("anr-v-b19")) == {"status": "success", "games": [], "global": True}
    assert run(plugin.user_library_remove("anr-v-b19")) == {"status": "success"}

    listed = run(plugin.user_libraries_installed())
    assert listed["damaged"] == [] and listed["global"] == {} and listed["installed_bytes"] == 0
    assert listed["missing"] == [] and run(plugin.user_library_game_choice("620"))["missing"] == []
    assert not libraries.store.item_dir("anr-v-b19").exists()


def test_only_what_the_store_lists_can_be_removed(plugin, home, plugin_home):
    libraries = owner(home)
    libraries.install(ul.ANR, "anr-v-b19")

    for outside in ("..", ".", "../entries", "nothing"):
        assert run(plugin.user_library_removal(outside))["status"] == "error"
        assert run(plugin.user_library_remove(outside))["status"] == "error"
    assert [item["id"] for item in run(plugin.user_libraries_installed())["libraries"]] == ["anr-v-b19"]


def test_what_would_take_more_than_a_library_may_is_refused(home, plugin_home, tmp_path, monkeypatch):
    monkeypatch.setattr(ul, "MAX_BYTES", 3)
    libraries = owner(home)
    dll = write(tmp_path / "libxess.dll", b"1234")
    sdk = write(tmp_path / "sdk.zip", zip_of({"bin/libxess.dll": b"1234"}))

    assert "more than" in libraries.add(str(dll))["message"]
    assert "more than" in libraries.add(str(sdk))["message"]
    assert libraries.store.installed() == []


def test_a_patched_game_says_when_its_choice_needs_patching_again(plugin, home, plugin_home, steam_library, tmp_path):
    owner(home).install(ul.ANR, "anr-v-b19")
    steam_library.add_game("1234", "Test Game")
    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))
    other = make_game_dir(tmp_path / "games" / "Other")
    run(plugin.manual_patch_directory(str(other), "dxgi.dll", NIGHTLY))
    run(plugin.user_library_choose("global", FG, "anr-v-b19"))  # both games now lack what they'd get

    chosen = run(plugin.user_library_choose("1234", FG, "anr-v-b19"))

    assert chosen["to_apply"] == ["Test Game"]  # a game's own change reaches that game alone
    assert run(plugin.user_library_game_choice("1234"))["pending"] is True
    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))
    assert run(plugin.user_library_game_choice("1234"))["pending"] is False

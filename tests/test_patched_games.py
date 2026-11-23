"""Every game the plugin patched, for the Games page (unit + integration)."""

from __future__ import annotations

import json

from conftest import NIGHTLY, NIGHTLY_FILES, NIGHTLY_INI, STABLE, install_version, make_game_dir, run
from deckyscaler.domain import patch_record
from deckyscaler.infrastructure import game_directory


def test_a_marker_says_whether_its_patch_is_whole_unfinished_or_an_older_plugins():
    whole = patch_record.to_json(patch_record.PatchRecord((), (), ()), complete=True)
    unfinished = patch_record.to_json(patch_record.PatchRecord((), (), ()), complete=False)

    assert patch_record.state(whole) == patch_record.OK
    assert patch_record.state(unfinished) == patch_record.INCOMPLETE
    assert patch_record.state({"dll_name": "dxgi.dll"}) == patch_record.DAMAGED  # the plugin's, with no record
    assert patch_record.state({}) == patch_record.DAMAGED  # half a file reads as nothing
    assert patch_record.state_of("DECKYSCALER_PATCH", {"dll_name": "dxgi.dll"}) == patch_record.DAMAGED
    assert patch_record.state_of("DECKYSCALER_PATCH", whole) == patch_record.OK
    # Without a record, the original Decky Framegen's marker is its patch; a record there is one an early build wrote.
    assert patch_record.state_of("FRAMEGEN_PATCH", {"dll_name": "dxgi.dll"}) == patch_record.UPSTREAM
    assert patch_record.state_of("FRAMEGEN_PATCH", whole) == patch_record.OK
    assert patch_record.state_of("FRAMEGEN_PATCH", unfinished) == patch_record.INCOMPLETE


def test_steam_games_and_directories_patched_are_listed_by_name(plugin, plugin_home, steam_library, tmp_path):
    steam_library.add_game("1", "Zeta")
    manual = make_game_dir(tmp_path / "games" / "alpha")
    run(plugin.patch_game("1", "winmm.dll", "", STABLE))
    run(plugin.manual_patch_directory(str(manual), "dxgi.dll", NIGHTLY))
    run(plugin.set_setting("1", "Menu", "UseHQFont", "true"))

    games = run(plugin.patched_games())["games"]

    assert [g["name"] for g in games] == [str(manual), "Zeta"]
    directory, steam = games
    assert {k: directory[k] for k in ("appid", "dll_name", "dll_present", "version_id", "record", "own_settings")} == {
        "appid": "", "dll_name": "dxgi.dll", "dll_present": True, "version_id": NIGHTLY, "record": "ok", "own_settings": False,
    }
    assert (steam["appid"], steam["dll_name"], steam["version_id"], steam["own_settings"]) == ("1", "winmm.dll", STABLE, True)
    assert steam["patched_at"]


def test_a_newer_build_of_the_games_channel_is_named(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    install_version(plugin_home, "nightly-20261024", "10", NIGHTLY_FILES, NIGHTLY_INI)

    assert run(plugin.patched_games())["games"][0]["newer_version"] == "nightly-20261024"


def test_a_game_patched_while_its_version_lacked_a_file_says_so_once_the_file_is_back(plugin, plugin_home, steam_library, tmp_path):
    kept = plugin_home / "library" / "versions" / STABLE / "files" / "libxess.dll"
    aside = tmp_path / "libxess.dll"
    steam_library.add_game("1234", "Test Game")
    directory = make_game_dir(tmp_path / "games" / "By Path")
    kept.replace(aside)  # the version lost a file it doesn't need to patch
    run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))
    run(plugin.manual_patch_directory(str(directory), "dxgi.dll", STABLE))
    lacking = lambda: {game["name"]: game["lacks_version_files"] for game in run(plugin.patched_games())["games"]}
    assert lacking() == {str(directory): False, "Test Game": False}  # nothing the version holds is missing

    aside.replace(kept)  # Download again brought it back
    assert lacking() == {str(directory): True, "Test Game": True}
    assert run(plugin.get_game_status("1234"))["lacks_version_files"] is True

    run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))
    assert run(plugin.get_game_status("1234"))["lacks_version_files"] is False
    assert lacking() == {str(directory): True, "Test Game": False}

    marker = directory / "DECKYSCALER_PATCH"
    marker.write_text(json.dumps({key: value for key, value in json.loads(marker.read_text()).items() if key != "format"}))
    assert lacking() == {str(directory): False, "Test Game": False}  # a marker without a record: nothing to compare


def test_a_game_whose_version_lost_a_file_says_its_version_is_incomplete(plugin, plugin_home, steam_library, tmp_path):
    version = plugin_home / "library" / "versions" / STABLE
    entry = json.loads((version / "entry.json").read_text())
    entry["files"] = sorted(p.relative_to(version / "files").as_posix() for p in (version / "files").rglob("*") if p.is_file())
    (version / "entry.json").write_text(json.dumps(entry))  # a version downloaded since the list is kept
    steam_library.add_game("1234", "Test Game")
    run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))
    assert run(plugin.get_game_status("1234"))["version_incomplete"] is False

    (version / "files" / "libxess.dll").unlink()

    assert run(plugin.get_game_status("1234"))["version_incomplete"] is True
    assert run(plugin.patched_games())["games"][0]["version_incomplete"] is True


def test_a_listing_reads_each_versions_files_once_and_a_status_once(plugin, plugin_home, steam_library, tmp_path, monkeypatch):
    from deckyscaler.infrastructure.library_store import LibraryStore

    steam_library.add_game("1234", "Test Game")
    run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))
    run(plugin.manual_patch_directory(str(make_game_dir(tmp_path / "games" / "By Path")), "dxgi.dll", STABLE))
    run(plugin.manual_patch_directory(str(make_game_dir(tmp_path / "games" / "Other")), "dxgi.dll", NIGHTLY))
    read, real = [], LibraryStore.files_of
    monkeypatch.setattr(LibraryStore, "files_of", lambda self, version_id: read.append(version_id) or real(self, version_id))

    run(plugin.patched_games())
    assert sorted(read) == [NIGHTLY, STABLE]
    read.clear()
    run(plugin.get_game_status("1234"))
    assert read == [STABLE]


def test_a_missing_proxy_and_an_unfinished_patch_are_told(plugin, plugin_home, tmp_path, monkeypatch):
    broken = make_game_dir(tmp_path / "games" / "Broken")
    run(plugin.manual_patch_directory(str(broken), "dxgi.dll", STABLE))
    (broken / "dxgi.dll").unlink()
    unfinished = make_game_dir(tmp_path / "games" / "Unfinished")
    monkeypatch.setattr(game_directory, "execute", lambda operations, directory, source: (_ for _ in ()).throw(OSError("asleep")))
    run(plugin.manual_patch_directory(str(unfinished), "dxgi.dll", STABLE))

    games = {g["directory"]: g for g in run(plugin.patched_games())["games"]}

    assert games[str(broken)]["dll_present"] is False
    assert games[str(unfinished)]["record"] == "incomplete"


def test_a_directory_whose_marker_is_gone_leaves_the_list_and_the_index(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    (game / "DECKYSCALER_PATCH").unlink()

    assert run(plugin.patched_games())["games"] == []
    assert json.loads((plugin_home / "patched.json").read_text()) == {}


def test_games_are_ordered_by_name_whatever_its_case(plugin, plugin_home, steam_library):
    steam_library.add_game("1", "Beta")
    steam_library.add_game("2", "alpha")
    run(plugin.patch_game("1", "dxgi.dll", "", STABLE))
    run(plugin.patch_game("2", "dxgi.dll", "", STABLE))

    assert [g["name"] for g in run(plugin.patched_games())["games"]] == ["alpha", "Beta"]

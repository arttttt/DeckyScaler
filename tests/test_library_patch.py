"""The user's libraries in a patch: placed as the game's choice says, selected in its ini, kept by the launch
wrapper, undone whole (integration)."""

from __future__ import annotations

import json

from conftest import NIGHTLY, STABLE, make_game_dir, run, snapshot, write
from deckyscaler.application.launch_wrapper import LaunchWrapper
from deckyscaler.domain import library_choice
from deckyscaler.domain import user_libraries as ul
from deckyscaler.infrastructure.settings_store import SettingsStore
from deckyscaler.infrastructure.user_library_store import LibraryChoicesStore, UserLibraryStore

FG, UP = ul.FRAME_GENERATION, ul.UPSCALER
ANR = "Apex Neural Rendering FG"
ANR_FILES = {f"{ANR}/dlssg/nvngx_dlssg.dll": b"anr dll", f"{ANR}/dlssg/nr_fg.ini": b"[nr]\nbuild=1\n"}


def add_library(plugin_home, library_id: str, files: dict[str, bytes], settings=()) -> ul.Library:
    """A library in ~/deckyscaler/libraries as the libraries' owner leaves it."""
    store = UserLibraryStore(plugin_home / "libraries")
    contents = ul.recognize(frozenset(files))
    library = ul.Library(library_id, library_id.upper(), "1", ul.YOUR_FILE, None, contents.providers, contents.dlls, contents.files, settings, "t")
    stage = store.staging(library_id)
    for path, data in files.items():
        write(stage / ul.FILES_DIRNAME / path, data)
    store.commit(stage, library)
    return library


def choose(plugin_home, scope: str, slot: str, value: str | None) -> None:
    store = LibraryChoicesStore(plugin_home / "settings" / "libraries.json")
    store.write(library_choice.with_choice(store.read(), scope, slot, value))


def anr(plugin_home) -> ul.Library:
    return add_library(plugin_home, "anr", ANR_FILES, ((("FrameGen", "DisableHudless"), "false"),))


def ini_of(game) -> str:
    return (game / "OptiScaler.ini").read_text()


def marker_of(game) -> dict:
    return json.loads((game / "DECKYSCALER_PATCH").read_text())


def wrapper_patch(home, game) -> None:
    """What the launch wrapper does before a game starts."""
    LaunchWrapper(home, {}).patch([str(game / "Game.exe")], "dxgi.dll")


def test_a_frame_generation_provider_is_copied_in_selected_and_undone_whole_with_its_logs(plugin, plugin_home, tmp_path):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))["status"] == "success"

    folder = game / "OptiScaler" / "custom" / ANR / "dlssg"
    assert (folder / "nvngx_dlssg.dll").read_bytes() == b"anr dll"
    assert not (folder / "nvngx_dlssg.dll").is_symlink()  # a copy: the game keeps it when the library goes
    assert {"FGInput=nvngxfg", f"FGNvngxReplacement={ANR}", "DisableHudless=false"} <= set(ini_of(game).splitlines())
    assert marker_of(game)["libraries"] == [{"slot": FG, "id": "anr", "label": "ANR 1"}]
    write(folder / "nr_fg-20261117.log", b"what ANR logged")

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before


def test_dlls_picked_as_the_upscaler_go_beside_optiscaler_and_select_it(plugin, plugin_home, tmp_path):
    add_library(plugin_home, "xess", {"bin/libxess.dll": b"my xess"})
    choose(plugin_home, library_choice.GLOBAL, UP, "xess")
    game = make_game_dir(tmp_path / "games" / "Game")

    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))

    assert (game / "OptiScaler" / "user-libraries" / "libxess.dll").read_bytes() == b"my xess"
    assert (game / "OptiScaler" / "libxess.dll").is_symlink()  # OptiScaler's own copy stays as the version has it
    lines = set(ini_of(game).splitlines())
    assert {"XeSSPath=OptiScaler\\user-libraries\\libxess.dll", "Dx12Upscaler=xess", "Dx11Upscaler=xess_12"} <= lines


def test_optiscaler_0_9_gets_no_library(plugin, plugin_home, tmp_path):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    game = make_game_dir(tmp_path / "games" / "Game")

    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))

    assert not (game / "custom").exists() and marker_of(game)["libraries"] == []


def test_a_games_own_choice_wins_and_none_means_none(plugin, plugin_home, steam_library):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    choose(plugin_home, "1234", FG, library_choice.NONE)
    root = steam_library.add_game("1234", "Test Game")

    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))

    assert marker_of(root)["libraries"] == []
    assert run(plugin.get_game_status("1234"))["libraries"] == []


def test_a_games_status_and_the_patched_games_say_what_libraries_it_has(plugin, plugin_home, steam_library):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    steam_library.add_game("1234", "Test Game")

    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))

    has = [{"slot": FG, "id": "anr", "label": "ANR 1"}]
    assert run(plugin.get_game_status("1234"))["libraries"] == has
    assert run(plugin.patched_games())["games"][0]["libraries"] == has


def test_the_wrapper_keeps_what_the_game_has_until_the_library_leaves_the_device(plugin, plugin_home, home, tmp_path):
    SettingsStore(plugin_home / "settings").save_global({("FrameGen", "FGInput"): "fsrfg"})
    library = anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    patched_at = marker_of(game)["patched_at"]
    choose(plugin_home, library_choice.GLOBAL, FG, None)

    wrapper_patch(home, game)  # a new choice is the user's to apply: the game starts as it was

    assert marker_of(game)["patched_at"] == patched_at
    assert "FGInput=nvngxfg" in ini_of(game)
    UserLibraryStore(plugin_home / "libraries").remove(library.id)

    wrapper_patch(home, game)  # the library left the device: the game is patched without it

    assert marker_of(game)["libraries"] == []
    assert not (game / "OptiScaler" / "custom").exists()
    lines = set(ini_of(game).splitlines())
    assert "FGInput=fsrfg" in lines  # the user's value again
    assert {f"FGNvngxReplacement=auto", "DisableHudless=auto"} <= lines  # nobody's: back to OptiScaler's own


def test_what_a_provider_rewrites_doesnt_break_the_patch_but_a_file_gone_does(plugin, plugin_home, home, tmp_path):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    patched_at = marker_of(game)["patched_at"]
    folder = game / "OptiScaler" / "custom" / ANR / "dlssg"
    (folder / "nr_fg.ini").write_text("[nr]\nbuild=2\n")

    wrapper_patch(home, game)

    assert marker_of(game)["patched_at"] == patched_at
    (folder / "nvngx_dlssg.dll").unlink()

    wrapper_patch(home, game)

    assert marker_of(game)["patched_at"] != patched_at
    assert (folder / "nvngx_dlssg.dll").read_bytes() == b"anr dll"


def test_a_settings_change_keeps_what_the_games_libraries_set(plugin, plugin_home, steam_library):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    root = steam_library.add_game("1234", "Test Game")
    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))

    run(plugin.set_setting("global", "FSR", "Fsr4Model", "1"))

    lines = set(ini_of(root).splitlines())
    assert {"Fsr4Model=1", "FGInput=nvngxfg"} <= lines


def _row(page: dict, section: str, key: str) -> dict:
    return next(s for sec in page["sections"] if sec["name"] == section for s in sec["settings"] if s["key"] == key)


def test_the_global_page_shows_what_the_global_choice_sets_and_wont_change_it(plugin, plugin_home):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")

    row = _row(run(plugin.global_settings()), "FrameGen", "FGInput")
    refused = run(plugin.set_setting("global", "FrameGen", "FGInput", "fsrfg"))

    assert (row["value"], row["source"], row["library"]) == ("nvngxfg", "library", "ANR 1")
    assert refused == {"status": "error", "message": "FrameGen.FGInput is set by ANR 1. Pick another library to change it."}
    assert run(plugin.set_setting("global", "FSR", "Fsr4Model", "1"))["status"] == "success"


def test_a_games_page_shows_what_its_libraries_set_and_wont_change_it(plugin, plugin_home, steam_library):
    anr(plugin_home)
    choose(plugin_home, library_choice.GLOBAL, FG, "anr")
    steam_library.add_game("1234", "Test Game")
    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))
    choose(plugin_home, library_choice.GLOBAL, FG, None)  # the game has ANR until it is patched again

    row = _row(run(plugin.game_settings("1234")), "FrameGen", "FGInput")
    refused = run(plugin.set_setting("1234", "FrameGen", "FGInput", "fsrfg"))

    assert (row["source"], row["library"]) == ("library", "ANR 1")
    assert refused["status"] == "error" and "set by ANR 1" in refused["message"]
    assert run(plugin.set_setting("global", "FrameGen", "FGInput", "fsrfg"))["status"] == "success"

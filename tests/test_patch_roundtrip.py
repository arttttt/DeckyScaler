"""Patch → unpatch round trips on a clean game must leave no trace."""

import asyncio
import json

import pytest

from conftest import NIGHTLY, STABLE, snapshot


def test_the_fixture_has_both_optiscaler_families(plugin, plugin_home):
    # Guards the harness itself: every other test patches with this library.
    assert [v["id"] for v in asyncio.run(plugin.library_installed())["versions"]] == [NIGHTLY, STABLE]


def test_manual_patch_then_unpatch_restores_clean_game_dir(plugin, plugin_home, game_dir):
    before = snapshot(game_dir)

    patched = asyncio.run(plugin.manual_patch_directory(str(game_dir), "dxgi.dll", STABLE))
    assert patched["status"] == "success", patched
    version_files = plugin_home / "library" / "versions" / "stable-0.9.4" / "files"
    assert (game_dir / "dxgi.dll").read_bytes() == (version_files / "OptiScaler.dll").read_bytes()
    assert (game_dir / "OptiScaler.ini").exists()

    unpatched = asyncio.run(plugin.manual_unpatch_directory(str(game_dir)))
    assert unpatched["status"] == "success", unpatched
    assert snapshot(game_dir) == before


def test_steam_patch_then_unpatch_restores_game_and_launch_options(plugin, plugin_home, steam_library):
    game_root = steam_library.add_game("1234", "Test Game")
    before = snapshot(game_root)
    user_options = "mangohud %command%"

    patched = asyncio.run(plugin.patch_game("1234", "dxgi.dll", user_options, STABLE))
    assert patched["status"] == "success", patched
    assert patched["target_dir"] == str(game_root)
    assert patched["launch_options"] == "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%"

    status = asyncio.run(plugin.get_game_status("1234"))
    assert status["patched"] is True
    assert status["optiscaler_version"] == "stable-0.9.4"

    unpatched = asyncio.run(plugin.unpatch_game("1234", patched["launch_options"]))  # what Steam holds now
    assert unpatched["status"] == "success", unpatched
    assert unpatched["launch_options"] == user_options
    assert snapshot(game_root) == before


def test_path_defaults_point_the_picker_at_home_and_the_native_steam_library(plugin, home):
    defaults = asyncio.run(plugin.get_path_defaults())

    assert defaults == {
        "home": str(home),
        "steam_common": str(home / ".local" / "share" / "Steam" / "steamapps" / "common"),
        "downloads": str(home),  # no Downloads folder: the picker opens at home
    }
    (home / "Downloads").mkdir()
    assert asyncio.run(plugin.get_path_defaults())["downloads"] == str(home / "Downloads")


def test_a_first_patch_without_the_games_launch_options_is_refused_and_changes_nothing(plugin, plugin_home, steam_library):
    root = steam_library.add_game("1234", "Test Game")
    before = snapshot(root)

    result = asyncio.run(plugin.patch_game("1234", "dxgi.dll", None, STABLE))

    assert result["status"] == "error" and "launch options" in result["message"]
    assert snapshot(root) == before


def test_a_repatch_without_the_games_launch_options_keeps_the_stored_ones(plugin, plugin_home, steam_library):
    steam_library.add_game("1234", "Test Game")
    patched = asyncio.run(plugin.patch_game("1234", "dxgi.dll", "mangohud %command%", STABLE))

    repatched = asyncio.run(plugin.patch_game("1234", "dxgi.dll", None, STABLE))
    unpatched = asyncio.run(plugin.unpatch_game("1234", patched["launch_options"]))  # what Steam still holds

    assert repatched["original_launch_options"] == "mangohud %command%"
    assert repatched["launch_options"] is None  # unknown, and the plugin's are what the last patch set: left
    assert unpatched["launch_options"] == "mangohud %command%"


def test_a_repatch_without_the_options_sets_them_when_the_plugins_change(plugin, plugin_home, steam_library):
    steam_library.add_game("1234", "Test Game")
    asyncio.run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))

    switched = asyncio.run(plugin.patch_game("1234", "winmm.dll", None, STABLE))

    assert switched["launch_options"] == "WINEDLLOVERRIDES=winmm=n,b SteamDeck=0 %command%"


def test_unpatching_leaves_launch_options_the_user_changed_since_the_patch_or_steam_didnt_say(plugin, plugin_home, steam_library):
    steam_library.add_game("1234", "Test Game")
    asyncio.run(plugin.patch_game("1234", "dxgi.dll", "mangohud %command%", STABLE))

    changed = asyncio.run(plugin.unpatch_game("1234", "gamemoderun %command%"))
    assert changed["launch_options"] is None  # the frontend leaves them
    assert changed["message"] == "Unpatched Test Game. Its launch options were changed since it was patched, so they were left as they are."

    asyncio.run(plugin.patch_game("1234", "dxgi.dll", "mangohud %command%", STABLE))
    unknown = asyncio.run(plugin.unpatch_game("1234", None))
    assert unknown["launch_options"] is None
    assert unknown["message"] == "Unpatched Test Game. Steam didn't say what its launch options are, so they were left as they are."


@pytest.mark.parametrize("users", ["SteamDeck=0 %command%", "PROTON_FSR4_UPGRADE=1 gamemoderun %command%"])
def test_a_users_own_options_that_look_like_the_plugins_come_back_after_unpatching(plugin, plugin_home, steam_library, users):
    steam_library.add_game("1234", "Test Game")
    patched = asyncio.run(plugin.patch_game("1234", "dxgi.dll", users, STABLE))

    assert asyncio.run(plugin.unpatch_game("1234", patched["launch_options"]))["launch_options"] == users


def test_the_plugin_serves_the_launch_setup(plugin):
    setup = asyncio.run(plugin.launch_setup())

    assert setup["default"] == "dxgi.dll" and setup["wrapper"]["patch"] == "~/deckyscaler/patch %command%"


def test_path_defaults_follow_a_flatpak_steam(plugin, home):
    flatpak_steamapps = home / ".var" / "app" / "com.valvesoftware.Steam" / "home" / ".local" / "share" / "Steam" / "steamapps"
    flatpak_steamapps.mkdir(parents=True)

    assert asyncio.run(plugin.get_path_defaults())["steam_common"] == str(flatpak_steamapps / "common")


def test_switching_the_proxy_takes_the_old_proxys_options_for_the_plugins_own(plugin, plugin_home, steam_library):
    steam_library.add_game("1234", "Test Game")
    first = asyncio.run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))

    switched = asyncio.run(plugin.patch_game("1234", "winmm.dll", first["launch_options"], STABLE))

    assert switched["original_launch_options"] == ""  # the dxgi options were the plugin's, not the user's
    assert asyncio.run(plugin.unpatch_game("1234", switched["launch_options"]))["launch_options"] == ""


def test_a_steam_game_the_wrapper_patched_is_known_by_its_page_and_stays_the_wrappers(plugin, home, plugin_home, steam_library):
    from deckyscaler.application.launch_wrapper import LaunchWrapper

    root = steam_library.add_game("1234", "Test Game")
    LaunchWrapper(home, {"SteamAppId": "1234"}).patch([str(root / "Game.exe")], "dxgi.dll")
    marker = json.loads((root / "DECKYSCALER_PATCH").read_text())
    assert (marker["appid"], marker["game_name"], marker["through"]) == ("1234", "Test Game", "wrapper")
    assert run_status(plugin)["by_wrapper"] is True
    assert [game["by_wrapper"] for game in asyncio.run(plugin.patched_games())["games"]] == [True]

    wrapped = "gamemoderun ~/deckyscaler/patch %command%"
    reinstalled = asyncio.run(plugin.patch_game("1234", "dxgi.dll", wrapped, STABLE))
    assert reinstalled["launch_options"] is None  # the wrapper stays: nothing to set
    assert reinstalled["message"].endswith("The launch wrapper stays in its launch options.")
    reinstalled_marker = json.loads((root / "DECKYSCALER_PATCH").read_text())
    assert (reinstalled_marker["through"], reinstalled_marker["launch_options"]) == ("wrapper", "")  # it set none

    unpatched = asyncio.run(plugin.unpatch_game("1234", wrapped))
    assert unpatched["launch_options"] == "gamemoderun %command%"
    assert unpatched["message"] == "Unpatched Test Game. The launch wrapper's command is out of its launch options."


def test_a_game_patched_from_the_panel_once_its_wrapper_is_taken_out_gets_the_plugins_options(plugin, home, plugin_home, steam_library):
    from deckyscaler.application.launch_wrapper import LaunchWrapper

    root = steam_library.add_game("1234", "Test Game")
    LaunchWrapper(home, {"SteamAppId": "1234"}).patch([str(root / "Game.exe")], "dxgi.dll")

    patched = asyncio.run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))  # the user took the wrapper out

    assert patched["launch_options"] == "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%"
    assert "through" not in json.loads((root / "DECKYSCALER_PATCH").read_text())


def test_unpatching_a_wrapper_game_steam_says_nothing_of_warns_it_comes_back(plugin, home, plugin_home, steam_library):
    from deckyscaler.application.launch_wrapper import LaunchWrapper

    root = steam_library.add_game("1234", "Test Game")
    LaunchWrapper(home, {"SteamAppId": "1234"}).patch([str(root / "Game.exe")], "dxgi.dll")

    unknown = asyncio.run(plugin.unpatch_game("1234", None))

    assert unknown["launch_options"] is None
    assert unknown["message"].endswith("If the launch wrapper is still in them, it patches the game again at its next start.")


def test_unpatching_a_directory_the_wrapper_patched_says_it_comes_back(plugin, home, plugin_home, tmp_path):
    from conftest import make_game_dir
    from deckyscaler.application.launch_wrapper import LaunchWrapper

    game = make_game_dir(tmp_path / "games" / "Heroic Game")
    LaunchWrapper(home, {}).patch([str(game / "Game.exe")], "dxgi.dll")

    result = asyncio.run(plugin.manual_unpatch_directory(str(game)))

    assert result["status"] == "success"
    assert result["message"].endswith("take ~/deckyscaler/patch out of how the game is started to keep it unpatched.")


def run_status(plugin) -> dict:
    return asyncio.run(plugin.get_game_status("1234"))


def test_a_start_that_changes_nothing_looks_up_no_game_and_marks_a_panel_patch_the_wrappers(plugin, home, plugin_home, steam_library, monkeypatch):
    from deckyscaler.application import patcher as patcher_module
    from deckyscaler.application.launch_wrapper import LaunchWrapper

    root = steam_library.add_game("1234", "Test Game")
    asyncio.run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))  # from the panel, then the user adds the wrapper
    assert "through" not in json.loads((root / "DECKYSCALER_PATCH").read_text())
    monkeypatch.setattr(patcher_module.steam_library, "find_game", lambda *_: (_ for _ in ()).throw(AssertionError("scanned")))

    LaunchWrapper(home, {"SteamAppId": "1234"}).patch([str(root / "Game.exe")], "dxgi.dll", STABLE)

    marker = json.loads((root / "DECKYSCALER_PATCH").read_text())
    assert (marker["through"], marker["appid"]) == ("wrapper", "1234")  # the panel's record kept, its route made true

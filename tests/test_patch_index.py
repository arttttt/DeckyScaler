"""Which games use a library version: the index of patched directories follows their markers (integration)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from conftest import NIGHTLY, REPO_ROOT, STABLE, make_game_dir, run


def using(plugin, version_id: str) -> list[str]:
    """The patched games and directories the plugin lists with a version."""
    return [g["name"] for g in run(plugin.patched_games())["games"] if g["version_id"] == version_id]
from deckyscaler.infrastructure import drives, game_directory
from deckyscaler.infrastructure.patch_index import PatchIndex

_ADD_FROM_A_PROCESS = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from deckyscaler.infrastructure.patch_index import PatchIndex
for n in range(int(sys.argv[3]), int(sys.argv[3]) + 100):
    PatchIndex(Path(sys.argv[2])).add(Path(f"/games/{n}"), f"Game {n}")
"""


def test_games_using_a_version_follow_patching_repatching_and_unpatching(plugin, plugin_home, steam_library, tmp_path):
    steam_library.add_game("1234", "Test Game")
    manual = make_game_dir(tmp_path / "games" / "Manual")

    run(plugin.patch_game("1234", "dxgi.dll", "", STABLE))
    run(plugin.manual_patch_directory(str(manual), "dxgi.dll", STABLE))
    assert sorted(using(plugin, STABLE)) == sorted([str(manual), "Test Game"])

    run(plugin.patch_game("1234", "dxgi.dll", "", NIGHTLY))
    assert using(plugin, STABLE) == [str(manual)]
    assert using(plugin, NIGHTLY) == ["Test Game"]

    run(plugin.manual_unpatch_directory(str(manual)))
    run(plugin.unpatch_game("1234"))
    assert using(plugin, STABLE) == []
    assert using(plugin, NIGHTLY) == []
    assert json.loads((plugin_home / "patched.json").read_text()) == {}  # the index does not grow with old patches


def test_a_directory_whose_marker_went_another_way_is_not_counted(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))

    (game / "DECKYSCALER_PATCH").unlink()  # e.g. the user deleted the game's files

    assert using(plugin, STABLE) == []


def test_a_game_on_a_card_taken_out_stays_indexed_and_keeps_its_version(plugin, plugin_home, tmp_path, monkeypatch):
    media = tmp_path / "run" / "media"
    card = media / "deck" / "SD"
    mounted = {card.resolve()}
    monkeypatch.setattr(drives, "REMOVABLE_MEDIA", (media,))
    monkeypatch.setattr(drives, "ismount", lambda path: Path(path) in mounted)
    game = make_game_dir(card / "Games" / "Card Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    indexed = lambda: json.loads((plugin_home / "patched.json").read_text())  # noqa: E731

    drawer = tmp_path / "drawer"
    card.rename(drawer)
    mounted.clear()  # the card is out

    assert using(plugin, STABLE) == []  # its patch can't be read
    assert str(game) in indexed()
    refused = run(plugin.library_remove(STABLE))
    assert refused == {
        "status": "error",
        "message": (
            f"{game} is on a drive that isn't mounted and may be patched with {STABLE}. "
            "Put the drive back in, or forget it on the Games page."
        ),
    }
    assert run(plugin.patched_games())["away"] == [{"directory": str(game), "name": str(game)}]

    drawer.rename(card)
    mounted.add(card.resolve())  # back in
    assert using(plugin, STABLE) == [str(game)]

    shutil.rmtree(game)  # deleted from the card while it is in
    assert using(plugin, STABLE) == []
    assert str(game) not in indexed()


def test_a_game_on_a_card_that_wont_be_back_is_forgotten_and_its_version_can_go(plugin, plugin_home, tmp_path, monkeypatch):
    media = tmp_path / "run" / "media"
    monkeypatch.setattr(drives, "REMOVABLE_MEDIA", (media,))
    monkeypatch.setattr(drives, "ismount", lambda path: False)  # nothing mounted: the card is out
    here = make_game_dir(tmp_path / "games" / "Here")
    run(plugin.manual_patch_directory(str(here), "dxgi.dll", NIGHTLY))
    away = str(media / "deck" / "SD" / "Games" / "Card Game")
    (plugin_home / "patched.json").write_text(json.dumps({**json.loads((plugin_home / "patched.json").read_text()), away: "Card Game"}))

    assert run(plugin.forget_patched(str(here))) == {
        "status": "error", "message": f"{here} isn't on a drive that is out: there is nothing to forget.",
    }
    assert run(plugin.forget_patched(away)) == {"status": "success", "message": "Card Game is forgotten."}

    assert run(plugin.patched_games())["away"] == []
    assert using(plugin, NIGHTLY) == [str(here)]  # the game that is there stays
    assert run(plugin.library_remove(STABLE))["status"] == "success"


def test_an_interrupted_patch_still_counts_as_using_its_version(plugin, plugin_home, tmp_path, monkeypatch):
    game = make_game_dir(tmp_path / "games" / "Game")

    def crash(operations, directory, source):
        raise OSError("device went to sleep")

    monkeypatch.setattr(game_directory, "execute", crash)
    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "error"

    assert using(plugin, STABLE) == [str(game)]


def test_a_read_only_index_never_fails_a_patch(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    (plugin_home / "patched.json").mkdir()  # cannot be written as a file

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"



def test_changes_the_plugin_and_launch_wrappers_make_at_once_all_land(tmp_path):
    path = tmp_path / "patched.json"

    def add(start: int) -> None:
        for n in range(start, start + 100):
            PatchIndex(path).add(Path(f"/games/{n}"), f"Game {n}")

    wrappers = [
        subprocess.Popen([sys.executable, "-c", _ADD_FROM_A_PROCESS, str(REPO_ROOT / "py_modules"), str(path), str(start)])
        for start in (1000, 1100, 1200)
    ]
    threads = [threading.Thread(target=add, args=(start,)) for start in range(0, 400, 100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [wrapper.wait() for wrapper in wrappers] == [0, 0, 0]

    assert len(PatchIndex(path).directories()) == 700

    def remove(start: int) -> None:
        for n in range(start, start + 100):
            PatchIndex(path).remove(Path(f"/games/{n}"))

    threads = [threading.Thread(target=remove, args=(start,)) for start in (0, 100, 1000, 1100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(PatchIndex(path).directories()) == sorted(
        f"/games/{n}" for n in [*range(200, 400), *range(1200, 1300)]
    )

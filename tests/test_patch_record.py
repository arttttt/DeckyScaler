"""The patch record: what a patch did, written first, and undone exactly (unit + integration)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import NIGHTLY, STABLE, game_file, make_game_dir, run, snapshot, write
from deckyscaler.domain import patch_record
from deckyscaler.domain.patch_plan import Copy, DeleteFile, Link, Move, RemoveTree
from deckyscaler.domain.patch_record import Backup, PatchRecord, Placed, RemoveDirIfEmpty
from deckyscaler.infrastructure import game_directory

HASHES = {
    "OptiScaler.dll": "a" * 64,
    "OptiScaler.ini": "b" * 64,
    "libxess.dll": "c" * 64,
    "plugins/OptiPatcher.asi": "d" * 64,
    "D3D12_Optiscaler/D3D12Core.dll": "e" * 64,
}

# ── unit: recording a plan ───────────────────────────────────────────────────


def test_a_plan_is_recorded_as_placed_files_backups_and_created_directories():
    operations = (
        Move("libxess.dll", "libxess.dll.b"),
        DeleteFile("nvngx.ini"),
        Copy("OptiScaler.dll", "dxgi.dll"),
        Copy("OptiScaler.ini", "OptiScaler.ini"),
        Copy("plugins/OptiPatcher.asi", "plugins/OptiPatcher.asi"),
        Copy("D3D12_Optiscaler/D3D12Core.dll", "D3D12_Optiscaler/D3D12Core.dll"),
        Copy("libxess.dll", "libxess.dll"),
    )

    recorded = patch_record.record(operations, frozenset({"Game.exe", "libxess.dll", "plugins"}), HASHES)

    assert recorded == PatchRecord(
        placed=(
            Placed("dxgi.dll", "a" * 64),
            Placed("OptiScaler.ini", None),  # OptiScaler rewrites its ini; it is ours whatever it holds
            Placed("plugins/OptiPatcher.asi", "d" * 64),
            Placed("D3D12_Optiscaler/D3D12Core.dll", "e" * 64),
            Placed("libxess.dll", "c" * 64),
        ),
        backups=(Backup("libxess.dll", "libxess.dll.b"),),
        # plugins/ was the game's own; D3D12_Optiscaler/ is the patch's.
        created_dirs=("D3D12_Optiscaler",),
    )


def test_what_a_patch_whose_record_is_gone_left_is_every_link_into_the_plugins_home():
    links = {
        "dxgi.dll": "/home/deck/deckyscaler/library/versions/v/files/OptiScaler.dll",
        "dxgi.dll.b": "/home/deck/deckyscaler/library/versions/old/files/OptiScaler.dll",  # set aside as a backup
        "OptiScaler/libxess.dll": "/home/deck/deckyscaler/library/versions/v/files/OptiScaler/libxess.dll",
        "OptiScaler/D3D12_OptiScaler/D3D12Core.dll": "/home/deck/deckyscaler/library/versions/v/files/x.dll",
        "OptiScaler/amdxcffx64.dll": "/home/deck/.steam/steamapps/compatdata/1/pfx/amdxcffx64.dll",  # FSR 4's driver
        "game.dll": "/home/deck/Games/game.dll",  # the user's own
        "near.dll": "/home/deck/deckyscaler-old/x.dll",  # beside the home, not in it
        "OptiScaler/own.dll": None,  # a file, not a link: never the plugin's by this
    }

    lost = patch_record.made_by_the_plugin(links, "/home/deck/deckyscaler")
    assert lost == ("OptiScaler/D3D12_OptiScaler/D3D12Core.dll", "OptiScaler/libxess.dll", "dxgi.dll", "dxgi.dll.b")
    assert patch_record.left_behind(lost) == (
        DeleteFile("OptiScaler/D3D12_OptiScaler/D3D12Core.dll"),
        DeleteFile("OptiScaler/libxess.dll"),
        DeleteFile("dxgi.dll"),
        DeleteFile("dxgi.dll.b"),
        RemoveDirIfEmpty("OptiScaler/D3D12_OptiScaler"),
        RemoveDirIfEmpty("OptiScaler"),
    )
    assert patch_record.made_by_the_plugin({"game.dll": "/home/deck/Games/game.dll"}, "/home/deck/deckyscaler") == ()
    assert patch_record.left_behind(()) == ()


def test_what_a_lost_patch_left_takes_the_plugins_library_folders_whole():
    dirs = ("OptiScaler/user-libraries", "OptiScaler/custom/Uniscaler")

    assert patch_record.left_behind(("dxgi.dll",), dirs) == (
        DeleteFile("dxgi.dll"),
        RemoveTree("OptiScaler/user-libraries"),
        RemoveTree("OptiScaler/custom/Uniscaler"),
        RemoveDirIfEmpty("OptiScaler/custom"),
        RemoveDirIfEmpty("OptiScaler"),
    )


def test_a_backup_a_patch_whose_record_is_gone_set_aside_is_restored_by_the_next_one():
    operations = (Link("OptiScaler.dll", "dxgi.dll"), Link("libxess.dll", "libxess.dll"), Link("D/x.dll", "D/x.dll"))
    hashes = {"OptiScaler.dll": "link:a", "libxess.dll": "link:b", "D/x.dll": "link:c"}

    adopted = patch_record.record(operations, frozenset({"Game.exe", "dxgi.dll.b", "libxess.dll.b", "D"}), hashes)
    assert adopted.backups == (Backup("dxgi.dll", "dxgi.dll.b"), Backup("libxess.dll", "libxess.dll.b"))

    there = patch_record.record(operations, frozenset({"Game.exe", "dxgi.dll", "dxgi.dll.b"}), hashes)
    assert there.backups == ()  # the file is there: its backup is someone else's business, as before

    moved = (Move("dxgi.dll", "dxgi.dll.b"), *operations)
    assert patch_record.record(moved, frozenset({"dxgi.dll"}), hashes).backups == (Backup("dxgi.dll", "dxgi.dll.b"),)


def test_a_placed_file_gone_or_not_as_placed_is_told_without_reading_it():
    patch = PatchRecord(
        placed=(
            Placed("dxgi.dll", "link:/lib/OptiScaler.dll"),
            Placed("OptiScaler/libxess.dll", "link:/lib/libxess.dll"),
            Placed("OptiScaler/a.dll", "link:/lib/a.dll"),
            Placed("OptiScaler/b.dll", "link:/lib/b.dll"),
            Placed("OptiScaler.ini", None),
            Placed("OptiScaler/custom/U/u.dll", "1" * 64),
        ),
        backups=(),
        created_dirs=(),
    )
    now = {
        "dxgi.dll": "link:/lib/OptiScaler.dll",
        "OptiScaler/libxess.dll": patch_record.FILE,  # a game update put its own there
        "OptiScaler/a.dll": None,  # gone, or leading nowhere
        "OptiScaler/b.dll": "link:/other/b.dll",
        "OptiScaler.ini": patch_record.FILE,  # rewritten by OptiScaler: only its being there counts
        "OptiScaler/custom/U/u.dll": patch_record.FILE,
    }

    assert patch_record.changed(patch, now) == ("OptiScaler/libxess.dll", "OptiScaler/a.dll", "OptiScaler/b.dll")
    assert patch_record.changed(patch, {**now, "OptiScaler.ini": None, "OptiScaler/custom/U/u.dll": None})[-2:] == (
        "OptiScaler.ini", "OptiScaler/custom/U/u.dll",
    )


def test_the_games_own_files_unpatch_cant_put_back_are_those_whose_backup_is_gone():
    patch = PatchRecord(
        placed=(Placed("dxgi.dll", "link:/lib/OptiScaler.dll"), Placed("libxess.dll", "link:/lib/libxess.dll"), Placed("a.dll", "1" * 64)),
        backups=(Backup("dxgi.dll", "dxgi.dll.b"), Backup("libxess.dll", "libxess.dll.b"), Backup("a.dll", "a.dll.b"), Backup("winmm.dll", "winmm.dll.b")),
        created_dirs=(),
    )
    whole = {"dxgi.dll": "link:/lib/OptiScaler.dll", "libxess.dll": "link:/lib/libxess.dll", "a.dll": "1" * 64,
             "dxgi.dll.b": "2" * 64, "libxess.dll.b": "3" * 64, "a.dll.b": "4" * 64, "winmm.dll.b": "5" * 64}

    assert patch_record.unrestorable(patch, whole) == ()
    gone = {path: kind for path, kind in whole.items() if not path.endswith(".b")}
    assert patch_record.unrestorable(patch, gone) == ("dxgi.dll", "libxess.dll", "a.dll", "winmm.dll")
    # Told without reading: the game put its own back where a link was (a verify), and Unpatch leaves it: nothing is
    # lost. A link gone or leading nowhere leaves the game without its own, and a file where a copy was can't be told
    # from the copy, which Unpatch takes.
    told = {**gone, "dxgi.dll": patch_record.FILE, "libxess.dll": None, "a.dll": patch_record.FILE}
    assert patch_record.unrestorable(patch, told) == ("libxess.dll", "a.dll", "winmm.dll")
    # Told by content, as Unpatch reads it: a game update's own file over the copy, or a link pointing elsewhere, is
    # left where it is; a link leading nowhere, still the patch's, goes.
    read = {**gone, "dxgi.dll": "link:/elsewhere/dxgi.dll", "a.dll": "6" * 64}
    assert patch_record.unrestorable(patch, read) == ("libxess.dll", "winmm.dll")
    # Where the patch placed nothing, anything there is the game's own, put back since (a verify): nothing is lost.
    assert patch_record.unrestorable(patch, {**told, "winmm.dll": patch_record.FILE}) == ("libxess.dll", "a.dll")
    assert patch_record.unrestorable(patch, {**read, "winmm.dll": "7" * 64}) == ("libxess.dll",)
    assert {op.name for op in patch_record.plan_unpatch(patch, read, marker="m")} == {"libxess.dll", "m"}  # what Unpatch takes


def test_the_record_round_trips_through_the_marker_and_old_markers_have_none():
    recorded = PatchRecord((Placed("dxgi.dll", "a" * 64), Placed("OptiScaler.ini", None)), (Backup("x", "x.b"),), ("d",))
    marker = {"dll_name": "dxgi.dll", **patch_record.to_json(recorded, complete=True)}

    assert patch_record.parse(json.loads(json.dumps(marker))) == recorded
    assert marker["complete"] is True
    assert patch_record.parse({"dll_name": "dxgi.dll", "backed_up_files": []}) is None
    assert patch_record.parse({"format": 2, "placed": "garbage"}) is None
    assert patch_record.parse({**marker, "format": 1}) is None
    owning = PatchRecord(recorded.placed, (), ("OptiScaler/custom/A", "OptiScaler/custom"), ("OptiScaler/custom/A",))
    assert patch_record.parse(patch_record.to_json(owning, complete=True)) == owning
    assert patch_record.parse({k: v for k, v in marker.items() if k != "owned_dirs"}).owned_dirs == ()


def test_files_a_program_rewrites_are_ours_whatever_they_hold_and_only_folders_the_patch_creates_are_owned_whole():
    provider = "OptiScaler/custom/ANR"
    operations = (
        Copy("/lib/anr/dlssg/nvngx_dlssg.dll", f"{provider}/dlssg/nvngx_dlssg.dll"),
        Copy("/lib/anr/dlssg/nr_fg.ini", f"{provider}/dlssg/nr_fg.ini"),
        Copy("/lib/x/x.dll", "Mods/custom/X/ffx/x.dll"),
    )
    hashes = {"/lib/anr/dlssg/nvngx_dlssg.dll": "1" * 64, "/lib/anr/dlssg/nr_fg.ini": "2" * 64, "/lib/x/x.dll": "3" * 64}

    recorded = patch_record.record(
        operations, frozenset({"Game.exe", "Mods", "Mods/custom", "Mods/custom/X"}), hashes,
        rewritten=frozenset({f"{provider}/dlssg/nr_fg.ini"}), owned_dirs=(provider, "Mods/custom/X"),
    )

    assert recorded.placed[1] == Placed(f"{provider}/dlssg/nr_fg.ini", None)
    assert recorded.placed[0].sha256 == "1" * 64
    assert recorded.owned_dirs == (provider,)  # Mods/custom/X was the game's: not the patch's to remove whole
    assert "Mods/custom" not in recorded.created_dirs and "OptiScaler/custom" in recorded.created_dirs


def test_a_folder_the_patch_makes_inside_one_the_game_had_is_the_patchs():
    operations = (Copy("/lib/anr/a.dll", "OptiScaler/custom/ANR/a.dll"), Link("OptiScaler/x.dll", "OptiScaler/D3D12/x.dll"))

    recorded = patch_record.record(
        operations, frozenset({"Game.exe", "OptiScaler", "OptiScaler/custom"}), {"/lib/anr/a.dll": "1" * 64, "OptiScaler/x.dll": "link:x"},
        owned_dirs=("OptiScaler/custom/ANR",),
    )

    assert recorded.created_dirs == ("OptiScaler/custom/ANR", "OptiScaler/D3D12")  # OptiScaler/ and custom/ were there
    assert recorded.owned_dirs == ("OptiScaler/custom/ANR",)

    behind_a_link = patch_record.record(
        operations, frozenset({"Game.exe", "OptiScaler"}), {"/lib/anr/a.dll": "1" * 64, "OptiScaler/x.dll": "link:x"},
        owned_dirs=("OptiScaler/custom/ANR",), links=frozenset({"OptiScaler"}),
    )
    assert behind_a_link.created_dirs == () and behind_a_link.owned_dirs == ()  # nothing behind it is listed


# ── unit: undoing a record ───────────────────────────────────────────────────

RECORD = PatchRecord(
    placed=(Placed("dxgi.dll", "a" * 64), Placed("libxess.dll", "c" * 64), Placed("OptiScaler.ini", None),
            Placed("D3D12_Optiscaler/D3D12Core.dll", "e" * 64)),
    backups=(Backup("libxess.dll", "libxess.dll.b"),),
    created_dirs=("D3D12_Optiscaler",),
)


def test_a_record_covers_the_paths_it_placed_and_no_others():
    placed = PatchRecord((Placed("dxgi.dll", "l"), Placed("libxess.dll", "l"), Placed("OptiScaler.ini", None)), (), ())

    assert patch_record.covers(placed, frozenset({"libxess.dll"}))
    assert patch_record.covers(placed, frozenset())
    assert not patch_record.covers(placed, frozenset({"libxess.dll", "libxess_dx11.dll"}))  # came back since


def test_undoing_removes_what_was_placed_restores_backups_and_drops_the_marker_last():
    current = {"dxgi.dll": "a" * 64, "libxess.dll": "c" * 64, "OptiScaler.ini": "f" * 64,
               "D3D12_Optiscaler/D3D12Core.dll": "e" * 64, "libxess.dll.b": "9" * 64}

    assert patch_record.plan_unpatch(RECORD, current) == (
        DeleteFile("dxgi.dll"),
        DeleteFile("libxess.dll"),
        DeleteFile("OptiScaler.ini"),
        DeleteFile("D3D12_Optiscaler/D3D12Core.dll"),
        Move("libxess.dll.b", "libxess.dll"),
        RemoveDirIfEmpty("D3D12_Optiscaler"),
        DeleteFile("DECKYSCALER_PATCH"),
    )


def test_a_folder_the_patch_owns_goes_whole_before_the_empty_ones():
    owning = PatchRecord((Placed("OptiScaler/custom/A/dlssg/a.dll", "1" * 64),), (), ("OptiScaler/custom/A/dlssg", "OptiScaler/custom/A"), ("OptiScaler/custom/A",))

    operations = patch_record.plan_unpatch(owning, {"OptiScaler/custom/A/dlssg/a.dll": "1" * 64})

    assert operations == (
        DeleteFile("OptiScaler/custom/A/dlssg/a.dll"),
        RemoveTree("OptiScaler/custom/A"),
        RemoveDirIfEmpty("OptiScaler/custom/A/dlssg"),
        RemoveDirIfEmpty("OptiScaler/custom/A"),
        DeleteFile("DECKYSCALER_PATCH"),
    )


def test_a_backup_comes_back_over_a_file_put_there_since():
    current = {"dxgi.dll": "a" * 64, "libxess.dll": "1" * 64, "libxess.dll.b": "9" * 64}

    operations = patch_record.plan_unpatch(RECORD, current)

    assert operations.index(DeleteFile("libxess.dll")) < operations.index(Move("libxess.dll.b", "libxess.dll"))


def test_a_file_put_there_since_stays_when_nothing_was_backed_up_for_it():
    current = {"dxgi.dll": "a" * 64, "D3D12_Optiscaler/D3D12Core.dll": "1" * 64}

    operations = patch_record.plan_unpatch(RECORD, current)

    assert DeleteFile("D3D12_Optiscaler/D3D12Core.dll") not in operations


def test_files_and_backups_already_gone_are_skipped():
    operations = patch_record.plan_unpatch(RECORD, {"dxgi.dll": "a" * 64})

    assert operations == (DeleteFile("dxgi.dll"), RemoveDirIfEmpty("D3D12_Optiscaler"), DeleteFile("DECKYSCALER_PATCH"))


# ── integration: the plugin ──────────────────────────────────────────────────


def test_patching_writes_the_record_and_unpatching_restores_the_game_exactly(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    before = snapshot(game)

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"
    marker = json.loads((game / "DECKYSCALER_PATCH").read_text())
    assert marker["format"] == 2 and marker["complete"] is True
    assert {"path": "dxgi.dll", "sha256": marker["placed"][0]["sha256"]} in marker["placed"]
    assert marker["backups"] == [{"original": "libxess.dll", "backup": "libxess.dll.b"}]

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before


def test_an_interrupted_patch_can_still_be_undone(plugin, plugin_home, tmp_path, monkeypatch):
    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    before = snapshot(game)
    real_execute = game_directory.execute

    def crash_halfway(operations, directory, fgmod_path):
        real_execute(operations[: len(operations) // 2], directory, fgmod_path)
        raise OSError("device went to sleep")

    monkeypatch.setattr(game_directory, "execute", crash_halfway)
    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "error"
    assert json.loads((game / "DECKYSCALER_PATCH").read_text())["complete"] is False
    monkeypatch.setattr(game_directory, "execute", real_execute)

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before


def test_a_marker_write_cut_short_leaves_the_record_whole_and_unpatching_takes_what_it_staged(plugin, plugin_home, tmp_path, monkeypatch):
    from deckyscaler.infrastructure import files

    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    before = snapshot(game)
    real_write = files.write_json
    marker_writes: list[Path] = []

    def stop_in_the_second(path, payload):
        if path.name.startswith("DECKYSCALER_PATCH"):
            marker_writes.append(path)
        if len(marker_writes) == 2 and path == marker_writes[-1]:
            path.write_text(json.dumps(payload)[:17])  # the stop comes in the middle of the write
            raise OSError("device went to sleep")
        real_write(path, payload)

    monkeypatch.setattr(files, "write_json", stop_in_the_second)
    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "error"
    monkeypatch.setattr(files, "write_json", real_write)

    assert json.loads((game / "DECKYSCALER_PATCH").read_text())["complete"] is False  # the record before the stop
    assert (game / "DECKYSCALER_PATCH.new").exists()
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before


def as_before_but_the_ini(after: dict, before: dict) -> bool:
    """The game as before a patch whose record was lost, but for its OptiScaler.ini: without the record it can't be
    told from the user's own, so it stays."""
    return {name: sha for name, sha in after.items() if name != "OptiScaler.ini"} == before and "OptiScaler.ini" in after


def test_a_game_whose_marker_was_lost_is_patched_again_over_what_the_lost_patch_left(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    (game / "DECKYSCALER_PATCH").unlink()  # its links stay: OptiScaler/ and dxgi.dll

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))["status"] == "success"
    assert not (game / "dxgi.dll.b").exists()  # the lost patch's proxy isn't taken for the game's own

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert as_before_but_the_ini(snapshot(game), before)


def test_the_games_own_files_a_lost_patch_set_aside_come_back_with_the_next_ones_unpatch(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    (game / "DECKYSCALER_PATCH").unlink()  # libxess.dll.b, the game's own, stays beside the lost patch's link

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert as_before_but_the_ini(snapshot(game), before)


def test_a_lost_patchs_proxy_once_set_aside_as_the_games_own_is_cleared(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    (game / "DECKYSCALER_PATCH").unlink()
    (game / "dxgi.dll").rename(game / "dxgi.dll.b")  # what patching again did before: the link kept as a backup

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert as_before_but_the_ini(snapshot(game), before)


DAMAGED = "DeckyScaler's record of this patch is damaged, so it can't be undone by it. Patch the game again to repair it."


def test_a_damaged_record_is_said_unpatching_is_refused_and_patching_again_repairs_it(plugin, plugin_home, steam_library):
    root = steam_library.add_game("900", "Damaged Game")
    before = snapshot(root)
    run(plugin.patch_game("900", "dxgi.dll", "", NIGHTLY))
    (root / "DECKYSCALER_PATCH").write_text('{"appid": "900", "dll_na')  # a write cut short by an older build

    status = run(plugin.get_game_status("900"))
    assert (status["patched"], status["record"], status["message"]) == (True, "damaged", DAMAGED)
    assert [game["record"] for game in run(plugin.patched_games())["games"]] == ["damaged"]
    assert run(plugin.preview_unpatch_game("900", "")) == {"status": "error", "message": DAMAGED}
    assert run(plugin.unpatch_game("900")) == {"status": "error", "message": DAMAGED}
    assert run(plugin.preview_unpatch_directory(str(root))) == {"status": "error", "message": DAMAGED}
    assert run(plugin.manual_unpatch_directory(str(root))) == {"status": "error", "message": DAMAGED}

    assert run(plugin.patch_game("900", "dxgi.dll", "", NIGHTLY))["status"] == "success"
    assert run(plugin.get_game_status("900"))["record"] == "ok"
    assert run(plugin.unpatch_game("900"))["status"] == "success"
    assert as_before_but_the_ini(snapshot(root), before)


def test_the_launch_wrapper_repairs_a_damaged_record_as_the_game_starts(plugin, plugin_home, home, tmp_path):
    from deckyscaler.application.launch_wrapper import LaunchWrapper

    game = make_game_dir(tmp_path / "games" / "Game")
    LaunchWrapper(home, {}).patch([str(game / "Game.exe")], "dxgi.dll")
    (game / "DECKYSCALER_PATCH").write_text("")

    LaunchWrapper(home, {}).patch([str(game / "Game.exe")], "dxgi.dll")

    assert patch_record.state(json.loads((game / "DECKYSCALER_PATCH").read_text())) == patch_record.OK


@pytest.mark.parametrize("version", [STABLE, NIGHTLY])
def test_a_patch_an_early_build_recorded_under_the_originals_name_is_undone_by_its_record(plugin, plugin_home, tmp_path, version):
    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", version))
    (game / "DECKYSCALER_PATCH").rename(game / "FRAMEGEN_PATCH")  # where those builds wrote it

    assert run(plugin.preview_unpatch_directory(str(game)))["mode"] == "record"
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before  # exactly: OptiScaler 10's links under OptiScaler/ included


def test_patching_over_a_patch_recorded_under_the_originals_name_undoes_it_first(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    (game / "DECKYSCALER_PATCH").rename(game / "FRAMEGEN_PATCH")

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"
    assert not (game / "FRAMEGEN_PATCH").exists() and (game / "DECKYSCALER_PATCH").is_file()
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before


def test_the_plugins_own_marker_wins_over_a_record_under_the_originals_name(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    (game / "FRAMEGEN_PATCH").write_text((game / "DECKYSCALER_PATCH").read_text())  # an early build's, left beside

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert not (game / "DECKYSCALER_PATCH").exists()  # undone by its own record


def _damage(game: Path) -> None:
    (game / "DECKYSCALER_PATCH").write_text("")


def _lose(game: Path) -> None:
    (game / "DECKYSCALER_PATCH").unlink()


def _damage_with_its_links_gone(game: Path) -> None:
    (game / "DECKYSCALER_PATCH").write_text("")
    (game / "dxgi.dll").unlink()
    shutil.rmtree(game / "OptiScaler")


@pytest.mark.parametrize("break_record", [_damage, _lose, _damage_with_its_links_gone])
def test_a_repaired_game_gets_a_fresh_ini_the_settings_reach(plugin, plugin_home, tmp_path, break_record):
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    break_record(game)

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))["status"] == "success"
    assert run(plugin.set_setting("global", "FSR", "Fsr4Model", "1"))["status"] == "success"

    assert "Fsr4Model=1" in (game / "OptiScaler.ini").read_text()
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert as_before_but_the_ini(snapshot(game), before)  # the lost patch's ini, set aside as the game's, is back


def test_a_repair_with_another_family_clears_the_lost_patchs_links_too(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))  # OptiScaler 10: its files under OptiScaler/
    (game / "DECKYSCALER_PATCH").unlink()

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"  # 0.9: beside it
    assert not (game / "OptiScaler").exists()

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert as_before_but_the_ini(snapshot(game), before)


def test_a_patch_recorded_under_the_originals_name_is_listed_and_keeps_its_version(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    (game / "DECKYSCALER_PATCH").rename(game / "FRAMEGEN_PATCH")

    assert [listed["name"] for listed in run(plugin.patched_games())["games"]] == [str(game)]
    assert run(plugin.library_remove(NIGHTLY))["status"] == "error"


def test_a_steam_game_recorded_under_the_originals_name_goes_back_into_the_index_when_found(plugin, plugin_home, steam_library):
    root = steam_library.add_game("910", "Early Game")
    run(plugin.patch_game("910", "dxgi.dll", "", NIGHTLY))
    (root / "DECKYSCALER_PATCH").rename(root / "FRAMEGEN_PATCH")
    (plugin_home / "patched.json").write_text("{}")

    assert run(plugin.get_game_status("910"))["record"] == "ok"
    assert [listed["name"] for listed in run(plugin.patched_games())["games"]] == ["Early Game"]


def test_a_repair_clears_the_links_of_a_version_no_longer_in_the_library(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    before = snapshot(game)
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))
    (game / "DECKYSCALER_PATCH").unlink()
    assert run(plugin.library_remove(NIGHTLY))["status"] == "success"  # nothing records a game using it now

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"
    assert not (game / "OptiScaler").exists()
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert as_before_but_the_ini(snapshot(game), before)


def test_every_directory_in_a_familys_folder_is_walked_but_none_through_a_link(tmp_path):
    game = tmp_path / "Game"
    (game / "OptiScaler" / "D3D12_OptiScaler").mkdir(parents=True)
    (game / "OptiScaler" / "custom" / "Provider").mkdir(parents=True)
    (tmp_path / "elsewhere" / "inside").mkdir(parents=True)
    (game / "OptiScaler" / "linked").symlink_to(tmp_path / "elsewhere")
    (game / "D3D12_Optiscaler").symlink_to(tmp_path / "elsewhere")
    (game / "Content" / "Paks").mkdir(parents=True)

    assert game_directory.directories_under(game, ("D3D12_Optiscaler", "OptiScaler", "Missing")) == {
        "OptiScaler", "OptiScaler/D3D12_OptiScaler", "OptiScaler/custom", "OptiScaler/custom/Provider",
    }


def test_optiscaler_unpacked_by_hand_is_set_aside_file_by_file_and_back_after_unpatching(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game", {
        "dxgi.dll": b"hand-installed OptiScaler",
        "OptiScaler.ini": b"[Menu]\nUseHQFont=false\n",
        "OptiScaler/libxess.dll": b"hand-installed libxess",
        "OptiScaler/D3D12_OptiScaler/D3D12Core.dll": b"hand-installed D3D12Core",
    })
    before = snapshot(game)

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", NIGHTLY))["status"] == "success"
    assert (game / "OptiScaler" / "libxess.dll.b").read_bytes() == b"hand-installed libxess"
    assert (game / "OptiScaler" / "D3D12_OptiScaler" / "D3D12Core.dll.b").read_bytes() == b"hand-installed D3D12Core"

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert snapshot(game) == before


def test_a_patched_game_says_which_of_its_files_are_gone_or_changed_and_patching_again_mends_them(plugin, plugin_home, steam_library, monkeypatch):
    from deckyscaler.infrastructure import files

    root = steam_library.add_game("950", "Changed Game")
    run(plugin.patch_game("950", "dxgi.dll", "", STABLE))
    (root / "fakenvapi.dll").unlink()
    (root / "libxess.dll").unlink()
    write(root / "libxess.dll", b"a game update's own")
    (root / "dxgi.dll").unlink()  # the proxy is told on its own
    real_sha256 = files.sha256
    monkeypatch.setattr(files, "sha256", lambda path: (_ for _ in ()).throw(AssertionError(f"read {path}")))

    status = run(plugin.get_game_status("950"))
    listed = run(plugin.patched_games())["games"][0]

    assert sorted(status["changed_files"]) == ["fakenvapi.dll", "libxess.dll"] == sorted(listed["changed_files"])
    monkeypatch.setattr(files, "sha256", real_sha256)  # patching reads what it copies
    assert run(plugin.patch_game("950", "dxgi.dll", "", STABLE))["status"] == "success"
    assert run(plugin.get_game_status("950"))["changed_files"] == []


def test_a_placed_link_leading_nowhere_is_changed(plugin, plugin_home, home, tmp_path):
    from deckyscaler.application.patcher import Patcher

    game = make_game_dir(tmp_path / "games" / "Game")
    assert Patcher(home).patch_directory(game, "dxgi.dll", version_id=NIGHTLY)["status"] == "success"
    (plugin_home / "library" / "versions" / NIGHTLY / "files" / "OptiScaler" / "libxess.dll").unlink()

    assert run(plugin.patched_games())["games"][0]["changed_files"] == ["OptiScaler/libxess.dll"]


def test_a_game_whose_backup_is_gone_says_so_before_and_after_unpatching(plugin, plugin_home, steam_library):
    root = steam_library.add_game("960", "Backup Game", {"libxess.dll": game_file("libxess.dll")})
    patched = run(plugin.patch_game("960", "dxgi.dll", "", STABLE))
    assert run(plugin.get_game_status("960"))["lost_backups"] == []  # its backup is there
    (root / "libxess.dll.b").unlink()  # the game's own, set aside: gone

    assert run(plugin.get_game_status("960"))["lost_backups"] == ["libxess.dll"]
    assert run(plugin.patched_games())["games"][0]["lost_backups"] == ["libxess.dll"]
    unpatched = run(plugin.unpatch_game("960", patched["launch_options"]))  # what Steam holds
    assert unpatched["message"] == (
        "Unpatched Backup Game. No backup of libxess.dll was left, so the game's own couldn't be put back: "
        "restore it with Steam's Verify integrity of game files."
    )


def test_a_folder_unpatched_without_a_backup_says_the_games_own_couldnt_be_put_back(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    (game / "libxess.dll.b").unlink()

    unpatched = run(plugin.manual_unpatch_directory(str(game)))

    assert unpatched["lost_backups"] == ["libxess.dll"]
    assert unpatched["message"] == (
        f"OptiScaler files removed from {game}. No backup of libxess.dll was left, so the game's own couldn't be put "
        "back: restore it with Steam's Verify integrity of game files."
    )


def test_a_proxy_leading_nowhere_without_its_backup_is_told_before_unpatching_as_unpatching_tells_it(plugin, plugin_home, steam_library):
    root = steam_library.add_game("961", "Dangling Game", {"dxgi.dll": game_file("dxgi.dll")})
    patched = run(plugin.patch_game("961", "dxgi.dll", "", STABLE))
    (root / "dxgi.dll").resolve().unlink()  # the library's file the proxy links to: gone
    (root / "dxgi.dll.b").unlink()

    assert run(plugin.get_game_status("961"))["lost_backups"] == ["dxgi.dll"]
    assert run(plugin.patched_games())["games"][0]["lost_backups"] == ["dxgi.dll"]
    unpatched = run(plugin.unpatch_game("961", patched["launch_options"]))
    assert unpatched["message"] == (
        "Unpatched Dangling Game. No backup of dxgi.dll was left, so the game's own couldn't be put back: "
        "restore it with Steam's Verify integrity of game files."
    )
    assert not (root / "dxgi.dll").is_symlink() and not (root / "dxgi.dll").exists()


def test_a_proxy_of_the_games_own_set_aside_and_put_back_by_a_verify_is_not_lost(plugin, plugin_home, steam_library):
    root = steam_library.add_game("962", "Version Game", {"version.dll": game_file("version.dll")})
    patched = run(plugin.patch_game("962", "dxgi.dll", "", STABLE))
    assert not (root / "version.dll").exists() and (root / "version.dll.b").is_file()  # set aside, nothing in its place
    (root / "version.dll.b").unlink()
    write(root / "version.dll", game_file("version.dll"))  # Steam's Verify puts the game's own back

    assert run(plugin.get_game_status("962"))["lost_backups"] == []
    assert run(plugin.patched_games())["games"][0]["lost_backups"] == []
    assert run(plugin.unpatch_game("962", patched["launch_options"]))["message"] == "Unpatched Version Game."
    assert (root / "version.dll").read_bytes() == game_file("version.dll")


def test_after_a_verify_the_games_own_proxy_is_told_and_the_patch_set_aside_as_its_backup_is_matched(plugin, plugin_home, tmp_path):
    shipped = game_file("dxgi.dll")
    game = make_game_dir(tmp_path / "games" / "Game", {"dxgi.dll": shipped})
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    (game / "DECKYSCALER_PATCH").unlink()  # the record lost, and Steam's Verify put the game's own back:
    (game / "dxgi.dll").unlink()
    write(game / "dxgi.dll", shipped)  # dxgi.dll and the same dxgi.dll.b side by side

    assert run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))["status"] == "success"
    assert (game / "dxgi.dll.b").read_bytes() == shipped and (game / "dxgi.dll").is_symlink()

    (game / "dxgi.dll").unlink()
    write(game / "dxgi.dll", shipped)  # verified again, now with the record there
    assert run(plugin.patched_games())["games"][0]["proxy_taken_back"] is True
    (game / "DECKYSCALER_PATCH").unlink()
    write(game / "dxgi.dll.b", b"another build")  # and a backup that isn't the same
    refused = run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    assert refused["status"] == "error" and "so is a different dxgi.dll.b" in refused["message"]


def test_what_is_in_a_game_is_looked_for_only_where_asked_and_never_through_a_link(tmp_path):
    game = tmp_path / "Game"
    write(game / "OptiScaler" / "keep.txt", b"game")
    (game / "OptiScaler" / "a.dll").symlink_to(tmp_path / "a.dll")
    (game / "dxgi.dll").symlink_to(tmp_path / "b.dll")
    (game / "Content").mkdir()
    (game / "Content" / "c.dll").symlink_to(tmp_path / "c.dll")  # no version links there
    (tmp_path / "elsewhere" / "D3D12_OptiScaler").mkdir(parents=True)
    (tmp_path / "elsewhere" / "D3D12_OptiScaler" / "d.dll").symlink_to(tmp_path / "d.dll")
    (game / "OptiScaler" / "D3D12_OptiScaler").symlink_to(tmp_path / "elsewhere" / "D3D12_OptiScaler")

    found = game_directory.contents(game, ("OptiScaler/D3D12_OptiScaler", "OptiScaler", ""))

    assert found == {
        "OptiScaler/keep.txt": None,
        "OptiScaler/a.dll": str(tmp_path / "a.dll"),
        "OptiScaler/D3D12_OptiScaler": str(tmp_path / "elsewhere" / "D3D12_OptiScaler"),  # a link itself, not entered
        "OptiScaler": None,
        "Content": None,  # listed as an entry of the game's own directory, not looked into
        "dxgi.dll": str(tmp_path / "b.dll"),
    }
    linked = tmp_path / "Linked"  # OptiScaler/ itself a link: nothing under it is looked into
    (tmp_path / "kept" / "D3D12_OptiScaler").mkdir(parents=True)
    (tmp_path / "kept" / "D3D12_OptiScaler" / "e.dll").symlink_to(tmp_path / "e.dll")
    linked.mkdir()
    (linked / "OptiScaler").symlink_to(tmp_path / "kept")
    assert game_directory.contents(linked, ("OptiScaler/D3D12_OptiScaler", "OptiScaler", "")) == {"OptiScaler": str(tmp_path / "kept")}


def test_unpatching_restores_the_backup_over_a_file_put_there_after_patching(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game", {"libxess.dll": game_file("libxess.dll")})
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    (game / "libxess.dll").unlink()  # replacing the file; writing through the link would change the library
    write(game / "libxess.dll", b"someone's own libxess")

    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    # The directory goes back to how it was before the patch: what came after is its owner's to track.
    assert (game / "libxess.dll").read_bytes() == game_file("libxess.dll")
    assert not (game / "libxess.dll.b").exists()
    assert not (game / "dxgi.dll").exists()


def test_a_failed_unpatch_keeps_the_marker_and_says_so(plugin, plugin_home, tmp_path, monkeypatch):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))
    real_execute = game_directory.execute

    def fail_before_the_end(operations, directory, fgmod_path):
        real_execute(operations[:2], directory, fgmod_path)
        raise PermissionError("read-only file system")

    monkeypatch.setattr(game_directory, "execute", fail_before_the_end)
    result = run(plugin.manual_unpatch_directory(str(game)))

    assert result == {"status": "error", "message": "Permission error while unpatching: read-only file system"}
    assert (game / "DECKYSCALER_PATCH").exists()
    monkeypatch.setattr(game_directory, "execute", real_execute)
    assert run(plugin.manual_unpatch_directory(str(game)))["status"] == "success"
    assert sorted(p.name for p in game.iterdir()) == ["Game.exe"]


@pytest.mark.parametrize("action", ["unpatch", "patch"])
def test_a_game_patched_by_an_older_version_is_left_alone(plugin, plugin_home, tmp_path, action):
    old_marker = json.dumps({"dll_name": "dxgi.dll", "backed_up_files": ["libxess.dll"]}).encode()
    game = make_game_dir(tmp_path / "games" / "Game", {"FRAMEGEN_PATCH": old_marker, "dxgi.dll": b"old opti"})
    before = snapshot(game)

    if action == "unpatch":
        result = run(plugin.manual_unpatch_directory(str(game)))
    else:
        result = run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))

    assert result == {"status": "error", "message": "This game was patched by Decky Framegen. "
                                                     "Unpatch it first: the plugin shows what that removes."}
    assert snapshot(game) == before


def test_a_steam_game_patched_by_an_older_version_says_so_and_keeps_its_launch_options(plugin, steam_library):
    old_marker = json.dumps({"dll_name": "dxgi.dll", "original_launch_options": "mangohud %command%"}).encode()
    root = steam_library.add_game("800", "Old Steam Game", {"FRAMEGEN_PATCH": old_marker, "dxgi.dll": b"old opti"})
    before = snapshot(root)

    status = run(plugin.get_game_status("800"))
    result = run(plugin.unpatch_game("800"))

    assert status["patched"] is True and "patched by Decky Framegen" in status["message"]
    assert result["status"] == "error" and "launch_options" not in result
    assert snapshot(root) == before


@pytest.mark.parametrize("reset_ini", [False, True])
def test_a_repatch_keeps_the_users_ini_settings_unless_asked_to_reset_them(plugin, plugin_home, tmp_path, reset_ini):
    from deckyscaler.application.patcher import Patcher

    game = make_game_dir(tmp_path / "games" / "Game")
    patcher = Patcher(tmp_path / "home")
    patcher.patch_directory(game, "dxgi.dll")
    write(game / "OptiScaler.ini", (game / "OptiScaler.ini").read_bytes() + b"\n[Mine]\nKeep=1\n")

    assert patcher.patch_directory(game, "dxgi.dll", reset_ini=reset_ini)["status"] == "success"

    assert (b"Keep=1" in (game / "OptiScaler.ini").read_bytes()) is not reset_ini
    # Either way the ini is the patch's, and unpatching removes it.
    assert patcher.unpatch_directory(game)["status"] == "success"
    assert sorted(p.name for p in game.iterdir()) == ["Game.exe"]


def test_unpatching_a_directory_with_a_record_needs_no_confirmation(plugin, plugin_home, tmp_path):
    game = make_game_dir(tmp_path / "games" / "Game")
    run(plugin.manual_patch_directory(str(game), "dxgi.dll", STABLE))

    assert run(plugin.preview_unpatch_directory(str(game))) == {"status": "success", "mode": "record", "target_dir": str(game)}


def test_a_patched_game_whose_marker_names_a_stale_path_still_reads_as_patched(plugin, plugin_home, steam_library):
    root = steam_library.add_game("740", "Moved Game")
    run(plugin.patch_game("740", "dxgi.dll", "", STABLE))
    marker_path = root / "DECKYSCALER_PATCH"
    marker_path.write_text(json.dumps({**json.loads(marker_path.read_text()), "target_dir": "/run/media/gone/Moved Game"}))

    status = run(plugin.get_game_status("740"))

    assert status["patched"] is True and status["target_dir"] == str(root)


def test_a_patch_is_intact_while_everything_it_placed_is_there_as_placed():
    whole = {"dxgi.dll": "a" * 64, "libxess.dll": "c" * 64, "OptiScaler.ini": "rewritten by OptiScaler",
             "D3D12_Optiscaler/D3D12Core.dll": "e" * 64}

    assert patch_record.intact(RECORD, whole)
    assert not patch_record.intact(RECORD, {k: v for k, v in whole.items() if k != "dxgi.dll"})
    assert not patch_record.intact(RECORD, {**whole, "libxess.dll": "1" * 64})
    assert not patch_record.intact(RECORD, {k: v for k, v in whole.items() if k != "OptiScaler.ini"})


def test_a_file_a_program_rewrites_that_is_gone_breaks_the_patch():
    provider = PatchRecord((Placed("OptiScaler/custom/A/dlssg/a.ini", None),), (), (), ())

    assert patch_record.intact(provider, {"OptiScaler/custom/A/dlssg/a.ini": "whatever the provider wrote"})
    assert not patch_record.intact(provider, {})


def test_a_marker_describes_a_finished_patch_of_this_version_under_this_name():
    from deckyscaler.domain import marker

    details = {"complete": True, "optiscaler_version": "nightly-1", "dll_name": "dxgi.dll"}

    assert marker.describes(details, "nightly-1", "dxgi.dll")
    assert not marker.describes({**details, "complete": False}, "nightly-1", "dxgi.dll")
    assert not marker.describes(details, "nightly-2", "dxgi.dll")
    assert not marker.describes(details, "nightly-1", "winmm.dll")


def test_a_patched_directory_is_shown_by_its_games_name_else_by_its_path():
    from deckyscaler.domain import marker

    game = marker.build(
        dll_name="dxgi.dll", target_dir=Path("/g"), backed_up_files=[], optiscaler_version="nightly-1", family="10",
        patched_at="t", steam_game=marker.SteamGame("1234", "Hades II", ""),
    )
    by_path = {**game, "game_name": ""}

    assert marker.shown_name(game, Path("/g")) == "Hades II"
    assert marker.shown_name(by_path, Path("/g")) == "/g"
    assert marker.shown_name({}, Path("/g")) == "/g"  # no marker to read


def test_a_marker_describes_a_patch_with_the_libraries_it_placed_and_keeps_the_keys_they_own():
    from deckyscaler.domain import marker
    from deckyscaler.domain.settings_layers import Owned

    layer = {("FrameGen", "FGInput"): Owned("nvngxfg", "ANR")}
    details = {
        **marker.build(
            dll_name="dxgi.dll", target_dir=Path("/g"), backed_up_files=[], optiscaler_version="nightly-1", family="10",
            patched_at="t", libraries=({"slot": "frame-generation", "id": "anr", "label": "ANR"},), library_layer=layer,
        ),
        "complete": True,
    }
    details = json.loads(json.dumps(details))

    assert marker.describes(details, "nightly-1", "dxgi.dll", (("frame-generation", "anr"),))
    assert not marker.describes(details, "nightly-1", "dxgi.dll")
    assert marker.library_layer(details) == layer
    assert marker.describes({**details, "libraries": None}, "nightly-1", "dxgi.dll")  # before libraries: none placed
    assert marker.library_layer({}) == {}


def test_a_patch_placed_only_what_its_record_lists():
    assert patch_record.placed_by(RECORD, "OptiScaler.ini")
    assert not patch_record.placed_by(RECORD, "game.ini")
    assert not patch_record.placed_by(None, "OptiScaler.ini")

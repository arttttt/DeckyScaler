"""Proton builds through the plugin: listing, installing and removing against a fake GitHub and Steam (integration)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from conftest import FakeDownload, run, sha256, write
from deckyscaler.application.proton_builds import ProtonBuilds
from deckyscaler.domain import proton_builds as pb
from deckyscaler.domain import steam
from deckyscaler.infrastructure import github_releases, processes
from test_binary_keyvalues import encode
from test_compat_tools_store import build_tree, tarball

FIXTURES = Path(__file__).parent / "fixtures"
NEWEST = "GE-Proton11-12-x86_64"
SHORTCUT_APPID = str(2**32 - 5)



@pytest.fixture
def world(home, tmp_path, steam_library, github_api, monkeypatch):
    """A native Steam that has run (its config names the games' tools), no Steam client running, and GitHub
    publishing GE-Proton with the newest x86_64 archive being `world.archive`."""
    monkeypatch.setattr(processes, "started_processes", lambda: [])

    class World:
        root = steam_library.root.resolve()
        tools = root / "compatibilitytools.d"
        moves_file = tmp_path / "settings" / "proton.json"
        reports: list = []

        def publish(self, archive_bytes: bytes) -> None:
            listing = json.loads((FIXTURES / "ge_proton.json").read_text())
            asset = next(a for a in listing[0]["assets"] if a["name"] == f"{NEWEST}.tar.gz")
            asset["digest"], asset["size"] = f"sha256:{sha256(archive_bytes)}", len(archive_bytes)
            github_api.body = json.dumps(listing).encode()
            self.archive = archive_bytes

        def proton(self, download=None) -> ProtonBuilds:
            return ProtonBuilds(home, github_releases.list_releases, download or FakeDownload(self.archive),
                                lambda *args: self.reports.append(args), self.moves_file)

        def tree(self) -> list[str]:
            return sorted(p.relative_to(self.tools).as_posix() for p in self.tools.glob("*")) if self.tools.exists() else []

    world = World()
    world.publish(tarball(tmp_path / "archives", name=NEWEST).read_bytes())
    steam_library.add_game("730", "Counter-Strike 2")
    steam_library.set_compat_tools({"730": NEWEST, SHORTCUT_APPID: NEWEST, "1245620": NEWEST})
    write(world.root / "userdata/1/config/shortcuts.vdf", encode({"shortcuts": {"0": {"appid": -5, "AppName": "Heroic"}}}))
    return world


def test_installing_puts_the_build_into_compatibilitytools_d(world):
    result = world.proton().install(pb.GE_PROTON, NEWEST)

    assert result == {"status": "success", "id": NEWEST, "message": f"{NEWEST} is installed. Restart Steam to use it."}
    assert (world.tools / NEWEST / "files/share/default_pfx/drive_c/windows/regedit.exe").read_bytes() == b"regedit"
    assert world.tree() == [".deckyscaler-partial", NEWEST]
    assert list((world.tools / ".deckyscaler-partial").iterdir()) == []
    assert world.reports[-1] == (NEWEST, len(world.archive), len(world.archive))

    rows = world.proton().versions(pb.GE_PROTON)["versions"]
    assert rows[0] == {"id": NEWEST, "version": "GE-Proton11-12", "date": "20261103", "state": "installed",
                       "reason": None, "size": len(world.archive)}
    assert "already installed" in world.proton().install(pb.GE_PROTON, NEWEST)["message"]


def failing(world, tmp_path, case) -> ProtonBuilds:
    if case == "checksum":
        return world.proton(FakeDownload(b"not the published archive"))
    if case == "not-an-archive":
        world.publish(b"not a tarball")
    if case == "wrong-directory":
        world.publish(tarball(tmp_path / "other", name="GE-Proton11-12").read_bytes())
    if case == "no-toolmanifest":
        source = tmp_path / "partial-build"
        build_tree(source, NEWEST)
        (source / NEWEST / "toolmanifest.vdf").unlink()
        import tarfile
        archive_path = tmp_path / "partial.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(source / NEWEST, arcname=NEWEST)
        world.publish(archive_path.read_bytes())
    return world.proton()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("checksum", "did not match its checksum"),
        ("not-an-archive", f"Installing {NEWEST} failed: Failed to unpack"),
        ("wrong-directory", f"holds GE-Proton11-12 instead of one {NEWEST} directory; not installed"),
        ("no-toolmanifest", "lacks toolmanifest.vdf; not installed"),
    ],
)
def test_a_failed_install_leaves_compatibilitytools_d_as_it_was(world, tmp_path, case, message):
    result = failing(world, tmp_path, case).install(pb.GE_PROTON, NEWEST)

    assert result["status"] == "error" and message in result["message"]
    assert world.tree() in ([], [".deckyscaler-partial"])
    assert not any((world.tools / ".deckyscaler-partial").iterdir())


def test_an_install_without_room_is_refused_before_downloading(world, monkeypatch):
    download = FakeDownload(world.archive)
    monkeypatch.setattr("deckyscaler.infrastructure.compat_tools_store.CompatToolsStore.free_bytes", lambda self: 10)

    result = world.proton(download).install(pb.GE_PROTON, NEWEST)

    assert result["message"].startswith(f"Not enough free space: installing {NEWEST} needs about")
    assert download.urls == []


def test_a_newest_release_still_uploading_leaves_the_previous_one_installable(world, github_api):
    listing = json.loads(github_api.body)
    listing[0]["assets"] = [a | {"state": "starter"} for a in listing[0]["assets"]]
    previous = next(a for a in listing[1]["assets"] if a["name"] == "GE-Proton11-11-x86_64.tar.gz")
    previous["digest"], previous["size"] = f"sha256:{sha256(world.archive)}", len(world.archive)
    github_api.body = json.dumps(listing).encode()
    proton = world.proton()

    assert proton.install(pb.GE_PROTON, NEWEST)["message"] == f"{NEWEST} can't be downloaded now. Check again."
    rows = proton.versions(pb.GE_PROTON)["versions"]
    assert (rows[0]["state"], rows[0]["reason"], rows[1]["state"]) == ("unsupported", "uploading", "available")


def test_only_a_release_the_build_publishes_is_installed(world):
    assert "is no longer published" in world.proton().install(pb.GE_PROTON, "GE-Proton9-1")["message"]
    assert world.proton().install("valve-proton", NEWEST) == {"status": "error", "message": "Unknown build: valve-proton"}


def test_without_a_steam_to_install_into_nothing_is_written_and_the_frontend_is_told_why(world):
    (world.root / "config" / "config.vdf").unlink()
    proton = world.proton()

    assert proton.install(pb.GE_PROTON, NEWEST) == {"status": "error", "problem": steam.NO_STEAM}
    assert proton.installed() == {"status": "success", "problem": steam.NO_STEAM, "tools": [], "others": [], "installed_bytes": 0,
                                  "restart_needed": False, "moves": []}
    assert proton.versions(pb.GE_PROTON)["problem"] == steam.NO_STEAM
    assert world.tree() == []


def test_installed_builds_list_every_tool_with_the_games_whose_user_chose_it(world, home):
    world.proton().install(pb.GE_PROTON, NEWEST)
    build_tree(world.tools, "Proton-EM-10.0-37")
    build_tree(home.parent / "system-compatibilitytools.d", "proton-cachyos-11.0-20261015-slr-x86_64")

    listed = world.proton().installed(with_sizes=True)

    tools = {tool["id"]: tool for tool in listed["tools"]}
    assert tools[NEWEST] | {"size": 0} == {
        "id": NEWEST, "build": pb.GE_PROTON, "build_label": "GE-Proton", "system": False, "linked": False, "size": 0,
        "games": [
            {"appid": "1245620", "name": None, "kind": "unknown"},  # uninstalled since: still the user's choice
            {"appid": SHORTCUT_APPID, "name": "Heroic", "kind": "shortcut"},
            {"appid": "730", "name": "Counter-Strike 2", "kind": "steam"},
        ],
        "global_default": False,
    }
    assert tools["Proton-EM-10.0-37"]["build"] is None and tools["Proton-EM-10.0-37"]["games"] == []
    system = tools["proton-cachyos-11.0-20261015-slr-x86_64"]
    assert system["system"] is True and system["build"] == pb.PROTON_CACHYOS
    assert listed["installed_bytes"] == tools[NEWEST]["size"] + tools["Proton-EM-10.0-37"]["size"]
    assert [tool["id"] for tool in listed["tools"]][-1] == "proton-cachyos-11.0-20261015-slr-x86_64"  # the system's last
    os.utime(world.tools / "Proton-EM-10.0-37", (2_000_000_000, 2_000_000_000))
    assert [tool["id"] for tool in world.proton().installed()["tools"]][:2] == ["Proton-EM-10.0-37", NEWEST]  # newest first

    page = world.proton().installed()  # the page counts builds: sizing thousands of files is the manage dialog's
    assert {tool["size"] for tool in page["tools"]} == {None} and page["installed_bytes"] is None


def test_removing_a_build_games_use_warns_first_and_then_removes_it(world, steam_library):
    world.proton().install(pb.GE_PROTON, NEWEST)
    steam_library.set_compat_tools({"730": NEWEST, "0": NEWEST})
    proton = world.proton()

    removal = proton.removal(NEWEST)
    assert removal == {"status": "success", "games": [{"appid": "730", "name": "Counter-Strike 2", "kind": "steam"}],
                       "global_default": True}
    assert proton.remove(NEWEST) == {"status": "success", "message": f"{NEWEST} is removed."}
    assert world.tree() == [".deckyscaler-partial"]
    assert proton.remove(NEWEST) == {"status": "error", "message": f"{NEWEST} is not installed."}


def test_steams_own_picks_are_not_listed_as_the_users_choice(world, steam_library):
    world.proton().install(pb.GE_PROTON, NEWEST)
    config = world.root / "config" / "config.vdf"
    config.write_text(config.read_text().replace('"priority"\t\t"250"', '"priority"\t\t"75"'))

    assert world.proton().removal(NEWEST)["games"] == []


def test_a_system_wide_build_is_never_removed(world, home):
    build_tree(home.parent / "system-compatibilitytools.d", "proton-cachyos")
    proton = world.proton()

    assert "installed for every user" in proton.removal("proton-cachyos")["message"]
    assert "installed for every user" in proton.remove("proton-cachyos")["message"]
    assert (home.parent / "system-compatibilitytools.d" / "proton-cachyos").is_dir()


def test_a_folder_that_isnt_a_build_is_listed_apart_and_removed_like_one(world, steam_library):
    world.proton().install(pb.GE_PROTON, NEWEST)
    write(world.tools / "GE-Proton9-1" / "proton", b"#!/bin/sh")  # a broken install: no compatibilitytool.vdf
    steam_library.set_compat_tools({"730": "GE-Proton9-1"})
    proton = world.proton()

    listed = proton.installed(with_sizes=True)
    assert [tool["id"] for tool in listed["tools"]] == [NEWEST]
    size = listed["others"][0]["size"]
    assert listed["others"] == [{"id": "GE-Proton9-1", "size": size}] and size > 0
    assert listed["installed_bytes"] == listed["tools"][0]["size"] + size
    assert proton.installed()["others"] == [{"id": "GE-Proton9-1", "size": None}]  # sizing is the manage dialog's

    assert proton.removal("GE-Proton9-1") == {  # Steam still names it for a game: say so
        "status": "success", "games": [{"appid": "730", "name": "Counter-Strike 2", "kind": "steam"}], "global_default": False,
    }
    assert proton.remove("GE-Proton9-1") == {"status": "success", "message": "GE-Proton9-1 is removed."}
    assert world.tree() == [".deckyscaler-partial", NEWEST]
    assert proton.remove("GE-Proton9-1") == {"status": "error", "message": "GE-Proton9-1 is not installed."}


def test_a_build_linked_in_from_elsewhere_is_listed_as_linked_and_never_removed(world, tmp_path):
    sdcard = tmp_path / "sdcard"
    build_tree(sdcard, "GE-Proton9-1")
    world.tools.mkdir(parents=True, exist_ok=True)
    os.symlink(sdcard / "GE-Proton9-1", world.tools / "GE-Proton9-1")
    proton = world.proton()

    assert {tool["id"]: tool["linked"] for tool in proton.installed()["tools"]} == {"GE-Proton9-1": True}
    refused = "GE-Proton9-1 is a link to a build kept elsewhere; it can't be removed here."
    assert proton.removal("GE-Proton9-1") == {"status": "error", "message": refused}
    assert proton.remove("GE-Proton9-1") == {"status": "error", "message": refused}
    assert (world.tools / "GE-Proton9-1").is_symlink() and (sdcard / "GE-Proton9-1" / "proton").is_file()


def test_github_failing_still_lists_what_is_installed(world, github_api):
    world.proton().install(pb.GE_PROTON, NEWEST)
    github_api.status, github_api.body = 403, b'{"message": "API rate limit exceeded"}'

    listed = world.proton().versions(pb.GE_PROTON)

    assert [row["id"] for row in listed["versions"]] == [NEWEST]
    assert listed["listing_error"].startswith("GitHub answered 403")


def test_the_plugin_offers_the_builds_and_installs_with_progress_events(plugin, world, monkeypatch):
    import main

    monkeypatch.setattr(github_releases, "download", FakeDownload(world.archive))
    events = []
    monkeypatch.setattr(main, "_decky_events", lambda name: lambda *args: events.append((name, *args)))

    assert [b["id"] for b in run(plugin.proton_build_options())] == [pb.GE_PROTON, pb.PROTON_CACHYOS, pb.PROTON_CACHYOS_V3]
    assert run(plugin.proton_install(pb.GE_PROTON, NEWEST))["status"] == "success"
    assert events[-1] == ("proton_download", NEWEST, len(world.archive), len(world.archive))
    assert [tool["id"] for tool in run(plugin.proton_installed())["tools"]] == [NEWEST]
    assert run(plugin.proton_versions(pb.GE_PROTON))["versions"][0]["state"] == "installed"
    assert run(plugin.proton_removal(NEWEST))["status"] == "success"
    assert run(plugin.proton_remove(NEWEST))["status"] == "success"


def test_steam_running_since_before_an_install_or_a_removal_needs_a_restart(world, monkeypatch):
    client = f"{world.root}/ubuntu12_32/steam -gamepadui"
    monkeypatch.setattr(processes, "started_processes", lambda: [(1.0, client)])  # started long ago
    proton = world.proton()

    assert proton.installed()["restart_needed"] is False  # no compatibilitytools.d yet
    proton.install(pb.GE_PROTON, NEWEST)
    assert proton.installed()["restart_needed"] is True

    monkeypatch.setattr(processes, "started_processes", lambda: [(time.time() + 60, client)])  # restarted since
    assert proton.installed()["restart_needed"] is False
    proton.remove(NEWEST)
    assert proton.installed()["restart_needed"] is False  # restarted "after" the removal too

    monkeypatch.setattr(processes, "started_processes", lambda: [])
    assert proton.installed()["restart_needed"] is False  # Steam isn't running


# ── moving games after an update ─────────────────────────────────────────────

OLDER = "GE-Proton11-11-x86_64"


@pytest.fixture
def updating(world, steam_library):
    """GE-Proton11-11 installed, chosen for Counter-Strike 2 and a shortcut; then 11-12 installed over GitHub."""
    build_tree(world.tools, OLDER)
    steam_library.set_compat_tools({"730": OLDER, SHORTCUT_APPID: OLDER, "1245620": "proton_experimental"})
    assert world.proton().install(pb.GE_PROTON, NEWEST)["status"] == "success"
    return world


def test_an_update_offers_to_move_the_older_builds_games_once_steam_lists_the_new_one(updating, monkeypatch):
    offers = updating.proton().installed()["moves"]

    assert offers == [{
        "build": pb.GE_PROTON,
        "target": NEWEST,
        "sources": [OLDER],
        "games": [{"appid": SHORTCUT_APPID, "name": "Heroic", "kind": "shortcut"},
                  {"appid": "730", "name": "Counter-Strike 2", "kind": "steam"}],
    }]

    client = f"{updating.root}/ubuntu12_32/steam"
    monkeypatch.setattr(processes, "started_processes", lambda: [(1.0, client)])  # Steam from before the install
    assert updating.proton().installed()["moves"] == []  # it doesn't list the new build yet: restart first


def test_the_offer_survives_the_plugin_and_shrinks_as_games_move(updating, steam_library):
    other = {"target": "proton-cachyos-11.0-20261015-slr-x86_64", "sources": ["proton-cachyos-x"], "appids": ["730"]}
    updating.moves_file.write_text(json.dumps(json.loads(updating.moves_file.read_text()) | {pb.PROTON_CACHYOS: other}))
    proton = updating.proton()

    assert proton.moved(NEWEST, ["730"]) == {"status": "success"}
    assert [g["appid"] for g in updating.proton().installed()["moves"][0]["games"]] == [SHORTCUT_APPID]
    assert json.loads(updating.moves_file.read_text())[pb.PROTON_CACHYOS] == other  # another build's move stays

    steam_library.set_compat_tools({"730": NEWEST, SHORTCUT_APPID: NEWEST})  # moved by hand meanwhile
    assert updating.proton().installed()["moves"] == []
    assert updating.proton().games(NEWEST)["games"] == [
        {"appid": SHORTCUT_APPID, "name": "Heroic", "kind": "shortcut"},
        {"appid": "730", "name": "Counter-Strike 2", "kind": "steam"},
    ]


def test_keeping_the_games_where_they_are_drops_the_offer(updating):
    assert updating.proton().keep(NEWEST) == {"status": "success"}

    assert updating.proton().installed()["moves"] == []
    assert json.loads(updating.moves_file.read_text()) == {}


def test_removing_the_new_build_drops_the_offer(updating):
    updating.proton().remove(NEWEST)

    assert updating.proton().installed()["moves"] == []


def test_an_install_nothing_moves_to_records_nothing(world, steam_library):
    build_tree(world.tools, OLDER)
    steam_library.set_compat_tools({"730": "proton_experimental"})

    world.proton().install(pb.GE_PROTON, NEWEST)

    assert not world.moves_file.exists()


def test_a_corrupt_moves_file_means_nothing_to_move(updating):
    updating.moves_file.write_text("{not json")

    assert updating.proton().installed()["moves"] == []


def test_the_games_on_a_tool_follow_steams_config_as_it_rewrites_it(world, steam_library):
    assert world.proton().games(NEWEST)["games"] == [
        {"appid": "1245620", "name": None, "kind": "unknown"},
        {"appid": SHORTCUT_APPID, "name": "Heroic", "kind": "shortcut"},
        {"appid": "730", "name": "Counter-Strike 2", "kind": "steam"},
    ]
    time.sleep(0.01)
    steam_library.set_compat_tools({"730": NEWEST})

    assert [g["appid"] for g in world.proton().games(NEWEST)["games"]] == ["730"]


def test_the_games_on_a_tool_count_the_names_it_is_known_by_as_its_rows_do(world, steam_library):
    tool_dir = build_tree(world.tools, "my-ge")
    (tool_dir / "compatibilitytool.vdf").write_text((tool_dir / "compatibilitytool.vdf").read_text().replace('"my-ge"', f'"{OLDER}"'))
    steam_library.set_compat_tools({"730": OLDER})

    assert world.proton().games("my-ge")["games"] == [{"appid": "730", "name": "Counter-Strike 2", "kind": "steam"}]
    assert world.proton().removal("my-ge")["games"] == world.proton().games("my-ge")["games"]


def test_moves_changed_at_once_keep_both_changes(world, monkeypatch):
    import threading

    from deckyscaler.application import proton_builds as owner

    moves = {
        pb.GE_PROTON: {"target": NEWEST, "sources": ["ge-proton11-11-x86_64"], "appids": ["730", "440"]},
        pb.PROTON_CACHYOS: {"target": "proton-cachyos-11.0-20261015-slr-x86_64", "sources": ["proton-cachyos-x"], "appids": ["570"]},
    }
    world.moves_file.parent.mkdir(parents=True, exist_ok=True)
    world.moves_file.write_text(json.dumps(moves))
    read, both_reading = owner.read_json, threading.Barrier(2)

    def read_together(path):
        """Each change waits for the other to read too: without one-at-a-time, both read the same old moves."""
        try:
            both_reading.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return read(path)

    monkeypatch.setattr(owner, "read_json", read_together)

    calls = [lambda: world.proton().moved(NEWEST, ["730"]), lambda: world.proton().keep("proton-cachyos-11.0-20261015-slr-x86_64")]
    threads = [threading.Thread(target=call) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert json.loads(world.moves_file.read_text()) == {
        pb.GE_PROTON: {"target": NEWEST, "sources": ["ge-proton11-11-x86_64"], "appids": ["440"]},
    }

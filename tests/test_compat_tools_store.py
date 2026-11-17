"""Proton archives and a Steam install's compatibilitytools.d on a real filesystem (integration)."""

from __future__ import annotations

import io
import os
import stat
import tarfile
import time
from pathlib import Path

import pytest

from conftest import write
from deckyscaler.domain.proton_builds import Tool
from deckyscaler.infrastructure import archive, proton
from deckyscaler.infrastructure.compat_tools_store import PARTIAL_DIRNAME, CompatToolsStore

TOOL = "GE-Proton11-12-x86_64"


def manifest(name: str) -> bytes:
    return (
        '"compatibilitytools"\n{\n  "compat_tools"\n  {\n'
        f'    "{name}" // Internal name of this tool\n    {{\n'
        f'      "install_path" "."\n      "display_name" "{name}"\n    }}\n  }}\n}}\n'
    ).encode()


def build_tree(root: Path, name: str = TOOL) -> Path:
    """A Proton build as its archive lays it out: the manifests, an executable script, a library and the default
    prefix's links pointing up into it."""
    tool = root / name
    write(tool / "compatibilitytool.vdf", manifest(name))
    write(tool / "toolmanifest.vdf", b'"manifest" { "commandline" "/proton %verb%" }')
    write(tool / "proton", b"#!/usr/bin/env python3\n").chmod(0o755)
    write(tool / "files/lib/wine/x86_64-windows/regedit.exe", b"regedit")
    write(tool / "files/share/notes.txt", b"shared").chmod(0o666)
    links = tool / "files/share/default_pfx/drive_c/windows"
    links.mkdir(parents=True)
    os.symlink("../../../../lib/wine/x86_64-windows/regedit.exe", links / "regedit.exe")
    return tool


def tarball(tmp_path: Path, mode: str = "w:gz", name: str = TOOL) -> Path:
    source = tmp_path / "source"
    build_tree(source, name)
    archive_path = tmp_path / f"{name}.tar.{mode[2:]}"
    with tarfile.open(archive_path, mode) as tar:
        tar.add(source / name, arcname=name)
    return archive_path


@pytest.mark.parametrize("mode", ["w:gz", "w:xz"])
def test_a_proton_archive_unpacks_with_its_links_and_executables(tmp_path, mode):
    out = tmp_path / "out"

    archive.extract_tar(tarball(tmp_path, mode), out)

    tool = out / TOOL
    link = tool / "files/share/default_pfx/drive_c/windows/regedit.exe"
    assert link.is_symlink() and link.read_bytes() == b"regedit"
    assert os.stat(tool / "proton").st_mode & stat.S_IXUSR
    assert not os.stat(tool / "files/share/notes.txt").st_mode & stat.S_IWOTH  # the data filter drops world-write


def evil(tmp_path: Path, member: tarfile.TarInfo) -> Path:
    path = tmp_path / "evil.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        tar.addfile(member, io.BytesIO(b"x") if member.isfile() else None)
    return path


def file_member(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = 1
    return info


def link_member(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type, info.linkname = tarfile.SYMTYPE, target
    return info


@pytest.mark.parametrize(
    "member",
    [file_member("../escape"), link_member("tool/out", "../../outside"), link_member("tool/abs", "/etc/passwd")],
    ids=["escaping-path", "escaping-link", "absolute-link"],
)
def test_an_archive_reaching_outside_is_refused(tmp_path, member):
    out = tmp_path / "out"

    with pytest.raises(RuntimeError, match="Failed to unpack evil.tar.gz"):
        archive.extract_tar(evil(tmp_path, member), out)
    assert not (tmp_path / "escape").exists()


def test_something_that_is_not_an_archive_fails_cleanly(tmp_path):
    broken = write(tmp_path / "broken.tar.xz", b"not an archive")

    with pytest.raises(RuntimeError, match="Failed to unpack broken.tar.xz"):
        archive.extract_tar(broken, tmp_path / "out")


# ── the store ────────────────────────────────────────────────────────────────


def tools_dir(tmp_path: Path) -> Path:
    return tmp_path / "Steam" / "compatibilitytools.d"


def test_every_tool_steam_would_find_is_listed_whoever_installed_it(tmp_path):
    tools, system = tools_dir(tmp_path), tmp_path / "system"
    build_tree(tools)
    write(tools / "Proton-EM-10.0-37" / "compatibilitytool.vdf", manifest("Proton-EM-10.0-37"))
    write(tools / "not-a-tool" / "readme.txt", b"")
    build_tree(tools / PARTIAL_DIRNAME / "GE-Proton11-13-x86_64")  # an install in progress is no tool yet
    write(system / "proton-cachyos" / "compatibilitytool.vdf", manifest("proton-cachyos"))

    found = CompatToolsStore(tools, system).installed()

    assert found == [
        Tool(TOOL, frozenset({TOOL.lower()})),
        Tool("Proton-EM-10.0-37", frozenset({"proton-em-10.0-37"})),
        Tool("proton-cachyos", frozenset({"proton-cachyos"}), system=True),
    ]
    assert CompatToolsStore(tmp_path / "missing").installed() == []


def test_a_tool_is_sized_by_its_files_counting_links_as_themselves(tmp_path):
    tools = tools_dir(tmp_path)
    build_tree(tools)
    store = CompatToolsStore(tools)
    files = [p for p in (tools / TOOL).rglob("*") if p.is_file() or p.is_symlink()]

    assert store.size(Tool(TOOL, frozenset())) == sum(os.lstat(p).st_size for p in files)


def test_an_unpacked_tool_moves_in_with_one_rename_and_never_over_one_already_there(tmp_path):
    tools = tools_dir(tmp_path)
    store = CompatToolsStore(tools)
    stage = store.staging(TOOL)
    archive.extract_tar(tarball(tmp_path), stage)

    assert store.top_entries(stage) == [TOOL]
    assert store.manifests(stage / TOOL) == (True, True, frozenset({TOOL.lower()}))
    store.commit(stage / TOOL, TOOL)
    assert (tools / TOOL / "proton").is_file()

    again = store.staging(TOOL)
    build_tree(again)
    with pytest.raises(FileExistsError):
        store.commit(again / TOOL, TOOL)


@pytest.mark.parametrize("folder", ["", ".", "..", PARTIAL_DIRNAME, "../Steam", "a/b"])
def test_only_a_tool_inside_compatibilitytools_d_is_removed(tmp_path, folder):
    tools = tools_dir(tmp_path)
    build_tree(tools)

    with pytest.raises(ValueError):
        CompatToolsStore(tools).remove(folder)
    assert (tools / TOOL).is_dir()


def test_a_linked_tool_is_not_followed_on_removal(tmp_path):
    tools, elsewhere = tools_dir(tmp_path), tmp_path / "elsewhere"
    build_tree(elsewhere)
    tools.mkdir(parents=True)
    os.symlink(elsewhere / TOOL, tools / TOOL)
    store = CompatToolsStore(tools)

    with pytest.raises(ValueError):
        store.remove(TOOL)
    assert (elsewhere / TOOL / "proton").is_file()

    build_tree(tools, "GE-Proton11-11-x86_64")
    store.remove("GE-Proton11-11-x86_64")
    assert not (tools / "GE-Proton11-11-x86_64").exists()


def test_clearing_an_interrupted_install_keeps_compatibilitytools_d_unchanged(tmp_path):
    tools = tools_dir(tmp_path)
    store = CompatToolsStore(tools)
    store.staging(TOOL)  # the first install ever makes the staging directory: one change
    before = store.changed_at()
    time.sleep(0.01)

    build_tree(store.staging(TOOL))
    write(store.partial_dir / "leftover.part", b"half a download")
    store.clear_partial()

    assert list(store.partial_dir.iterdir()) == []
    assert store.changed_at() == before


def test_compatibilitytools_d_changes_when_a_tool_comes_or_goes(tmp_path):
    tools = tools_dir(tmp_path)
    store = CompatToolsStore(tools)
    stage = store.staging(TOOL)
    build_tree(stage)
    before = store.changed_at()
    time.sleep(0.01)

    store.commit(stage / TOOL, TOOL)
    installed = store.changed_at()
    time.sleep(0.01)
    store.remove(TOOL)

    assert before < installed < store.changed_at()
    assert CompatToolsStore(tmp_path / "missing").changed_at() is None


def test_free_space_is_measured_where_builds_go_even_before_compatibilitytools_d_exists(tmp_path):
    assert CompatToolsStore(tmp_path / "Steam" / "compatibilitytools.d").free_bytes() > 0


# ── the tools users chose ────────────────────────────────────────────────────


def test_the_tools_users_chose_come_from_the_installs_config(steam_library):
    steam_library.set_compat_tools({"730": TOOL, "0": "proton_experimental"})

    chosen = proton.forced_mappings(steam_library.root)

    assert chosen.games == {"730": TOOL} and chosen.global_tool == "proton_experimental"
    assert proton.forced_mappings(steam_library.root.parent).games == {}

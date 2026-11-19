"""Where the user's libraries live on the device, which of them go into games, and reading what the user picked: a
zip's members, a DLL's file version."""

from __future__ import annotations

import struct
import zipfile

import pytest

from deckyscaler.domain import user_libraries as ul
from deckyscaler.domain.library_choice import Choices
from deckyscaler.infrastructure import archive, dll_version
from deckyscaler.infrastructure.user_library_store import LibraryChoicesStore, UserLibraryStore

FG, UP = ul.FRAME_GENERATION, ul.UPSCALER


# ── zips ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def addon(tmp_path):
    path = tmp_path / "addon.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ANR/dlssg/nvngx_dlssg.dll", b"dll")
        zf.writestr("ANR/dlssg/nr_fg.ini", b"ini")
        zf.writestr("install.sh", b"#!/bin/sh")
        zf.writestr("ANR/empty/", b"")
        zf.writestr("../escape.dll", b"out")
    return path


def test_a_zips_members_are_its_files(addon):
    assert archive.zip_members(addon) == {"ANR/dlssg/nvngx_dlssg.dll", "ANR/dlssg/nr_fg.ini", "install.sh", "../escape.dll"}


def test_only_the_named_members_are_unpacked_and_none_lands_outside(addon, tmp_path):
    out = tmp_path / "out"

    archive.extract_zip(addon, ("ANR/dlssg/nvngx_dlssg.dll", "../escape.dll"), out, 1_000)

    assert (out / "ANR" / "dlssg" / "nvngx_dlssg.dll").read_bytes() == b"dll"
    assert not (out / "install.sh").exists() and not (tmp_path / "escape.dll").exists()
    assert (out / "escape.dll").read_bytes() == b"out"


def test_members_unpacking_past_the_limit_are_refused(addon, tmp_path):
    with pytest.raises(RuntimeError, match="more than"):
        archive.extract_zip(addon, ("ANR/dlssg/nvngx_dlssg.dll", "ANR/dlssg/nr_fg.ini"), tmp_path / "out", 5)
    assert not (tmp_path / "out").exists()


def test_what_isnt_a_zip_says_so(tmp_path):
    (tmp_path / "x.zip").write_bytes(b"not a zip")

    with pytest.raises(RuntimeError):
        archive.zip_members(tmp_path / "x.zip")
    with pytest.raises(RuntimeError):
        archive.extract_zip(tmp_path / "x.zip", ("a",), tmp_path / "out", 10)


# ── a DLL's file version ─────────────────────────────────────────────────────


def _pe(resources: bytes, outside: bytes = b"") -> bytes:
    """A PE file with one section, .rsrc, holding `resources`; `outside` sits between the headers and it."""
    pe_offset = 0x40
    dos = bytearray(pe_offset)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, pe_offset)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 0, 0)
    data_offset = pe_offset + len(coff) + 40 + len(outside)
    section = b".rsrc\0\0\0" + struct.pack("<IIII", len(resources), 0x1000, len(resources), data_offset) + bytes(16)
    return bytes(dos) + coff + section + outside + resources


def _fixed_info(structure: int, high: int, low: int) -> bytes:
    return b"\0" * 8 + struct.pack("<IIII", 0xFEEF04BD, structure, high, low)


def test_a_dlls_file_version_comes_from_its_resources(tmp_path):
    path = tmp_path / "libxess.dll"
    path.write_bytes(_pe(_fixed_info(0x00010000, (2 << 16) | 0, (2 << 16) | 68)))

    assert dll_version.file_version(path) == "2.0.2.68"


@pytest.mark.parametrize(
    "data",
    [
        _pe(b"\0" * 32, outside=_fixed_info(0x00010000, 1, 1)),  # the signature by chance outside the resources
        _pe(_fixed_info(0x7C81E575, 1, 1)),  # not a version structure
        _pe(b"\0" * 32),
        b"XX" + _pe(_fixed_info(0x00010000, 1, 1))[2:],  # a version where no DLL starts
        b"MZ" + b"\0" * 10,
        b"not a dll",
    ],
)
def test_no_version_is_read_where_there_is_none(tmp_path, data):
    path = tmp_path / "x.dll"
    path.write_bytes(data)

    assert dll_version.file_version(path) is None


def test_a_missing_file_has_no_version(tmp_path):
    assert dll_version.file_version(tmp_path / "gone.dll") is None


# ── the store ────────────────────────────────────────────────────────────────


def _library(library_id: str) -> ul.Library:
    contents = ul.recognize(frozenset({"libxess.dll"}))
    return ul.Library(library_id, "libxess.dll", "2.0.2.68", ul.YOUR_FILE, None, contents.providers, contents.dlls, contents.files, (), "t")


def test_a_committed_library_is_installed_with_its_files_until_removed(tmp_path):
    store = UserLibraryStore(tmp_path / "libraries")
    stage = store.staging("x")
    (stage / ul.FILES_DIRNAME).mkdir()
    (stage / ul.FILES_DIRNAME / "libxess.dll").write_bytes(b"12345")

    store.commit(stage, _library("x"))

    assert store.installed() == [_library("x")]
    assert (store.files_dir("x") / "libxess.dll").read_bytes() == b"12345"
    assert store.size("x") > 5
    store.remove("x")
    assert store.installed() == []


def test_a_library_missing_a_file_isnt_on_the_device_and_a_new_one_of_its_id_replaces_it(tmp_path):
    store = UserLibraryStore(tmp_path / "libraries")
    stage = store.staging("x")
    (stage / ul.FILES_DIRNAME).mkdir()
    (stage / ul.FILES_DIRNAME / "libxess.dll").write_bytes(b"12345")
    store.commit(stage, _library("x"))
    (store.files_dir("x") / "libxess.dll").unlink()

    assert store.installed() == []
    stage = store.staging("x")
    (stage / ul.FILES_DIRNAME).mkdir()
    (stage / ul.FILES_DIRNAME / "libxess.dll").write_bytes(b"678")
    store.commit(stage, _library("x"))
    assert store.installed() == [_library("x")]
    assert (store.files_dir("x") / "libxess.dll").read_bytes() == b"678"


def test_only_a_directory_named_as_its_entry_is_a_library(tmp_path):
    store = UserLibraryStore(tmp_path / "libraries")
    stage = store.staging("y")
    store.commit_entry(stage, "y", ul.entry_json(_library("other")))
    (store.items_dir / "junk").mkdir()

    assert store.installed() == []


def test_what_isnt_a_whole_library_is_damaged_and_named_by_what_its_entry_still_says(tmp_path):
    store = UserLibraryStore(tmp_path / "libraries")
    for name in ("whole", "missing"):
        stage = store.staging(name)
        (stage / ul.FILES_DIRNAME).mkdir()
        (stage / ul.FILES_DIRNAME / "libxess.dll").write_bytes(b"1")
        store.commit(stage, _library(name))
    (store.files_dir("missing") / "libxess.dll").unlink()
    store.commit_entry(store.staging("moved"), "moved", ul.entry_json(_library("other")))
    (store.items_dir / "unreadable").mkdir()
    (store.items_dir / "unreadable" / ul.ENTRY_FILENAME).write_text("{not json")
    (store.items_dir / "no-entry" / ul.FILES_DIRNAME).mkdir(parents=True)  # an interrupted removal took its entry

    assert store.installed() == [_library("whole")]
    assert store.damaged() == [
        ("missing", _library("missing")), ("moved", _library("other")), ("no-entry", None), ("unreadable", None),
    ]
    assert store.listed() == {"whole", "missing", "moved", "no-entry", "unreadable"}


def test_the_choices_are_kept_in_one_file(tmp_path):
    store = LibraryChoicesStore(tmp_path / "settings" / "libraries.json")

    assert store.read() == Choices({}, {})
    store.write(Choices({UP: "xess"}, {"620": {FG: "none"}}))
    assert store.read() == Choices({UP: "xess"}, {"620": {FG: "none"}})

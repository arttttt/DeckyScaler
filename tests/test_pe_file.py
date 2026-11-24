"""Reading sections of a DLL without the rest of it."""

from __future__ import annotations

import pytest
from conftest import pe_dll

from deckyscaler.infrastructure import pe_file


def test_only_the_named_sections_are_read_each_with_its_own_bytes(tmp_path):
    path = tmp_path / "upscaler.dll"
    path.write_bytes(pe_dll({".text": b"code" * 8, ".data": b"rtti names", ".rsrc": b"resources"}, outside=b"\xcc" * 7))

    assert pe_file.sections(path, frozenset({".data", ".rsrc"})) == {".data": b"rtti names", ".rsrc": b"resources"}
    assert pe_file.sections(path, frozenset({".data"})) == {".data": b"rtti names"}


def test_a_section_the_file_doesnt_have_is_left_out(tmp_path):
    path = tmp_path / "x.dll"
    path.write_bytes(pe_dll({".rsrc": b"resources"}))

    assert pe_file.sections(path, frozenset({".data", ".rsrc"})) == {".rsrc": b"resources"}


@pytest.mark.parametrize(
    "data",
    [
        b"XX" + pe_dll({".data": b"rtti"})[2:],  # no DOS header
        pe_dll({".data": b"rtti"})[:0x40] + b"NE\0\0" + pe_dll({".data": b"rtti"})[0x44:],  # no PE signature
        b"MZ" + b"\0" * 10,
        b"",
    ],
    ids=["not-mz", "not-pe", "truncated", "empty"],
)
def test_a_file_that_isnt_a_pe_file_has_no_sections(tmp_path, data):
    path = tmp_path / "x.dll"
    path.write_bytes(data)

    assert pe_file.sections(path, frozenset({".data"})) == {}


def test_a_missing_file_has_no_sections(tmp_path):
    assert pe_file.sections(tmp_path / "gone.dll", frozenset({".data"})) == {}

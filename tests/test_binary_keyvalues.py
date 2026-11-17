"""Valve's binary KeyValues format and naming apps from it (unit)."""

from __future__ import annotations

import struct

import pytest

from deckyscaler.domain import binary_keyvalues as bkv
from deckyscaler.domain import steam


def encode(tree: dict) -> bytes:
    """What Steam writes for a tree: str → STRING, int → INT32, float → FLOAT32, dict → MAP."""
    out = b""
    for key, value in tree.items():
        name = key.encode() + b"\0"
        if isinstance(value, dict):
            out += bytes([bkv.MAP]) + name + encode(value)
        elif isinstance(value, str):
            out += bytes([bkv.STRING]) + name + value.encode() + b"\0"
        elif isinstance(value, float):
            out += bytes([bkv.FLOAT32]) + name + struct.pack("<f", value)
        else:
            out += bytes([bkv.INT32]) + name + struct.pack("<i", value)
    return out + bytes([bkv.END])


SHORTCUTS = {
    "shortcuts": {
        "0": {"appid": -1878337519, "AppName": "Heroic Games Launcher", "Exe": '"/usr/bin/heroic"', "LastPlayTime": 0,
              "tags": {"0": "favorite"}},
        "1": {"appid": 123456, "appname": "Low Id Shortcut", "OpenVR": 0},
        "2": {"appid": 7, "AppName": ""},
        "3": "junk",
    }
}


def test_a_shortcuts_file_reads_back_as_its_tree_with_keys_lowercased():
    tree = bkv.parse(encode(SHORTCUTS))

    first = tree["shortcuts"]["0"]
    assert first["appid"] == -1878337519 and first["appname"] == "Heroic Games Launcher"
    assert first["tags"] == {"0": "favorite"}
    assert bkv.parse(encode({"x": 1.5}))["x"] == 1.5
    assert bkv.parse(bytes([bkv.UINT64]) + b"big\0" + struct.pack("<Q", 2**40) + bytes([bkv.END]))["big"] == 2**40


def test_the_outermost_end_may_be_missing():
    assert bkv.parse(encode({"a": "b"})[:-1]) == {"a": "b"}


@pytest.mark.parametrize(
    "data",
    [
        bytes([bkv.MAP]) + b"shortcuts\0" + bytes([bkv.STRING]) + b"k\0value",  # unterminated string
        bytes([bkv.MAP]) + b"a\0" + bytes([bkv.MAP]) + b"b\0",  # maps that never end
        bytes([bkv.INT32]) + b"n\0" + b"\x01\x02",  # a number cut short
        bytes([0x05]) + b"wide\0" + b"\0\0",  # a type Steam doesn't write there
    ],
    ids=["unterminated", "unended", "short-number", "unknown-type"],
)
def test_anything_else_is_refused(data):
    with pytest.raises(ValueError):
        bkv.parse(data)


def test_shortcuts_are_named_by_the_unsigned_appid_steams_other_files_use():
    names = steam.shortcut_names(bkv.parse(encode(SHORTCUTS)))

    assert names == {str(-1878337519 + 2**32): "Heroic Games Launcher", "123456": "Low Id Shortcut"}
    assert steam.shortcut_names({}) == {}


def test_an_app_is_named_by_its_manifest_else_its_shortcut_else_not_at_all():
    named = steam.name_apps(["730", "2416629777", "1245620"], {"730": "Counter-Strike 2"}, {"2416629777": "Heroic"})

    assert named == [
        steam.NamedApp("730", "Counter-Strike 2", steam.STEAM_APP),
        steam.NamedApp("2416629777", "Heroic", steam.SHORTCUT),
        steam.NamedApp("1245620", None, steam.UNKNOWN_APP),
    ]

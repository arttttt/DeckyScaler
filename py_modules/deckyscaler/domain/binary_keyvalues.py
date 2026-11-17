"""Valve's binary KeyValues format, as Steam writes shortcuts.vdf: each entry is a type byte, a NUL-terminated key
and a value; a map's entries end with END. Keys are lowercased, as in the text format."""

from __future__ import annotations

import struct

BinaryKeyValues = dict[str, "str | int | float | BinaryKeyValues"]

MAP, STRING, INT32, FLOAT32, UINT64, END = 0x00, 0x01, 0x02, 0x03, 0x07, 0x08
_NUMBERS = {INT32: "<i", FLOAT32: "<f", UINT64: "<Q"}


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def byte(self) -> int:
        if self.at >= len(self.data):
            raise ValueError("binary KeyValues end before their maps do")
        self.at += 1
        return self.data[self.at - 1]

    def cstring(self) -> str:
        end = self.data.find(b"\0", self.at)
        if end == -1:
            raise ValueError("binary KeyValues hold an unterminated string")
        text = self.data[self.at : end].decode("utf-8", errors="replace")
        self.at = end + 1
        return text

    def number(self, kind: int) -> int | float:
        layout = _NUMBERS[kind]
        size = struct.calcsize(layout)
        if self.at + size > len(self.data):
            raise ValueError("binary KeyValues end inside a number")
        (value,) = struct.unpack_from(layout, self.data, self.at)
        self.at += size
        return value


def _map(reader: _Reader) -> BinaryKeyValues:
    entries: BinaryKeyValues = {}
    while (kind := reader.byte()) != END:
        key = reader.cstring().lower()
        if kind == MAP:
            entries[key] = _map(reader)
        elif kind == STRING:
            entries[key] = reader.cstring()
        elif kind in _NUMBERS:
            entries[key] = reader.number(kind)
        else:
            raise ValueError(f"binary KeyValues hold a value of unknown type {kind}")
    return entries


def parse(data: bytes) -> BinaryKeyValues:
    """The nested key/value tree; raises ValueError for anything that isn't binary KeyValues."""
    reader = _Reader(data + bytes([END]))  # the outermost map's END is optional in files Steam writes
    return _map(reader)

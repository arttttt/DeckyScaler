"""A DLL's file version, as Windows shows it: from the VS_FIXEDFILEINFO in its resources."""

from __future__ import annotations

import struct
from pathlib import Path

_SIGNATURE = struct.pack("<I", 0xFEEF04BD)
_STRUCTURE_VERSION = 0x00010000


def file_version(path: Path) -> str | None:
    """The DLL's file version ("2.0.2.68"), or None when it records none or isn't a DLL. Only the resource section
    is searched: the signature's bytes turn up by chance in code (ANR's DLL has them outside its resources)."""
    try:
        return _version(path.read_bytes())
    except OSError:
        return None


def _version(data: bytes) -> str | None:
    try:
        if data[:2] != b"MZ":
            return None
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe : pe + 4] != b"PE\0\0":
            return None
        sections, = struct.unpack_from("<H", data, pe + 6)
        optional_size, = struct.unpack_from("<H", data, pe + 20)
        table = pe + 24 + optional_size
        for index in range(sections):
            entry = table + 40 * index
            if data[entry : entry + 8].rstrip(b"\0") != b".rsrc":
                continue
            size, offset = struct.unpack_from("<II", data, entry + 16)
            found = data.find(_SIGNATURE, offset, offset + size)
            if found < 0:
                return None
            structure, high, low = struct.unpack_from("<III", data, found + 4)
            if structure != _STRUCTURE_VERSION:
                return None
            return f"{high >> 16}.{high & 0xFFFF}.{low >> 16}.{low & 0xFFFF}"
    except struct.error:
        return None
    return None

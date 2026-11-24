"""A DLL's file version, as Windows shows it: from the VS_FIXEDFILEINFO in its resources."""

from __future__ import annotations

import struct
from pathlib import Path

from deckyscaler.infrastructure import pe_file

_RESOURCES = ".rsrc"
_SIGNATURE = struct.pack("<I", 0xFEEF04BD)
_STRUCTURE_VERSION = 0x00010000


def file_version(path: Path) -> str | None:
    """The DLL's file version ("2.0.2.68"), or None when it records none or isn't a DLL. Only the resource section
    is searched: the signature's bytes turn up by chance in code (ANR's DLL has them outside its resources)."""
    resources = pe_file.sections(path, frozenset({_RESOURCES})).get(_RESOURCES)
    return None if resources is None else _version(resources)


def _version(resources: bytes) -> str | None:
    found = resources.find(_SIGNATURE)
    if found < 0:
        return None
    try:
        structure, high, low = struct.unpack_from("<III", resources, found + 4)
    except struct.error:
        return None
    if structure != _STRUCTURE_VERSION:
        return None
    return f"{high >> 16}.{high & 0xFFFF}.{low >> 16}.{low & 0xFFFF}"

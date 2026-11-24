"""Sections of a Windows PE file (a DLL), read without the rest of it: AMD's upscaler DLL runs to tens of megabytes,
while what the plugin reads of a DLL sits in a section of a few hundred kilobytes at most."""

from __future__ import annotations

import struct
from pathlib import Path

_SECTION_HEADER = 40


def sections(path: Path, names: frozenset[str]) -> dict[str, bytes]:
    """The raw bytes of the named sections, by name. A section the file doesn't have is left out, and so is every one
    when the file isn't a PE file or can't be read."""
    try:
        with path.open("rb") as file:
            dos = file.read(0x40)
            if len(dos) < 0x40 or dos[:2] != b"MZ":
                return {}
            (pe,) = struct.unpack_from("<I", dos, 0x3C)
            file.seek(pe)
            coff = file.read(24)
            if len(coff) < 24 or coff[:4] != b"PE\0\0":
                return {}
            (count,) = struct.unpack_from("<H", coff, 6)
            (optional_size,) = struct.unpack_from("<H", coff, 20)
            file.seek(pe + 24 + optional_size)
            table = file.read(_SECTION_HEADER * count)
            found: dict[str, bytes] = {}
            for at in range(0, len(table) - _SECTION_HEADER + 1, _SECTION_HEADER):
                name = table[at : at + 8].rstrip(b"\0").decode("ascii", "replace")
                if name not in names:
                    continue
                size, offset = struct.unpack_from("<II", table, at + 16)  # SizeOfRawData, PointerToRawData
                file.seek(offset)
                found[name] = file.read(size)
            return found
    except (OSError, struct.error):
        return {}

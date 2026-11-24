"""Reading Steam's Proton tools from disk: which one the user set for each game (config.vdf), and where
distributions install them for every user."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from deckyscaler.domain import compat_tools, keyvalues
from deckyscaler.infrastructure import files

SYSTEM_TOOLS = Path("/usr/share/steam/compatibilitytools.d")
"""Where distributions install compatibility tools for every user, next to each Steam root's own."""

T = TypeVar("T")
_cache: dict[tuple[str, Path], tuple[int, object]] = {}


def _cached(kind: str, path: Path, compute: Callable[[], T]) -> T:
    """`compute()`'s result for `path`, kept while the file's mtime stays: config.vdf runs to megabytes, read on every
    look at the Proton builds otherwise."""
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return compute()
    hit = _cache.get((kind, path))
    if hit is not None and hit[0] == stamp:
        return hit[1]  # type: ignore[return-value]
    value = compute()
    _cache[(kind, path)] = (stamp, value)
    return value


def forced_mappings(steam_root: Path) -> compat_tools.ForcedMappings:
    """The tools the user chose in one Steam install, from its config.vdf."""
    config = steam_root / "config" / "config.vdf"
    if not config.is_file():
        return compat_tools.ForcedMappings({}, None)
    return compat_tools.forced_mappings(_cached("config", config, lambda: keyvalues.parse(files.read_text_or_empty(config))))

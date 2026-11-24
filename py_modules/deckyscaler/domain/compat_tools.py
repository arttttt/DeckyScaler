"""Steam's compatibility tools as its files describe them: which tool runs a game, which ones the user chose,
and what a tool's manifest declares.

Steam compares tool names case-insensitively; the names here keep the case Steam wrote them in.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import keyvalues

GLOBAL_MAPPING = "0"
"""CompatToolMapping's entry for the tool the user chose for every game."""

USER_CHOICE_PRIORITY = 250
"""The priority Steam gives a tool the user picked in a game's Properties; Steam's own automatic picks rank lower
(decky-wine-cellar steam_util.rs, USER_FORCED_PRIORITY)."""


def _mapping(config: keyvalues.KeyValues) -> dict:
    found = keyvalues.find(config, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping")
    return found if isinstance(found, dict) else {}


def _name(entry: object) -> str | None:
    name = entry.get("name") if isinstance(entry, dict) else None
    return name if isinstance(name, str) and name else None


def compat_tool(config: keyvalues.KeyValues, appid: str) -> str | None:
    """The compatibility tool Steam runs a game with, by internal name (GE-Proton11-11, proton_experimental):
    the game's own choice, else the one chosen for every game. None means Steam's default, which no file names."""
    mapping = _mapping(config)
    for key in (str(appid), GLOBAL_MAPPING):
        name = _name(mapping.get(key))
        if name:
            return name
    return None


@dataclass(frozen=True)
class ForcedMappings:
    """The tools the user chose: per game, and the one for every game."""

    games: dict[str, str]
    """appid → the tool's internal name, for the games whose tool the user picked in their Properties."""
    global_tool: str | None
    """The tool chosen for every game, if any."""


def _user_choice(entry: object) -> bool:
    priority = entry.get("priority") if isinstance(entry, dict) else None
    try:
        return int(str(priority)) >= USER_CHOICE_PRIORITY
    except ValueError:
        return False


def forced_mappings(config: keyvalues.KeyValues) -> ForcedMappings:
    """Which tool the user chose for which game. Steam's own picks (a lower priority) are not the user's, and
    the entry for every game is kept apart from the games."""
    mapping = _mapping(config)
    games = {
        appid: name
        for appid, entry in mapping.items()
        if appid != GLOBAL_MAPPING and _user_choice(entry) and (name := _name(entry))
    }
    return ForcedMappings(games, _name(mapping.get(GLOBAL_MAPPING)))


def custom_tools(manifest: keyvalues.KeyValues) -> dict[str, str]:
    """The tools a compatibilitytool.vdf declares: internal name, lowercased as Steam compares it → install_path
    (relative to the file)."""
    tools = keyvalues.find(manifest, "compatibilitytools", "compat_tools")
    if not isinstance(tools, dict):
        return {}
    return {
        name: str(entry.get("install_path") or ".")
        for name, entry in tools.items()
        if isinstance(entry, dict)
    }


def launch_target(toolmanifest: keyvalues.KeyValues) -> str | None:
    """The file a tool's toolmanifest.vdf has Steam run, relative to the tool's install path: the first word of its
    commandline (else of commandline_waitforexitandrun), without the leading "/". Every Proton names `proton`; other
    tools their own script. None when it names none."""
    manifest = keyvalues.find(toolmanifest, "manifest")
    if not isinstance(manifest, dict):
        return None
    for key in ("commandline", "commandline_waitforexitandrun"):
        line = manifest.get(key)
        if isinstance(line, str) and line.split():
            return line.split()[0].lstrip("/") or None
    return None

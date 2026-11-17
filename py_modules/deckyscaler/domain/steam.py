"""Reading Steam's library metadata: where libraries live and which games they hold."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FLATPAK_APP = Path(".var") / "app" / "com.valvesoftware.Steam"
_FLATPAK_HOME = _FLATPAK_APP / "home"

# Steam installs these as apps, but they are tools, not games.
_TOOL_NAME_MARKERS = ("Proton", "Steam Linux Runtime")


@dataclass(frozen=True)
class AppManifest:
    appid: str
    name: str
    installdir: str


def steam_root_candidates(home: Path) -> list[Path]:
    """Where a Steam install may live: native layouts first, then the Flatpak sandbox (its data/Steam, which
    flathub's steam_wrapper links to the sandbox's .local/share, then the links Steam makes in the sandbox
    home). Several of them can be one install seen through links."""
    return [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / _FLATPAK_APP / "data" / "Steam",
        home / _FLATPAK_HOME / ".local" / "share" / "Steam",
        home / _FLATPAK_HOME / ".steam" / "steam",
    ]


_CLIENT = re.compile(r"(?:^|\s)(/\S+)/ubuntu12_(?:32|64)/steam(?=\s|$)")

NO_STEAM = "no-steam"
SEVERAL_STEAMS = "several-steams"


def client_root(command_line: str) -> Path | None:
    """The Steam install a process runs from, when it is the Steam client itself (<root>/ubuntu12_32/steam,
    or ubuntu12_64); None for any other process, steamwebhelper and the game launch wrappers included."""
    match = _CLIENT.search(command_line)
    return Path(match.group(1)) if match else None


@dataclass(frozen=True)
class ActiveRoot:
    """The Steam install the plugin works with, or why there is none to pick."""

    root: Path | None
    problem: str | None = None


def active_root(configured: list[Path], running: list[Path]) -> ActiveRoot:
    """Which Steam install to use: the one running now, else the only one that has ever run (has a
    config.vdf). With none, NO_STEAM; with several and none running, SEVERAL_STEAMS — starting Steam tells."""
    for root in running:
        if root in configured:
            return ActiveRoot(root)
    if len(configured) == 1:
        return ActiveRoot(configured[0])
    return ActiveRoot(None, SEVERAL_STEAMS if configured else NO_STEAM)


def _quoted_value(line: str, key: str) -> str:
    return line.split(f'"{key}"', 1)[1].strip().strip('"')


def parse_library_folders(text: str) -> list[str]:
    """Library paths listed in a libraryfolders.vdf."""
    return [
        _quoted_value(line, "path").replace("\\\\", "/")
        for line in text.splitlines()
        if '"path"' in line
    ]


def parse_app_manifest(text: str) -> AppManifest:
    """The fields of an appmanifest_*.acf the plugin uses; missing ones are empty."""
    fields = {"appid": "", "name": "", "installdir": ""}
    for line in text.splitlines():
        for key in fields:
            if f'"{key}"' in line:
                fields[key] = _quoted_value(line, key)
                break
    return AppManifest(**fields)


def is_game(manifest: AppManifest) -> bool:
    """A manifest describes a game the plugin can patch: complete, and not a Steam tool."""
    if not manifest.appid or not manifest.name:
        return False
    return not any(marker in manifest.name for marker in _TOOL_NAME_MARKERS)


# ── Naming an app ─────────────────────────────────────────────────────────────

STEAM_APP = "steam"
SHORTCUT = "shortcut"
UNKNOWN_APP = "unknown"

_UINT32 = 1 << 32


def shortcut_names(shortcuts: dict) -> dict[str, str]:
    """appid → name of the non-Steam games in a parsed shortcuts.vdf. The file keeps an appid as a signed 32-bit
    number; Steam's other files (config.vdf's CompatToolMapping) spell it unsigned, as here."""
    entries = shortcuts.get("shortcuts")
    names: dict[str, str] = {}
    for entry in entries.values() if isinstance(entries, dict) else []:
        appid, name = (entry.get("appid"), entry.get("appname")) if isinstance(entry, dict) else (None, None)
        if isinstance(appid, int) and isinstance(name, str) and name:
            names[str(appid % _UINT32)] = name
    return names


@dataclass(frozen=True)
class NamedApp:
    appid: str
    name: str | None
    kind: str
    """STEAM_APP (installed), SHORTCUT (a non-Steam game) or UNKNOWN_APP (no longer installed, or unknown here)."""


def name_apps(appids: list[str], installed: dict[str, str], shortcuts: dict[str, str]) -> list[NamedApp]:
    """Each app by the name Steam shows it under, where the device still has one."""
    named = []
    for appid in appids:
        if appid in installed:
            named.append(NamedApp(appid, installed[appid], STEAM_APP))
        elif appid in shortcuts:
            named.append(NamedApp(appid, shortcuts[appid], SHORTCUT))
        else:
            named.append(NamedApp(appid, None, UNKNOWN_APP))
    return named

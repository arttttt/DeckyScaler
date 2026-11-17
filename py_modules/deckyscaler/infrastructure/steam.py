"""Finding Steam libraries, installed games and their executables on disk."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from deckyscaler.domain import binary_keyvalues, steam
from deckyscaler.infrastructure import processes

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstalledGame:
    appid: str
    name: str
    library_path: Path
    install_path: Path


def steam_roots(home: Path) -> list[Path]:
    """Every Steam install on the device once, by its real path: ~/.steam/steam and ~/.steam/root are links
    to ~/.local/share/Steam, Flatpak's data/Steam to its sandbox's .local/share/Steam."""
    roots: list[Path] = []
    for candidate in steam.steam_root_candidates(home):
        if candidate.is_dir() and (real := candidate.resolve()) not in roots:
            roots.append(real)
    return roots


def running_clients() -> list[tuple[Path, float]]:
    """The running Steam clients: the install each runs from (by its real path) and when it started."""
    return [(root.resolve(), started) for started, line in processes.started_processes() if (root := steam.client_root(line))]


def active_root(home: Path, clients: list[tuple[Path, float]]) -> steam.ActiveRoot:
    """The Steam install the plugin works with: the running client's, else the only one that has run."""
    roots = steam_roots(home)
    configured = [root for root in roots if (root / "config" / "config.vdf").is_file()]
    return steam.active_root(configured, [root for root, _started in clients])


def library_paths(home: Path) -> list[Path]:
    """Every Steam library: each existing Steam root plus the folders its libraryfolders.vdf lists."""
    paths: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if str(path) not in seen:
            paths.append(path)
            seen.add(str(path))

    for steam_root in steam_roots(home):
        add(steam_root)
        library_file = steam_root / "steamapps" / "libraryfolders.vdf"
        if not library_file.exists():
            continue
        try:
            text = library_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.error(f"[DeckyScaler] failed to parse libraryfolders: {library_file}: {exc}")
            continue
        for path in steam.parse_library_folders(text):
            add(Path(path))
    return paths


def installed_games(home: Path, appid: str | None = None) -> list[InstalledGame]:
    """Installed games across all libraries, sorted by name; one entry per appid (the last found wins)."""
    by_appid: dict[str, InstalledGame] = {}
    for library_path in library_paths(home):
        steamapps = library_path / "steamapps"
        if not steamapps.exists():
            continue
        for manifest_file in steamapps.glob("appmanifest_*.acf"):
            try:
                manifest = steam.parse_app_manifest(manifest_file.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                log.error(f"[DeckyScaler] skipping manifest {manifest_file}: {exc}")
                continue
            if not steam.is_game(manifest):
                continue
            if appid is not None and manifest.appid != str(appid):
                continue
            install_path = steamapps / "common" / manifest.installdir if manifest.installdir else Path()
            by_appid[manifest.appid] = InstalledGame(manifest.appid, manifest.name, library_path, install_path)
    return sorted(by_appid.values(), key=lambda game: game.name.lower())


def app_names(home: Path) -> dict[str, str]:
    """appid → name of every app installed in any library, games and Steam's tools alike."""
    names: dict[str, str] = {}
    for library_path in library_paths(home):
        for manifest_file in (library_path / "steamapps").glob("appmanifest_*.acf"):
            try:
                manifest = steam.parse_app_manifest(manifest_file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if manifest.appid and manifest.name:
                names[manifest.appid] = manifest.name
    return names


def shortcut_names(steam_root: Path) -> dict[str, str]:
    """appid → name of the non-Steam games every user of a Steam install added; a file that can't be read is
    skipped."""
    names: dict[str, str] = {}
    for shortcuts in sorted(steam_root.glob("userdata/*/config/shortcuts.vdf")):
        try:
            names.update(steam.shortcut_names(binary_keyvalues.parse(shortcuts.read_bytes())))
        except (OSError, ValueError) as exc:
            log.warning(f"[DeckyScaler] skipping {shortcuts}: {exc}")
    return names


def find_game(home: Path, appid: str) -> InstalledGame | None:
    matches = installed_games(home, appid)
    return matches[0] if matches else None


def executables(install_root: Path) -> list[Path]:
    """Every .exe file under a game's install directory."""
    if not install_root.exists():
        return []
    try:
        return [exe for exe in install_root.rglob("*.exe") if exe.is_file()]
    except OSError as exc:
        log.error(f"[DeckyScaler] exe scan failed for {install_root}: {exc}")
        return []

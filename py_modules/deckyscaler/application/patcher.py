"""Patching and unpatching games: the one owner of the patch lifecycle.

Manual directory patching and Steam AppID patching are two entry points into
the same plan-and-execute path. Results are the plain dicts the frontend reads.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from deckyscaler.domain import (
    bundle,
    exe_target,
    fsr4,
    ini,
    ini_schema,
    launch_options,
    library,
    library_choice,
    library_placement,
    marker,
    patch_record,
    settings_layers,
    steam,
    stock_reset,
    user_libraries,
    version_placement,
)
from deckyscaler.domain import patch_plan as plan
from deckyscaler.infrastructure import drives, files, game_directory, processes, proton
from deckyscaler.infrastructure.library_store import LibraryStore
from deckyscaler.infrastructure.patch_index import PatchIndex
from deckyscaler.infrastructure.settings_store import SettingsStore
from deckyscaler.infrastructure.user_library_store import LibraryChoicesStore, UserLibraryStore
from deckyscaler.infrastructure import steam as steam_library

log = logging.getLogger(__name__)

NO_VERSION = "No OptiScaler version is downloaded. Download one under Open DeckyScaler → OptiScaler first."
BUNDLE_IS_NOT_A_GAME = "The target directory is in DeckyScaler's own folder (~/deckyscaler), not a game. Aborting to prevent accidental deletion."
PATCHED_BY_DECKY_FRAMEGEN = (
    "This game was patched by Decky Framegen. Unpatch it first: the plugin shows what that removes."
)
DAMAGED_RECORD = (
    "DeckyScaler's record of this patch is damaged, so it can't be undone by it. Patch the game again to repair it."
)
LAUNCH_OPTIONS_UNKNOWN = (
    "Steam didn't say what this game's launch options are, so Unpatch couldn't put them back. "
    "Nothing was changed; try patching again."
)
RECORD = "record"
"""How a directory is unpatched: by its patch record, exactly as the patch recorded it."""
RESET = "reset"
"""How a directory Decky Framegen patched is unpatched: by what it placed, after the user confirms."""
REPAIR = "repair"
"""A directory whose record is damaged isn't unpatched: patching it again repairs the record first."""


def _marker_of(directory: Path) -> Path:
    """The file a directory's patch is recorded in: the plugin's marker, or the original's name when an early build
    recorded its patch there; where the plugin's marker goes when there is neither."""
    upstream = directory / bundle.UPSTREAM_MARKER_FILENAME
    if not (directory / bundle.MARKER_FILENAME).is_file() and upstream.is_file():
        if patch_record.state_of(upstream.name, files.read_json(upstream)) != patch_record.UPSTREAM:
            return upstream
    return directory / bundle.MARKER_FILENAME


def _patched_by_upstream(directory: Path) -> bool:
    """Whether the original Decky Framegen patched a directory (and this plugin didn't since): its patch has
    no record, so it is reset after the user confirms, never patched over or unpatched by a record."""
    upstream = directory / bundle.UPSTREAM_MARKER_FILENAME
    return upstream.is_file() and _marker_of(directory) != upstream and not (directory / bundle.MARKER_FILENAME).is_file()


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def _fsr4_json(state: fsr4.State | None) -> dict | None:
    return None if state is None else {"state": state.kind, "tool": state.tool, "version": state.version}


class Patcher:
    def __init__(self, home: Path):
        self.home = home
        self.plugin_home = home / bundle.HOME_DIRNAME
        self.library = LibraryStore(self.plugin_home / "library")
        self.settings = SettingsStore(self.plugin_home / "settings")
        self.patches = PatchIndex(self.plugin_home / "patched.json")
        self.user_libraries = UserLibraryStore(self.plugin_home / "libraries")
        self.library_choices = LibraryChoicesStore(self.plugin_home / "settings" / "libraries.json")

    # ── directories ──────────────────────────────────────────────────────────

    def resolve_directory(self, directory: str) -> Path:
        """A user-supplied directory, checked to exist and be writable."""
        target = Path(directory).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"Target directory does not exist: {directory}")
        if not target.is_dir():
            raise NotADirectoryError(f"Target path is not a directory: {directory}")
        if not os.access(target, os.W_OK | os.X_OK):
            raise PermissionError(f"Insufficient permissions for {directory}")
        return target

    def patch_directory(
        self,
        directory: Path,
        dll_name: str,
        *,
        version_id: str | None = None,
        reset_ini: bool = False,
        steam_game: marker.SteamGame | None = None,
        fsr4_driver: Path | None = None,
        unless_current: bool = False,
        settings_appid: str | None = None,
        keep_libraries: bool = False,
    ) -> dict:
        """Patch a directory with a library version and record it in a marker. A patch that names no
        version (the launch wrapper's, unless DECKYSCALER_VERSION is set) keeps the one the directory is
        patched with, else takes the newest downloaded. `unless_current` leaves a directory alone when
        it is already patched exactly as this patch would patch it (the wrapper patches on every launch).
        The user's libraries are picked as the game's choice says, or as the directory has them with
        `keep_libraries` (the wrapper's patch, as for the version: a new choice is the user's to apply); every
        other library OptiScaler's menu offers goes in with them, as the device has them now."""
        if dll_name not in bundle.VALID_DLL_NAMES:
            return _error(f"Invalid proxy DLL name: {dll_name}")
        if _patched_by_upstream(directory):
            return _error(PATCHED_BY_DECKY_FRAMEGEN)
        marker_path = directory / bundle.MARKER_FILENAME
        recorded_in = _marker_of(directory)
        installed = self.library.installed()
        if version_id:
            entry = next((e for e in installed if e.id == version_id), None)
            if entry is None:
                return _error(f"OptiScaler {version_id} is not in the library.")
        else:
            entry = library.version_to_patch_with(installed, files.read_json(recorded_in).get("optiscaler_version"))
            if entry is None:
                return _error(NO_VERSION)
        family = library.FAMILIES[entry.family]
        source = self.library.version_dir(entry.id) / library.FILES_DIRNAME
        settings_appid = steam_game.appid if steam_game else settings_appid
        previous_details = files.read_json(recorded_in)
        had = library_choice.recorded_picks(previous_details.get("libraries")) if recorded_in.exists() else None
        to_place = self._libraries_to_place(settings_appid, had if keep_libraries else None, family)
        placed = library_choice.placed(to_place)
        version_files = files.files_under(source)
        if unless_current and not reset_ini and self._patched_as(directory, entry.id, dll_name, placed, version_files):
            log.info(f"{directory} is already patched with OptiScaler {entry.id}, {dll_name}")
            if patch_record.placed_by(patch_record.parse(files.read_json(marker_path)), plan.INI_FILENAME):
                self.apply_settings(directory, source, settings_appid)
            return {"status": "success", "message": f"OptiScaler {entry.version} is in {directory}.", "optiscaler_version": entry.id}

        carried_over: frozenset[str] = frozenset()
        previous = patch_record.parse(previous_details)
        if previous is not None:
            # A repatch first undoes the previous patch, exactly as its marker records it, keeping
            # the OptiScaler.ini it placed (the user's settings) unless asked to reset it or the
            # new version is of another family, whose ini keys differ. A damaged record undoes nothing: what its
            # patch left is cleared below, and the new record replaces it.
            same_family = previous_details.get("family") == entry.family
            if same_family and not reset_ini and plan.INI_FILENAME in {p.path for p in previous.placed}:
                carried_over = frozenset({plan.INI_FILENAME})
            undone = self.unpatch_directory(directory, keep=carried_over)
            if undone["status"] != "success":
                return undone
        try:
            # What a patch left whose record is gone (the marker lost, or damaged) goes first: nothing would take it
            # away, and a link can't be made where one is. Which version it was, and whether the library still has
            # it, isn't known, so every family's own folders are looked into. Its OptiScaler.ini is set aside as the
            # game's, for a fresh one the settings reach.
            looked_into = (
                *version_placement.placed_dirs(version_files),
                *sorted(game_directory.directories_under(directory, version_placement.family_dirs())),
            )
            here = game_directory.contents(directory, looked_into)
            lost = patch_record.made_by_the_plugin(here, str(self.plugin_home.absolute()))
            repairing = previous is None and (recorded_in.exists() or bool(lost))
            left = patch_record.left_behind(lost, self._plugin_dirs() if repairing else ())
            if left:
                game_directory.execute(left, directory, source)
            # What is in the game where a patch places files, at any depth: a file there that isn't ours (OptiScaler
            # unpacked by hand, the user's own provider files) is set aside as a backup, never linked or copied over.
            entries = game_directory.listing(directory)[0] | frozenset(game_directory.contents(directory, looked_into))
            placement = self.placement(to_place, family)
            request = version_placement.Request(
                dll_name, reset_ini or repairing, str(fsr4_driver) if fsr4_driver else None, placement.copies
            )
            operations = version_placement.plan_patch(entries, version_files, family, request)
            log.info(f"Patching {directory} with OptiScaler {entry.id}, {dll_name}, libraries {list(placed)}")
            recorded = patch_record.record(
                operations,
                entries,
                game_directory.bundle_hashes(source, operations),
                carried_over & entries,
                placement.settings_files,
                placement.owned_dirs,
            )
            details = marker.build(
                dll_name=dll_name,
                target_dir=directory,
                backed_up_files=[backup.original for backup in recorded.backups],
                optiscaler_version=entry.id,
                family=entry.family,
                patched_at=datetime.now(timezone.utc).isoformat(),
                steam_game=steam_game,
                libraries=placement.recorded,
                library_layer=placement.layer,
            )
            # The record lands before the first file does, so even an interrupted patch can be undone.
            files.replace_json(marker_path, {**details, **patch_record.to_json(recorded, complete=False)})
            self._remember(directory, marker.shown_name(details, directory))
            game_directory.execute(operations, directory, source)
            files.replace_json(marker_path, {**details, **patch_record.to_json(recorded, complete=True)})
            if patch_record.placed_by(recorded, plan.INI_FILENAME):
                # Keys the previous patch's libraries set and these don't are written back once, in a kept ini; a
                # fresh one holds none of them.
                previous = marker.library_layer(previous_details) if carried_over else {}
                released = library_placement.released(previous, placement.layer)
                self.apply_settings(directory, source, settings_appid, released)
        except plan.PlanError as exc:
            return _error(str(exc))
        except PermissionError as exc:
            log.error(f"Patch permission error: {exc}")
            return _error(f"Permission error while patching: {exc}")
        except Exception as exc:
            log.error(f"Patch failed: {exc}")
            return _error(f"Patch failed: {exc}")
        return {
            "status": "success",
            "message": f"OptiScaler {entry.version} is in {directory}.",
            "optiscaler_version": entry.id,
        }

    def apply_settings(
        self, directory: Path, source: Path, appid: str | None, released: frozenset[settings_layers.Key] = frozenset()
    ) -> None:
        """Write the user's settings into a game's OptiScaler.ini: the global ones with the game's own over
        them, as far as the version's own OptiScaler.ini (`source`) offers each key and value, and over both
        what the game's libraries set, as its marker records. Only an ini the patch placed gets them: one the
        game had before is someone else's, and unpatching must leave it as it was."""
        try:
            schema = ini_schema.parse(files.read_text(source / plan.INI_FILENAME))
        except OSError as exc:
            log.warning(f"Reading the version's OptiScaler.ini failed, settings left as they are: {exc}")
            return
        game = self.settings.game_layer(appid) if appid else {}
        libraries = marker.library_layer(files.read_json(_marker_of(directory)))
        values = settings_layers.to_write(schema, self.settings.global_layer(), game, libraries, released)
        game_directory.edit_ini(directory / plan.INI_FILENAME, lambda text: ini.set_values(text, values), "the user's settings")

    # ── the user's libraries ─────────────────────────────────────────────────

    def _libraries_to_place(
        self, appid: str | None, recorded: tuple[library_choice.Pick, ...] | None, family: library.Family
    ) -> library_choice.ToPlace:
        installed = self.user_libraries.installed()
        chosen = library_choice.to_patch_with(self.library_choices.read(), appid, recorded, installed)
        return library_choice.to_place(chosen, installed, family)

    def _plugin_dirs(self) -> tuple[str, ...]:
        """The folders of a game only the plugin's libraries fill, for every family that takes libraries."""
        libraries = self.user_libraries.installed()
        return tuple(
            path
            for family in library.FAMILIES.values()
            if family.libraries
            for path in library_placement.plugin_dirs(family.main_dir, libraries)
        )

    def placement(self, to_place: library_choice.ToPlace, family: library.Family) -> library_placement.Placement:
        """How a game's libraries go into a game of `family`, from their files on the device."""
        libraries = [item for _, item in to_place.picked] + list(to_place.offered)
        files_dirs = {item.id: str(self.user_libraries.files_dir(item.id)) for item in libraries}
        return library_placement.place(to_place, family.main_dir, files_dirs)

    def chosen_layer(self, chosen: dict[str, str], family: library.Family) -> settings_layers.LibraryLayer:
        """The ini keys the libraries of a choice would set in a game patched with a version of `family`."""
        return self.placement(library_choice.to_place(chosen, self.user_libraries.installed(), family), family).layer

    def library_users(self, library_id: str) -> list[str]:
        """The patched games whose patch placed a library, picked or offered."""
        return library_choice.users(library_id, [(name, details.get("libraries")) for _, name, details in self.patched_markers()])

    def _patched_as(
        self,
        directory: Path,
        version_id: str,
        dll_name: str,
        placed: tuple[library_choice.Placed, ...],
        version_files: frozenset[str],
    ) -> bool:
        """Whether a patch now would place nothing other than the directory has: the same version, proxy and
        libraries, every placed file still there, and every file the version holds now among them (one that came
        back with Download again after the game was patched without it is not)."""
        details = files.read_json(_marker_of(directory))
        recorded = patch_record.parse(details)
        return (
            recorded is not None
            and marker.describes(details, version_id, dll_name, placed)
            and patch_record.intact(recorded, game_directory.current_state(directory, recorded))
            and version_placement.placed_every_file(recorded, version_files)
        )

    def _is_bundle(self, directory: Path) -> bool:
        """Whether `directory` is ~/deckyscaler or inside it: never a game, never to be unpatched or reset."""
        return directory.resolve().is_relative_to(self.plugin_home.resolve())

    def unpatch_directory(self, directory: Path, keep: frozenset[str] = frozenset()) -> dict:
        """Undo the patch recorded in the directory's marker. The marker goes last, so a failure keeps it.

        `keep` names placed files a repatch carries over instead of removing.
        """
        if self._is_bundle(directory):
            return _error(BUNDLE_IS_NOT_A_GAME)
        marker_path = _marker_of(directory)
        if _patched_by_upstream(directory):
            return _error(PATCHED_BY_DECKY_FRAMEGEN)
        if not marker_path.exists():
            self._forget(directory)
            return {"status": "success", "message": f"No DeckyScaler patch found in {directory}"}
        recorded = patch_record.parse(files.read_json(marker_path))
        if recorded is None:
            return _error(DAMAGED_RECORD)
        try:
            current = game_directory.current_state(directory, recorded)
            operations = patch_record.plan_unpatch(recorded, current, keep, marker_path.name)
            game_directory.execute(operations, directory, self.plugin_home)
        except PermissionError as exc:
            log.error(f"Unpatch permission error: {exc}")
            return _error(f"Permission error while unpatching: {exc}")
        except Exception as exc:
            log.error(f"Unpatch failed: {exc}")
            return _error(f"Unpatch failed: {exc}")
        # What a marker write cut short staged goes with the marker.
        files.staged(directory / bundle.MARKER_FILENAME).unlink(missing_ok=True)
        self._forget(directory)
        return {"status": "success", "message": f"OptiScaler files removed from {directory}"}

    # The index of patched directories follows the markers: an entry is added once a marker is
    # written and dropped once it is gone, but kept while its drive is out. Failing to update it never fails a patch.

    def _remember(self, directory: Path, name: str) -> None:
        try:
            self.patches.add(directory, name, drives.identity(directory))
        except OSError as exc:
            log.warning(f"Updating the index of patched directories failed: {exc}")

    def _forget(self, directory: Path) -> None:
        try:
            self.patches.remove(directory)
        except OSError as exc:
            log.warning(f"Updating the index of patched directories failed: {exc}")

    def _indexed(self) -> tuple[list[tuple[Path, str, dict]], list[tuple[Path, str]]]:
        """The indexed directories by whether their patch can be read now: each one with its marker, with its name and
        marker; each one on a drive that isn't mounted, with its name, kept until the drive is back. A directory whose
        marker is gone from where it can be read (the game was removed, or the marker by hand) is dropped from the
        index."""
        found, away = [], []
        for directory, entry in self.patches.entries().items():
            path = Path(directory)
            marker_path = _marker_of(path)
            if marker_path.is_file():
                found.append((path, entry.name, files.read_json(marker_path)))
                if entry.drive is None and drives.identity(path) is not None:
                    self._remember(path, entry.name)  # indexed before drives were kept: its drive is known now
            elif drives.on_unmounted_drive(path, entry.drive):
                away.append((path, entry.name))
            else:
                self._forget(path)
        return found, away

    def patched_markers(self) -> list[tuple[Path, str, dict]]:
        """Every indexed directory whose patch can be read now, with its name and marker."""
        return self._indexed()[0]

    def away(self) -> list[str]:
        """The names of the indexed directories on a drive that isn't mounted: what reaches every patched game
        doesn't reach them until the drive is back."""
        return sorted(name for _, name in self._indexed()[1])

    def _against_version(self, details: dict, installed: list[library.Installed], seen: dict[str, frozenset[str]]) -> dict:
        """What a patched game's version, while still in the library, says of the game: whether the game lacks files
        the version holds now (patched while they were gone, it gets them only when patched again, which the launch
        wrapper does at launch), and whether the version is incomplete (files a game gets are gone from it, so the
        game's links to them lead nowhere). `seen` keeps each version's files for the rest of one listing."""
        version = str(details.get("optiscaler_version") or "")
        entry, recorded = next((e for e in installed if e.id == version), None), patch_record.parse(details)
        if entry is None or recorded is None:
            return {"lacks_version_files": False, "version_incomplete": False}
        if version not in seen:
            seen[version] = self.library.files_of(version)
        return {
            "lacks_version_files": not version_placement.placed_every_file(recorded, seen[version]),
            "version_incomplete": bool(version_placement.lost_files(entry, seen[version])),
        }

    def patched_games(self) -> dict:
        """Every game and directory the plugin patched, by name: what it was patched with, what its version says of it
        (`_against_version`), and whether it has settings of its own. A Steam game has its appid; a directory patched
        by path has none. Those on a drive that isn't mounted are listed apart (`away`), by name alone."""
        installed = self.library.installed()
        seen: dict[str, frozenset[str]] = {}
        games = []
        found, away = self._indexed()
        for directory, name, details in found:
            appid = str(details.get("appid") or "")
            dll_name = details.get("dll_name") or bundle.DEFAULT_PROXY_DLL
            version = details.get("optiscaler_version")
            games.append({
                "directory": str(directory),
                "name": name,
                "appid": appid,
                "dll_name": dll_name,
                "dll_present": (directory / dll_name).exists(),
                "version_id": version,
                "newer_version": library.newer_in_channel(installed, version),
                **self._against_version(details, installed, seen),
                "patched_at": details.get("patched_at"),
                "record": patch_record.state(details),
                "own_settings": bool(appid) and bool(self.settings.game_layer(appid)),
                "libraries": details.get("libraries") or [],
            })
        return {
            "status": "success",
            "games": sorted(games, key=lambda game: game["name"].lower()),
            "away": [{"directory": str(path), "name": name} for path, name in sorted(away, key=lambda item: item[1].lower())],
        }

    def forget(self, directory: str) -> dict:
        """Drop a game on a drive that isn't mounted from the index, for a drive that won't be back: its versions can
        then be removed. Should it come back after all, a Steam game's page finds its patch again."""
        name = next((name for path, name in self._indexed()[1] if str(path) == directory), None)
        if name is None:
            known = entry.name if (entry := self.patches.entries().get(directory)) else directory
            return _error(f"{known} isn't on a drive that isn't mounted: unpatch it rather than forget it.")
        try:
            self.patches.remove(Path(directory))
        except OSError as exc:
            return _error(f"Forgetting {name} failed: {exc}")
        return {"status": "success", "message": f"{name} is forgotten."}

    def games_using(self, version_id: str) -> library.Users:
        """The patched games and directories whose marker names this library version, and those on a drive that isn't
        mounted, whose marker can't be read."""
        found, away = self._indexed()
        return library.Users(
            tuple(sorted(name for _, name, details in found if details.get("optiscaler_version") == version_id)),
            tuple(sorted(name for _, name in away)),
        )


    def patch_user_directory(
        self, directory: str, dll_name: str, version_id: str | None = None
    ) -> dict:
        try:
            target = self.resolve_directory(directory)
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            log.error(f"Manual patch validation failed: {exc}")
            return _error(str(exc))
        return self.patch_directory(target, dll_name, version_id=version_id)

    def unpatch_user_directory(self, directory: str, confirmed_reset: bool = False) -> dict:
        """Unpatch a directory the user picked: by its record, or — for a Decky Framegen version's
        patch, once the user confirmed what the preview showed — by resetting it."""
        try:
            target = self.resolve_directory(directory)
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            log.error(f"Manual unpatch validation failed: {exc}")
            return _error(str(exc))
        if confirmed_reset and self._unpatch_mode(_marker_of(target)) == RESET:
            return self._reset_directory(target)
        # Decky Framegen's marker is refused there: its patch needs the confirmed reset.
        return self.unpatch_directory(target)

    def preview_unpatch_directory(self, directory: str) -> dict:
        try:
            target = self.resolve_directory(directory)
            mode = self._unpatch_mode(_marker_of(target))
            if mode == RECORD:
                return {"status": "success", "mode": RECORD, "target_dir": str(target)}
            if mode == REPAIR:
                return _error(DAMAGED_RECORD)
            preview, _ = self._reset_plan(target, None, None)
            return {**preview, "mode": RESET} if preview["status"] == "success" else preview
        except Exception as exc:
            log.error(f"[DeckyScaler] preview_unpatch_directory failed for {directory}: {exc}")
            return _error(str(exc))

    @staticmethod
    def _unpatch_mode(marker_path: Path | None) -> str:
        """RECORD when the marker holds a patch record; REPAIR when it is the plugin's and its record is damaged;
        RESET for anything else (Decky Framegen's marker, or no marker — then only the reset's own evidence rules
        decide whether anything is ours)."""
        if marker_path is None or not marker_path.is_file():
            return RESET
        state = patch_record.state_of(marker_path.name, files.read_json(marker_path))
        return {patch_record.UPSTREAM: RESET, patch_record.DAMAGED: REPAIR}.get(state, RECORD)

    def path_defaults(self) -> dict:
        """Starting points for the pickers: home; the games of the first Steam library found (native or Flatpak),
        else where native Steam would keep them; and Downloads, where Desktop Mode puts what the user brings, or
        home when there is none."""
        libraries = [library for library in steam_library.library_paths(self.home) if (library / "steamapps").is_dir()]
        steam_root = libraries[0] if libraries else steam.steam_root_candidates(self.home)[0]
        downloads = self.home / "Downloads"
        return {
            "home": str(self.home),
            "steam_common": str(steam_root / "steamapps" / "common"),
            "downloads": str(downloads if downloads.is_dir() else self.home),
        }

    # ── Steam games ──────────────────────────────────────────────────────────

    def list_games(self) -> dict:
        try:
            games = [
                {"appid": game.appid, "name": game.name, "install_found": game.install_path.exists()}
                for game in steam_library.installed_games(self.home)
            ]
        except Exception as exc:
            log.error(str(exc))
            return _error(str(exc))
        return {"status": "success", "games": games}

    @staticmethod
    def is_running(directory: Path) -> bool:
        """Whether a game in `directory` runs: one of its executables is in a process's command line."""
        executables = [exe for exe in directory.glob("*.exe") if exe.is_file()]
        return bool(executables) and exe_target.running_executable(executables, processes.command_lines()) is not None

    def _running_executable(self, candidates: list[Path]) -> Path | None:
        if not candidates:
            return None
        return exe_target.running_executable(candidates, processes.command_lines())

    def _is_running(self, game: steam_library.InstalledGame) -> bool:
        return self._running_executable(steam_library.executables(game.install_path)) is not None

    def _fsr4(self, game: steam_library.InstalledGame) -> tuple[fsr4.State | None, Path | None]:
        """The game's FSR 4 under Proton, and — when a patch should ask Proton to fetch it — where in the
        game's prefix the DLL lands."""
        amd = proton.amd_gpu()
        tool = proton.compat_tool(self.home, game.appid)
        tool_dir = proton.tool_directory(self.home, tool) if tool else None
        reads_variable = tool_dir is not None and proton.reads_upgrade_variable(tool_dir)
        prefix = proton.compatdata(game.library_path, game.appid)
        state = fsr4.state(amd, tool, reads_variable, proton.dll_in_prefix(prefix), proton.tracked_version(prefix))
        return state, proton.prefix_dll(prefix) if fsr4.wants_upgrade_variable(amd, reads_variable) else None

    def _patch_target(self, game: steam_library.InstalledGame) -> tuple[Path, Path | None]:
        candidates = steam_library.executables(game.install_path)
        running = self._running_executable(candidates)
        return exe_target.patch_target(game.install_path, game.name, candidates, running)

    def find_marker(self, install_root: Path) -> Path | None:
        """The game's patch marker: where the patch index says the plugin patched it, else by searching
        the whole install, for the plugin's marker and then the original Decky Framegen's (whose patch is
        reset, having no record). A patch of the plugin's found by searching, its record under either name, goes
        back into the index."""
        if not install_root.exists():
            return None
        for directory in self.patches.entries():
            marker_path = _marker_of(Path(directory))
            if marker_path.parent.is_relative_to(install_root) and marker_path.is_file():
                return marker_path
        try:
            for name in (bundle.MARKER_FILENAME, bundle.UPSTREAM_MARKER_FILENAME):
                found = next((path for path in install_root.rglob(name) if path.is_file()), None)
                if found is not None:
                    break
            else:
                return None
        except OSError:
            return None
        details = files.read_json(found)
        if patch_record.state_of(found.name, details) != patch_record.UPSTREAM:
            # The index learns a patch of ours it didn't know, so the pages listing from it show the game again.
            self._remember(found.parent, marker.shown_name(details, found.parent))
        return found

    def game_status(self, appid: str) -> dict:
        try:
            return self._game_status(appid)
        except Exception as exc:
            log.error(f"[DeckyScaler] get_game_status failed for {appid}: {exc}")
            return _error(str(exc))

    def _game_status(self, appid: str) -> dict:
        game = steam_library.find_game(self.home, str(appid))
        unpatched = {
            "status": "success",
            "appid": str(appid),
            "patched": False,
            "dll_name": None,
            "target_dir": None,
            "newer_version": None,
            "lacks_version_files": False,
            "version_incomplete": False,
            "fsr4": None,
            "record": None,
        }
        if game is None:
            return {**unpatched, "install_found": False, "message": "Game not found in Steam library."}
        if not game.install_path.exists():
            return {**unpatched, "name": game.name, "install_found": False, "message": "Game install directory not found."}
        # FSR 4 is the Proton's business, so it is told whether the game is patched or not.
        unpatched["fsr4"] = _fsr4_json(self._fsr4(game)[0])
        marker_path = self.find_marker(game.install_path)
        if marker_path is None:
            return {**unpatched, "name": game.name, "install_found": True, "message": "Not patched."}

        metadata = files.read_json(marker_path)
        record = patch_record.state_of(marker_path.name, metadata)
        if record in (patch_record.UPSTREAM, patch_record.DAMAGED):
            return {
                **unpatched, "name": game.name, "install_found": True, "patched": True, "record": record,
                "target_dir": str(marker_path.parent),
                "message": PATCHED_BY_DECKY_FRAMEGEN if record == patch_record.UPSTREAM else DAMAGED_RECORD,
            }
        dll_name = metadata.get("dll_name", bundle.DEFAULT_PROXY_DLL)
        # The marker sits in the directory it patched; the path written into it can go stale.
        target_dir = marker_path.parent
        dll_present = (target_dir / dll_name).exists()
        version = metadata.get("optiscaler_version")
        installed = self.library.installed()
        if dll_present:
            message = f"Patched with OptiScaler {version} using {dll_name}."
        else:
            message = f"Marker found but {dll_name} is missing. Patch it again."
        return {
            "status": "success",
            "appid": str(appid),
            "name": game.name,
            "install_found": True,
            "patched": dll_present,
            "dll_name": dll_name,
            "target_dir": str(target_dir),
            "patched_at": metadata.get("patched_at"),
            "optiscaler_version": version,
            "newer_version": library.newer_in_channel(installed, version),
            **self._against_version(metadata, installed, {}),
            "fsr4": unpatched["fsr4"],
            "libraries": metadata.get("libraries") or [],
            "record": record,
            "message": message,
        }

    def patch_game(
        self, appid: str, dll_name: str, current_launch_options: str | None, version_id: str | None = None
    ) -> dict:
        """Patch a Steam game. `current_launch_options` is None when Steam didn't say what they are."""
        try:
            return self._patch_game(appid, dll_name, current_launch_options, version_id)
        except Exception as exc:
            log.error(f"[DeckyScaler] patch_game failed for {appid}: {exc}")
            return _error(str(exc))

    def _patch_game(
        self, appid: str, dll_name: str, current_launch_options: str | None, version_id: str | None
    ) -> dict:
        game = steam_library.find_game(self.home, str(appid))
        if game is None:
            return _error("Game not found in Steam library.")
        if not game.install_path.exists():
            return _error("Game install directory does not exist.")
        candidates = steam_library.executables(game.install_path)
        if self._running_executable(candidates) is not None:
            return _error("Close the game before patching.")
        existing_marker = self.find_marker(game.install_path)
        existing = files.read_json(existing_marker) if existing_marker else {}
        stored = str(existing.get("original_launch_options") or "") if existing_marker else None
        original_options = marker.original_launch_options(current_launch_options, stored)
        if original_options is None:
            return _error(LAUNCH_OPTIONS_UNKNOWN)

        target_dir, target_exe = exe_target.patch_target(game.install_path, game.name, candidates, None)
        if existing_marker and existing_marker.parent != target_dir:
            # The game's executable moved since its last patch; that directory is undone first.
            moved = self.unpatch_directory(existing_marker.parent)
            if moved["status"] != "success":
                return moved
        log.info(f"[DeckyScaler] patch_game: appid={appid} dll={dll_name} target={target_dir} exe={target_exe}")
        fsr4_driver = self._fsr4(game)[1]
        result = self.patch_directory(
            target_dir,
            dll_name,
            version_id=version_id,
            steam_game=marker.SteamGame(str(appid), game.name, original_options),
            fsr4_driver=fsr4_driver,
        )
        if result["status"] != "success":
            return result

        managed_options = launch_options.managed(dll_name, fsr4_driver is not None)
        log.info(f"[DeckyScaler] patch_game success: appid={appid} launch_options={managed_options}")
        return {
            "status": "success",
            "appid": str(appid),
            "name": game.name,
            "dll_name": dll_name,
            "target_dir": str(target_dir),
            "launch_options": managed_options,
            "original_launch_options": original_options,
            "optiscaler_version": result.get("optiscaler_version"),
            "message": f"Patched {game.name} with OptiScaler {result.get('optiscaler_version')} using {dll_name}.",
        }

    def unpatch_game(self, appid: str, current_launch_options: str = "", confirmed_reset: bool = False) -> dict:
        """Unpatch a Steam game: by its record, or — for a Decky Framegen patch, once the
        user confirmed what the preview showed — by resetting it."""
        try:
            return self._unpatch_game(appid, current_launch_options, confirmed_reset)
        except Exception as exc:
            log.error(f"[DeckyScaler] unpatch_game failed for {appid}: {exc}")
            return _error(str(exc))

    def _unpatch_game(self, appid: str, current_launch_options: str, confirmed_reset: bool) -> dict:
        game = steam_library.find_game(self.home, str(appid))
        if game is None:
            return _error("Game not found in Steam library.")
        not_patched = {"status": "success", "appid": str(appid), "name": game.name, "launch_options": ""}
        if not game.install_path.exists():
            return {**not_patched, "message": "Game install directory does not exist."}
        if self._is_running(game):
            return _error("Close the game before unpatching.")
        marker_path = self.find_marker(game.install_path)
        if self._unpatch_mode(marker_path) == RESET:
            if confirmed_reset:
                return self._reset_game(appid, current_launch_options)
            if marker_path is None:
                return {**not_patched, "message": "No DeckyScaler patch found for this game."}
            return _error(PATCHED_BY_DECKY_FRAMEGEN)

        metadata = files.read_json(marker_path)
        target_dir = marker_path.parent
        result = self.unpatch_directory(target_dir)
        if result["status"] != "success":
            return result
        log.info(f"[DeckyScaler] unpatch_game success: appid={appid} target={target_dir}")
        return {
            "status": "success",
            "appid": str(appid),
            "name": game.name,
            "launch_options": str(metadata.get("original_launch_options") or ""),
            "message": f"Unpatched {game.name}.",
        }

    # ── unpatching what Decky Framegen patched ──────────────────────
    # Such a patch has no record, so Unpatch resets the directory instead: for one game the
    # user picked, shown first (preview), carried out only once the user confirms.

    def _reset_target(self, appid: str) -> tuple[steam_library.InstalledGame, Path, Path | None]:
        game = steam_library.find_game(self.home, str(appid))
        if game is None:
            raise LookupError("Game not found in Steam library.")
        if not game.install_path.exists():
            raise LookupError("Game install directory does not exist.")
        marker_path = self.find_marker(game.install_path)
        # The marker sits in the directory it patched. The path Decky Framegen wrote into it is not
        # trusted: it can name a mount point or a library location that no longer exists.
        target = marker_path.parent if marker_path is not None else self._patch_target(game)[0]
        return game, target, marker_path

    def _reset_plan(
        self, directory: Path, marker_path: Path | None, current_launch_options: str | None
    ) -> tuple[dict, tuple[plan.Operation, ...]]:
        """What resetting `directory` does, as the frontend shows it, and the operations that do it."""
        if self._is_bundle(directory):
            return _error(BUNDLE_IS_NOT_A_GAME), ()
        entries, plugin_entries = game_directory.listing(directory)
        marked_elsewhere = marker_path is not None and marker_path.parent != directory
        reset = stock_reset.plan(entries, plugin_entries, marked_elsewhere)
        if reset.evidence is None:
            return _error(f"No sign of DeckyScaler in {directory}; nothing to reset."), ()
        stored = str(files.read_json(marker_path).get("original_launch_options") or "") if marker_path else ""
        new_options = (
            stock_reset.launch_options_after_reset(current_launch_options, stored)
            if current_launch_options is not None
            else None
        )
        preview = {
            "status": "success",
            "target_dir": str(directory),
            "evidence": reset.evidence,
            "remove": list(reset.removed),
            "restore": list(reset.restored),
            "unrecoverable": list(reset.unrecoverable),
            "launch_options": new_options,
        }
        return preview, reset.operations

    def preview_unpatch_game(self, appid: str, current_launch_options: str) -> dict:
        """How unpatching a game goes: by its record (nothing to confirm), or a reset whose preview
        the user confirms first."""
        try:
            game, target, marker_path = self._reset_target(appid)
            mode = self._unpatch_mode(marker_path)
            if mode == RECORD:
                return {"status": "success", "mode": RECORD, "name": game.name, "target_dir": str(target)}
            if mode == REPAIR:
                return _error(DAMAGED_RECORD)
            preview, _ = self._reset_plan(target, marker_path, current_launch_options)
            return {**preview, "mode": RESET, "name": game.name} if preview["status"] == "success" else preview
        except Exception as exc:
            log.error(f"[DeckyScaler] preview_unpatch_game failed for {appid}: {exc}")
            return _error(str(exc))

    def _reset_game(self, appid: str, current_launch_options: str) -> dict:
        try:
            game, target, marker_path = self._reset_target(appid)
            if self._is_running(game):
                return _error("Close the game before resetting it.")
            preview, operations = self._reset_plan(target, marker_path, current_launch_options)
            if preview["status"] != "success":
                return preview
            game_directory.execute(operations, target, self.plugin_home)
            if marker_path is not None and marker_path.exists():
                marker_path.unlink()
            self._forget(target)
            log.info(f"[DeckyScaler] reset_game: appid={appid} target={target}")
            return {**preview, "name": game.name, "message": f"{game.name} is back to how it shipped."}
        except Exception as exc:
            log.error(f"[DeckyScaler] reset_game failed for {appid}: {exc}")
            return _error(str(exc))

    def _reset_directory(self, target: Path) -> dict:
        try:
            preview, operations = self._reset_plan(target, None, None)
            if preview["status"] != "success":
                return preview
            game_directory.execute(operations, target, self.plugin_home)
            self._forget(target)
            log.info(f"[DeckyScaler] reset_directory: {target}")
            return {**preview, "message": f"{target} is back to how it shipped."}
        except Exception as exc:
            log.error(f"[DeckyScaler] reset_directory failed for {target}: {exc}")
            return _error(str(exc))

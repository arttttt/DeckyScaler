"""The user's libraries: list, download, add and remove them, choose which go into games, and apply a new choice to
the games already patched."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from deckyscaler.application.patcher import Patcher
from deckyscaler.domain import library, library_choice, user_libraries
from deckyscaler.infrastructure import archive, dll_version, files
from deckyscaler.infrastructure.github_releases import Download, ListReleases, ReleasesUnavailable, Report

log = logging.getLogger(__name__)


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def _refused(reason: str) -> dict:
    """Something the user picked that isn't a library, as a kind the frontend words."""
    return {"status": "error", "reason": reason}


class UserLibraries:
    def __init__(self, home: Path, list_releases: ListReleases, download: Download, report: Report):
        self.patcher = Patcher(home)
        self.store = self.patcher.user_libraries
        self.choices = self.patcher.library_choices
        self.list_releases = list_releases
        self.download = download
        self.report = report

    # ── what is on the device ────────────────────────────────────────────────

    def installed(self) -> dict:
        """The libraries, by name, with what they serve and take and the games that have them; the slots and the
        global choice; and the patched games a patch now would give other libraries ("Apply to them")."""
        libraries = sorted(self.store.installed(), key=lambda item: item.label.lower())
        sizes = {item.id: self.store.size(item.id) for item in libraries}
        patched = self.patcher.patched_markers()
        recorded = [(name, details.get("libraries")) for _, name, details in patched]
        choices = self.choices.read()
        return {
            "libraries": [
                user_libraries.library_json(item, sizes[item.id], library_choice.users(item.id, recorded)) for item in libraries
            ],
            "slots": list(user_libraries.SLOTS),
            "global": choices.global_choice,
            "to_apply": [name for _, name, details in self._to_apply(patched, choices, libraries)],
            "installed_bytes": sum(sizes.values()),
        }

    def game_choice(self, appid: str) -> dict:
        """A game's own choice per slot (a library, none, or absent: the global choice), what it comes to, and
        whether the game, patched, has other libraries than that ("patch again")."""
        choices, installed = self.choices.read(), self.store.installed()
        patched = [entry for entry in self.patcher.patched_markers() if str(entry[2].get("appid") or "") == appid]
        return {
            "status": "success",
            "own": choices.games.get(appid, {}),
            "resolved": library_choice.resolved(choices, appid),
            "pending": bool(self._to_apply(patched, choices, installed)),
        }

    @staticmethod
    def _to_apply(patched: list, choices: library_choice.Choices, installed: list) -> list:
        return [
            (path, name, details)
            for path, name, details in patched
            if details.get("family") in library.FAMILIES
            and library_choice.needs_applying(
                details.get("libraries"),
                library_choice.resolved(choices, str(details.get("appid") or "") or None),
                installed,
                library.FAMILIES[details["family"]],
            )
        ]

    # ── downloading ──────────────────────────────────────────────────────────

    def _releases(self, source: str) -> list[user_libraries.Release]:
        return user_libraries.releases(source, self.list_releases(user_libraries.SOURCES[source].repository))

    def versions(self, source: str) -> dict:
        """A source's releases for the download dialog: the newest, then those downloaded and no longer listed."""
        if source not in user_libraries.SOURCES:
            return _error(f"Unknown source: {source}")
        installed = self.store.installed()
        sizes = {item.id: self.store.size(item.id) for item in installed}
        try:
            releases, listing_error = self._releases(source), None
        except ReleasesUnavailable as exc:
            log.error(f"Listing {source} releases failed: {exc}")
            releases, listing_error = [], str(exc)
        rows = user_libraries.rows(source, releases, installed, sizes)
        return {"status": "success", "versions": [row.__dict__ for row in rows], "listing_error": listing_error}

    def install(self, source: str, release_id: str) -> dict:
        """Download, verify and unpack a release, then add it in one step; anything that goes wrong adds nothing."""
        if source not in user_libraries.SOURCES:
            return _error(f"Unknown source: {source}")
        if any(item.id == release_id for item in self.store.installed()):
            return _error(f"{release_id} is already on the device.")
        try:
            release = next((r for r in self._releases(source) if r.id == release_id), None)
        except ReleasesUnavailable as exc:
            return _error(str(exc))
        if release is None:
            return _error(f"{release_id} is no longer published. Check again.")
        if release.unsupported:
            return _error(f"{release.version} can't be downloaded now. Check again.")
        if self.store.free_bytes() < user_libraries.space_needed(release.size):
            return _error(f"Not enough free space: {release.version} needs about {user_libraries.space_needed(release.size) // 1_000_000 + 1} MB.")
        self.store.clear_partial()
        try:
            stage = self.store.staging(release.id)
            zip_path = stage.parent / f"{release.id}.zip"
            self.download(release.url, zip_path, lambda got, total: self.report(release.id, got, total))
            if files.sha256(zip_path) != release.sha256:
                return _error(f"The {release.version} download did not match its checksum. Try again.")
            contents = user_libraries.recognize(archive.zip_members(zip_path))
            if isinstance(contents, str):
                return _refused(contents)
            archive.extract_zip(zip_path, contents.files, stage / user_libraries.FILES_DIRNAME, user_libraries.MAX_BYTES)
            added = user_libraries.downloaded(release, contents, datetime.now(timezone.utc).isoformat())
            self.store.commit(stage, added)
        except (ReleasesUnavailable, RuntimeError, OSError) as exc:
            log.error(f"Installing {release.id} failed: {exc}")
            return _error(f"Installing {release.version} failed: {exc}")
        finally:
            self.store.clear_partial()
        return {"status": "success", "id": added.id, "message": f"{added.label} is downloaded."}

    # ── adding the user's own ────────────────────────────────────────────────

    def add(self, picked: str) -> dict:
        """Add what the user picked: a library's zip, its folder, or a DLL."""
        path = Path(picked)
        try:
            if path.is_dir():
                members, source = files.files_under(path), path
            elif path.suffix.lower() == ".zip":
                members, source = archive.zip_members(path), None
            elif path.is_file():
                members, source = frozenset({path.name}), path.parent
            else:
                return _error(f"{picked} isn't there.")
            contents = user_libraries.recognize(members)
            if isinstance(contents, str):
                return _refused(contents)
            if source is not None and sum((source / p).stat().st_size for p in contents.files) > user_libraries.MAX_BYTES:
                return _error(f"{path.name} takes more than {user_libraries.MAX_BYTES // 1_000_000} MB.")
            self.store.clear_partial()
            stage = self.store.staging("added")
            kept = stage / user_libraries.FILES_DIRNAME
            if source is None:
                archive.extract_zip(path, contents.files, kept, user_libraries.MAX_BYTES)
            else:
                files.copy_files(source, contents.files, kept)
            lone = contents.dlls[0].path if len(contents.dlls) == 1 else None
            version = dll_version.file_version(kept / lone) if lone else None
            taken = {item.id for item in self.store.installed()}
            added = user_libraries.added(contents, path.name, version, taken, datetime.now(timezone.utc).isoformat())
            if isinstance(added, str):
                return _refused(added)
            self.store.commit(stage, added)
        except (RuntimeError, OSError) as exc:
            log.error(f"Adding {picked} failed: {exc}")
            return _error(f"Adding {path.name} failed: {exc}")
        finally:
            self.store.clear_partial()
        return {"status": "success", "id": added.id, "message": f"{added.label} is added."}

    # ── removing ─────────────────────────────────────────────────────────────

    def removal(self, library_id: str) -> dict:
        """What removing a library touches, asked before the user confirms: the games that have it (each keeps its
        copy until patched again) and whether it is the choice for every game."""
        if not any(item.id == library_id for item in self.store.installed()):
            return _error(f"{library_id} is not on the device.")
        return {
            "status": "success",
            "games": self.patcher.library_users(library_id),
            "global": library_id in self.choices.read().global_choice.values(),
        }

    def remove(self, library_id: str) -> dict:
        if not any(item.id == library_id for item in self.store.installed()):
            return _error(f"{library_id} is not on the device.")
        try:
            self.store.remove(library_id)
            self.choices.write(library_choice.without(self.choices.read(), library_id))
        except OSError as exc:
            return _error(f"Removing {library_id} failed: {exc}")
        return {"status": "success"}

    # ── choosing ─────────────────────────────────────────────────────────────

    def choose(self, scope: str, slot: str, value: str | None) -> dict:
        """Set a slot for every game (scope "global") or a game's own (its appid): a library, NONE, or None (for a
        game, following the global choice). Patched games get it once it is applied or they are patched again: the
        answer names those the change reaches."""
        if slot not in user_libraries.SLOTS:
            return _error(f"Not a slot: {slot}")
        if scope != library_choice.GLOBAL and not scope.isdigit():
            return _error(f"Not a Steam app id: {scope}")
        installed = self.store.installed()
        if not library_choice.can_choose(slot, value, installed):
            return _error(f"{value} isn't a library for that.")
        choices = library_choice.with_choice(self.choices.read(), scope, slot, value)
        self.choices.write(choices)
        # The patched games the change reaches that don't have their libraries yet: every game for a global change.
        patched = [
            entry for entry in self.patcher.patched_markers()
            if scope == library_choice.GLOBAL or str(entry[2].get("appid") or "") == scope
        ]
        return {"status": "success", "to_apply": [name for _, name, _ in self._to_apply(patched, choices, installed)]}

    def apply(self) -> dict:
        """Patch again the games a patch now would give other libraries, with their version and proxy; running ones
        are left alone and named. A Steam game's launch options come back with it, for the frontend to set."""
        choices, installed = self.choices.read(), self.store.installed()
        applied, skipped, failed = [], [], []
        for path, name, details in self._to_apply(self.patcher.patched_markers(), choices, installed):
            if self.patcher.is_running(path):
                skipped.append(name)
                continue
            dll_name, version_id = str(details.get("dll_name") or ""), str(details.get("optiscaler_version") or "")
            appid = str(details.get("appid") or "")
            result = (
                self.patcher.patch_game(appid, dll_name, None, version_id)
                if appid
                else self.patcher.patch_user_directory(str(path), dll_name, version_id)
            )
            if result["status"] == "success":
                # A Steam game's launch options are Steam's to set: the frontend sets what the patch says.
                applied.append({"name": name, "appid": appid, "launch_options": result.get("launch_options")})
            else:
                failed.append({"name": name, "message": result.get("message", "")})
        return {"status": "success", "applied": applied, "skipped": skipped, "failed": failed}

"""Proton builds: list, install and remove custom Proton builds in the Steam install the plugin works with.

Shaped like the OptiScaler library (installed / versions / install / removal / remove), but its own owner: a
build goes into Steam's compatibilitytools.d, is known by Steam's name for it, and Steam only sees a change
after a restart.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from deckyscaler.domain import proton_builds, steam
from deckyscaler.infrastructure import archive, proton
from deckyscaler.infrastructure import steam as steam_library
from deckyscaler.infrastructure.compat_tools_store import CompatToolsStore
from deckyscaler.infrastructure.files import sha256
from deckyscaler.infrastructure.github_releases import ReleasesUnavailable

log = logging.getLogger(__name__)

ListReleases = Callable[[str], list]
Download = Callable[[str, Path, Callable[[int, int | None], None]], None]
Report = Callable[[str, int, int | None], None]
"""Tells the frontend how a download goes: tool name, bytes received, total bytes if known."""

UNPACKED_DIRNAME = "unpacked"


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def _problem(problem: str) -> dict:
    """No Steam install to work with; the frontend words why."""
    return {"status": "error", "problem": problem}


def builds_json() -> list[dict]:
    """The builds the download dialog offers, in its order."""
    return [{"id": build.id, "label": build.label, "note": build.note} for build in proton_builds.BUILDS.values()]


def _app_json(app: steam.NamedApp) -> dict:
    return {"appid": app.appid, "name": app.name, "kind": app.kind}


class ProtonBuilds:
    def __init__(
        self,
        home: Path,
        list_releases: ListReleases,
        download: Download,
        report: Report,
        system_tools: Path | None = None,
    ):
        self.home = home
        self.list_releases = list_releases
        self.download = download
        self.report = report
        self.system_tools = system_tools if system_tools is not None else proton.SYSTEM_TOOLS

    def _active(self, clients: list[tuple[Path, float]] | None = None) -> steam.ActiveRoot:
        return steam_library.active_root(self.home, steam_library.running_clients() if clients is None else clients)

    def _store(self, root: Path) -> CompatToolsStore:
        return CompatToolsStore(root / "compatibilitytools.d", self.system_tools)

    def _games(self, root: Path, appids: list[str]) -> list[dict]:
        named = steam.name_apps(appids, steam_library.app_names(self.home), steam_library.shortcut_names(root))
        return [_app_json(app) for app in named]

    def installed(self) -> dict:
        """Every build Steam would find, with what it takes on disk and the games whose user chose it, and whether
        Steam must restart to see the builds as they are now."""
        clients = steam_library.running_clients()
        active = self._active(clients)
        if active.root is None:
            return {"status": "success", "problem": active.problem, "tools": [], "installed_bytes": 0, "restart_needed": False}
        store = self._store(active.root)
        forced = proton.forced_mappings(active.root)
        rows = []
        for tool in store.installed():
            appids, global_default = proton_builds.chosen_for(tool, forced)
            build = tool.build
            rows.append({
                "id": tool.folder,
                "build": build.id if build else None,
                "build_label": build.label if build else None,
                "system": tool.system,
                "size": store.size(tool),
                "games": self._games(active.root, appids),
                "global_default": global_default,
            })
        own = sum(row["size"] for row in rows if not row["system"])
        restart = steam.restart_needed(active.root, clients, store.changed_at())
        return {"status": "success", "problem": None, "tools": rows, "installed_bytes": own, "restart_needed": restart}

    def _published(self, build_id: str) -> list[proton_builds.Release]:
        return proton_builds.available(build_id, self.list_releases(proton_builds.BUILDS[build_id].repository))

    def versions(self, build_id: str) -> dict:
        """A build's newest releases, each installed, downloadable or saying why not; installed ones stay listed."""
        if build_id not in proton_builds.BUILDS:
            return _error(f"Unknown build: {build_id}")
        active = self._active()
        tools = self._store(active.root).installed() if active.root else []
        try:
            published, listing_error = self._published(build_id), None
        except ReleasesUnavailable as exc:
            log.error(f"Listing {build_id} releases failed: {exc}")
            published, listing_error = [], str(exc)
        rows = proton_builds.versions(build_id, published, tools)
        return {"status": "success", "problem": active.problem, "versions": [row.__dict__ for row in rows], "listing_error": listing_error}

    def install(self, build_id: str, tool_name: str) -> dict:
        """Download, verify, unpack and check a release, then move it into compatibilitytools.d in one rename.

        Anything that goes wrong leaves compatibilitytools.d as it was.
        """
        if build_id not in proton_builds.BUILDS:
            return _error(f"Unknown build: {build_id}")
        active = self._active()
        if active.root is None:
            return _problem(str(active.problem))
        try:
            release = next((r for r in self._published(build_id) if r.tool == tool_name), None)
        except ReleasesUnavailable as exc:
            return _error(str(exc))
        if release is None:
            return _error(f"{tool_name} is no longer published. Check again.")
        if release.unsupported:
            return _error(f"{tool_name} can't be installed: {release.unsupported}.")
        store = self._store(active.root)
        if any(tool.known_as(tool_name) for tool in store.installed()):
            return _error(f"{tool_name} is already installed.")
        if store.free_bytes() < proton_builds.space_needed(release.size):
            needed = proton_builds.space_needed(release.size) // 1_000_000
            return _error(f"Not enough free space: installing {tool_name} needs about {needed} MB.")

        store.clear_partial()
        try:
            stage = store.staging(tool_name)
            archive_path = stage / f"{tool_name}{proton_builds.BUILDS[build_id].extension}"
            self.download(release.url, archive_path, lambda got, total: self.report(tool_name, got, total))
            if sha256(archive_path) != release.sha256:
                return _error(f"The {tool_name} download did not match its checksum. Try again.")
            unpacked = stage / UNPACKED_DIRNAME
            archive.extract_tar(archive_path, unpacked)
            archive_path.unlink()
            missing = proton_builds.check_extracted(store.top_entries(unpacked), tool_name, *store.manifests(unpacked / tool_name))
            if missing:
                return _error(f"The {tool_name} archive {missing}; not installed.")
            store.commit(unpacked / tool_name, tool_name)
        except (ReleasesUnavailable, RuntimeError, OSError) as exc:
            log.error(f"Installing {tool_name} failed: {exc}")
            return _error(f"Installing {tool_name} failed: {exc}")
        finally:
            store.clear_partial()
        log.info(f"Installed {tool_name} into {store.tools_dir}")
        return {"status": "success", "id": tool_name, "message": f"{tool_name} is installed. Restart Steam to use it."}

    def _own_tool(self, root: Path, folder: str) -> proton_builds.Tool | str:
        tool = next((t for t in self._store(root).installed() if t.folder == folder), None)
        if tool is None:
            return f"{folder} is not installed."
        if tool.system:
            return f"{folder} is installed for every user of this device; it can't be removed here."
        return tool

    def removal(self, folder: str) -> dict:
        """The games whose user chose a build, asked before removing it: removing warns, it doesn't refuse."""
        active = self._active()
        if active.root is None:
            return _problem(str(active.problem))
        tool = self._own_tool(active.root, folder)
        if isinstance(tool, str):
            return _error(tool)
        appids, global_default = proton_builds.chosen_for(tool, proton.forced_mappings(active.root))
        return {"status": "success", "games": self._games(active.root, appids), "global_default": global_default}

    def remove(self, folder: str) -> dict:
        active = self._active()
        if active.root is None:
            return _problem(str(active.problem))
        tool = self._own_tool(active.root, folder)
        if isinstance(tool, str):
            return _error(tool)
        try:
            self._store(active.root).remove(folder)
        except (OSError, ValueError) as exc:
            return _error(f"Removing {folder} failed: {exc}")
        log.info(f"Removed {folder}")
        return {"status": "success", "message": f"{folder} is removed."}

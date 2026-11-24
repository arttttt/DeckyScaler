"""Proton builds: list, install and remove custom Proton builds in the Steam install the plugin works with.

Shaped like the OptiScaler library (installed / versions / install / removal / remove), but its own owner: a
build goes into Steam's compatibilitytools.d, is known by Steam's name for it, and Steam only sees a change
after a restart.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from deckyscaler.domain import proton_builds, steam
from deckyscaler.infrastructure import archive, proton
from deckyscaler.infrastructure import steam as steam_library
from deckyscaler.infrastructure.compat_tools_store import CompatToolsStore
from deckyscaler.infrastructure.files import read_json, replace_json, sha256
from deckyscaler.infrastructure.github_releases import Download, ListReleases, ReleasesUnavailable, Report

log = logging.getLogger(__name__)


UNPACKED_DIRNAME = "unpacked"

_PENDING = threading.Lock()
"""Each call builds its own owner, and an install's end can meet a move's: the pending moves change one at a time."""


BUSY = "Another Proton build is still being downloaded: try again once it's done."


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
        moves_file: Path,
        system_tools: Path | None = None,
    ):
        self.home = home
        self.list_releases = list_releases
        self.download = download
        self.report = report
        self.moves_file = moves_file
        """Moves an update leaves to offer once Steam restarted (the plugin restarts with it), per build."""
        self.system_tools = system_tools if system_tools is not None else proton.SYSTEM_TOOLS

    def _active(self, clients: list[tuple[Path, float]] | None = None) -> steam.ActiveRoot:
        return steam_library.active_root(self.home, steam_library.running_clients() if clients is None else clients)

    def _store(self, root: Path) -> CompatToolsStore:
        return CompatToolsStore(root / "compatibilitytools.d", self.system_tools)

    def _namer(self, root: Path) -> Callable[[list[str]], list[dict]]:
        """Names games by what the device holds, read once for every list an answer needs."""
        installed, shortcuts = steam_library.app_names(self.home), steam_library.shortcut_names(root)
        return lambda appids: [_app_json(app) for app in steam.name_apps(appids, installed, shortcuts)]

    def _pending(self) -> dict[str, proton_builds.PendingMove]:
        return proton_builds.parse_pending(read_json(self.moves_file))

    def _change_pending(self, change: Callable[[dict[str, proton_builds.PendingMove]], None]) -> None:
        with _PENDING:
            moves = self._pending()
            change(moves)
            replace_json(self.moves_file, proton_builds.pending_to_json(moves))

    def _offers(self, tools: list[proton_builds.Tool], forced, name: Callable[[list[str]], list[dict]]) -> list[dict]:
        """The moves to offer now: games still on an older build of a build whose newer one Steam lists."""
        offers = []
        for build, pending in self._pending().items():
            appids = proton_builds.still_to_move(pending, tools, forced)
            if appids:
                offers.append({
                    "build": build,
                    "target": pending.target,
                    "sources": sorted({forced.games[appid] for appid in appids}),
                    "games": name(appids),
                })
        return offers

    def clear_interrupted(self) -> None:
        """Remove what an install the plugin's stop cut short left in the active Steam's compatibilitytools.d. Its
        staging directory itself stays, so Steam needs no restart for it."""
        active = self._active()
        if active.root is not None:
            self._store(active.root).clear_when_idle()

    def installed(self, with_sizes: bool = False) -> dict:
        """Every build Steam would find, newest first, with the games whose user chose it; the device's own folders
        in compatibilitytools.d that aren't builds, to remove; and whether Steam must restart to see the builds as
        they are now. Sizing walks thousands of files per build: only when asked."""
        clients = steam_library.running_clients()
        active = self._active(clients)
        if active.root is None:
            return {"status": "success", "problem": active.problem, "tools": [], "others": [], "installed_bytes": 0,
                    "restart_needed": False, "moves": [], "unresolved": {"global": None, "tools": []}}
        store = self._store(active.root)
        forced = proton.forced_mappings(active.root)
        name = self._namer(active.root)
        tools = proton_builds.newest_first(store.installed())

        def row_of(tool: proton_builds.Tool) -> dict:
            """What every row says: its folder, its size when asked, and the games whose user chose it."""
            appids, global_default = proton_builds.chosen_for(tool, forced)
            size = store.size(tool) if with_sizes else None
            return {"id": tool.folder, "size": size, "games": name(appids), "global_default": global_default}

        rows = []
        for tool in tools:
            build = tool.build
            rows.append({
                **row_of(tool),
                "build": build.id if build else None,
                "build_label": build.label if build else None,
                "system": tool.system,
                "linked": tool.linked,
                "missing": tool.missing,
            })
        others = [row_of(tool) for tool in store.others()]
        absent = proton_builds.unresolved(forced, tools)
        unresolved = {
            "global": absent.global_tool,
            "tools": [{"tool": tool, "games": name(list(appids))} for tool, appids in absent.games],
        }
        own = (
            sum(row["size"] for row in rows if not row["system"]) + sum(row["size"] for row in others) if with_sizes else None
        )
        restart = steam.restart_needed(active.root, clients, store.changed_at())
        # Steam takes a game's move only to a build it lists, which a restart due means it doesn't yet.
        moves = [] if restart else self._offers(tools, forced, name)
        return {"status": "success", "problem": None, "tools": rows, "others": others, "installed_bytes": own,
                "restart_needed": restart, "moves": moves, "unresolved": unresolved}

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
            releases = self._published(build_id)
        except ReleasesUnavailable as exc:
            return _error(str(exc))
        release = next((r for r in releases if r.tool == tool_name), None)
        if release is None:
            return _error(f"{tool_name} is no longer published. Check again.")
        if release.unsupported:
            return _error(f"{tool_name} can't be downloaded now. Check again.")
        store = self._store(active.root)
        tools = store.installed()
        known = next((tool for tool in tools if tool.known_as(tool_name)), None)
        if known is not None and known.missing:
            if known.linked:
                return _error(
                    f"{tool_name} is a link to a build kept elsewhere, and that build isn't whole (its {known.missing} is "
                    "missing): mend it where it is kept, or take the link out of compatibilitytools.d."
                )
            return _error(
                f"{tool_name} is there but not whole (its {known.missing} is missing): remove it under Manage installed…, "
                "then download it again."
            )
        if known is not None:
            return _error(f"{tool_name} is already installed.")
        if store.taken(tool_name):
            # The build would land on what holds its name: say so before downloading, and leave clearing it to the user.
            if any(other.folder == tool_name for other in store.others()):
                return _error(f"{tool_name} is already in compatibilitytools.d, but it isn't a build. Remove it under Manage installed… first.")
            return _error(f"Something named {tool_name} is already in compatibilitytools.d, and it isn't a build. Move it out of there first.")
        if store.free_bytes() < proton_builds.space_needed(release.size):
            needed = proton_builds.space_needed(release.size) // 1_000_000
            return _error(f"Not enough free space: installing {tool_name} needs about {needed} MB.")

        with store.assembling() as free:
            if not free:
                return _error(BUSY)
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
        log.info(f"Installed {tool_name} into {store.tools_dir}")
        self._remember_move(build_id, proton_builds.pending_move(release, releases, tools, proton.forced_mappings(active.root)))
        return {"status": "success", "id": tool_name, "message": f"{tool_name} is installed. Restart Steam to use it."}

    def _remember_move(self, build_id: str, pending: proton_builds.PendingMove | None) -> None:
        """Keep the move an update leaves for after Steam's restart; the build is installed either way."""
        if pending is None:
            return
        def remember(moves: dict[str, proton_builds.PendingMove]) -> None:
            merged = proton_builds.merge(moves.get(build_id), pending)
            if merged is not None:
                moves[build_id] = merged

        try:
            self._change_pending(remember)
        except OSError as exc:
            log.warning(f"Keeping the games to move to {pending.target} failed: {exc}")

    def moved(self, target: str, appids: list[str]) -> dict:
        """These games were moved to `target`: they are offered no more."""
        def forget(moves: dict[str, proton_builds.PendingMove]) -> None:
            for build, pending in list(moves.items()):
                if pending.target == target:
                    left = proton_builds.moved(pending, appids)
                    if left is None:
                        del moves[build]
                    else:
                        moves[build] = left

        self._change_pending(forget)
        return {"status": "success"}

    def keep(self, target: str) -> dict:
        """The user keeps the games where they are: the move to `target` is offered no more."""
        def drop(moves: dict[str, proton_builds.PendingMove]) -> None:
            for build in [build for build, m in moves.items() if m.target == target]:
                del moves[build]

        self._change_pending(drop)
        return {"status": "success"}

    def games(self, tool_name: str) -> dict:
        """The games whose user chose a tool now, as Steam's config says (read again whenever Steam rewrote it)."""
        active = self._active()
        if active.root is None:
            return _problem(str(active.problem))
        tools = self._store(active.root).installed()
        tool = next((t for t in tools if t.known_as(tool_name)), proton_builds.Tool(tool_name, frozenset({tool_name.lower()})))
        appids, _global_default = proton_builds.chosen_for(tool, proton.forced_mappings(active.root))
        return {"status": "success", "games": self._namer(active.root)(appids)}

    def _own_tool(self, root: Path, folder: str) -> proton_builds.Tool | str:
        """A tool of the device's own to remove: a build, or a folder there that isn't one (it declares no names, so
        only a mapping naming its folder can name it); never a tool installed for every user, nor a link to a build
        kept elsewhere. A system tool of the same name doesn't hide the device's own."""
        store = self._store(root)
        tools = store.installed()
        own = next((t for t in [*tools, *store.others()] if t.folder == folder and not t.system), None)
        if own is not None:
            return f"{folder} is a link to a build kept elsewhere; it can't be removed here." if own.linked else own
        if any(t.folder == folder for t in tools):
            return f"{folder} is installed for every user of this device; it can't be removed here."
        return f"{folder} is not installed."

    def removal(self, folder: str) -> dict:
        """The games whose user chose a build, asked before removing it: removing warns, it doesn't refuse."""
        active = self._active()
        if active.root is None:
            return _problem(str(active.problem))
        tool = self._own_tool(active.root, folder)
        if isinstance(tool, str):
            return _error(tool)
        appids, global_default = proton_builds.chosen_for(tool, proton.forced_mappings(active.root))
        return {"status": "success", "games": self._namer(active.root)(appids), "global_default": global_default}

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

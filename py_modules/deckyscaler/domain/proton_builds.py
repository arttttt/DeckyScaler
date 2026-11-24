"""Proton builds the plugin installs into Steam's compatibilitytools.d: the builds it offers, their releases, which
installed tool is which, and whether an unpacked build is whole.

Builds are data, as the OptiScaler library's channels are. A build's tool name is its release asset's file name
without the extension: the archive's one top directory and the internal name Steam knows the tool by
(GE-Proton11-12-x86_64, proton-cachyos-11.0-20261015-slr-x86_64). Valve's own Proton is Steam's to manage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import release_assets
from .compat_tools import ForcedMappings

GE_PROTON = "ge-proton"
PROTON_CACHYOS = "proton-cachyos"
PROTON_CACHYOS_V3 = "proton-cachyos-v3"

SHOWN = 10
"""Releases offered at a time: the newest ones (installed builds stay listed regardless), as for nightly OptiScaler."""


@dataclass(frozen=True)
class Build:
    id: str
    label: str
    repository: str
    """`owner/name` whose GitHub releases publish this build."""
    tool: re.Pattern[str]
    """The build's tool names: an asset's file name without `extension`, and an installed tool's directory or
    internal name. Other architectures and variants don't match."""
    extension: str
    note: str | None = None
    """What to know before picking it."""


BUILDS = {
    GE_PROTON: Build(
        GE_PROTON,
        "GE-Proton",
        "GloriousEggroll/proton-ge-custom",
        # GE-Proton11-12-x86_64; up to GE-Proton11-3 the x86_64 build carried no suffix.
        re.compile(r"^GE-Proton\d+-\d+(?:-x86_64)?$", re.IGNORECASE),
        ".tar.gz",
    ),
    PROTON_CACHYOS: Build(
        PROTON_CACHYOS,
        "Proton-CachyOS",
        "CachyOS/proton-cachyos",
        # proton-cachyos-11.0-20261015-slr-x86_64; CachyOS advises this one ("be conservative and use x86_64").
        re.compile(r"^proton-cachyos-.+-x86_64$", re.IGNORECASE),
        ".tar.xz",
    ),
    PROTON_CACHYOS_V3: Build(
        PROTON_CACHYOS_V3,
        "Proton-CachyOS (x86_64_v3)",
        "CachyOS/proton-cachyos",
        re.compile(r"^proton-cachyos-.+-x86_64_v3$", re.IGNORECASE),
        ".tar.xz",
        "Built for newer CPUs; for experimenting.",
    ),
}


def build_of(name: str) -> Build | None:
    """The build a tool name belongs to, or None for any other tool."""
    return next((build for build in BUILDS.values() if build.tool.match(name)), None)


# ── Releases ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Release:
    """A release of a build, as the download dialog offers it."""

    tool: str
    """The tool it installs; the tag when the release has no archive of the build."""
    build: str
    tag: str
    published_at: str
    url: str
    sha256: str
    size: int
    unsupported: str | None
    """Why it can't be downloaded, or None when it can."""

    @property
    def date(self) -> str:
        """The day it was published, YYYYMMDD."""
        return release_assets.day(self.published_at)


def available(build_id: str, listing: object) -> list[Release]:
    """The newest releases of a build, newest first, each either downloadable or saying why not."""
    build = BUILDS[build_id]
    found = [_release(build, release) for release in release_assets.releases(listing, prerelease=False)]
    return release_assets.newest(found, lambda r: r.published_at, lambda r: r.tool, SHOWN)


def _tool_name(build: Build, asset: dict) -> str | None:
    name = str(asset.get("name", ""))
    if not name.endswith(build.extension):
        return None
    tool = name[: -len(build.extension)]
    return tool if build.tool.match(tool) else None


def _release(build: Build, release: dict) -> Release:
    tag = str(release.get("tag_name", ""))
    published_at = str(release.get("published_at") or "")
    matches = [(asset, tool) for asset in release.get("assets") or [] if isinstance(asset, dict) and (tool := _tool_name(build, asset))]
    if len(matches) != 1:
        reason = release_assets.SEVERAL_ARCHIVES if matches else release_assets.NO_ARCHIVE
        return Release(tag, build.id, tag, published_at, "", "", 0, reason)
    asset, tool = matches[0]
    return Release(
        tool=tool,
        build=build.id,
        tag=tag,
        published_at=published_at,
        url=str(asset.get("browser_download_url", "")),
        sha256=release_assets.sha256(asset) or "",
        size=int(asset.get("size") or 0),
        unsupported=release_assets.problem(asset, build.repository, tag),
    )


# ── Installed tools ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tool:
    """A compatibility tool in a compatibilitytools.d, whoever installed it."""

    folder: str
    names: frozenset[str]
    """The internal names its compatibilitytool.vdf declares, lowercased as Steam compares them."""
    system: bool = False
    """Installed for every user (/usr/share/steam/compatibilitytools.d): listed, never changed here."""
    modified: float = 0.0
    """When its directory last changed: unpacking keeps the archive's times, so about when the build was made."""
    linked: bool = False
    """A link to a folder kept elsewhere (a build on an SD card): listed as a tool, never removed by the plugin."""
    missing: str | None = None
    """The file its toolmanifest.vdf has Steam run, when that isn't there (a removal cut short, files deleted by
    hand): Steam lists the tool, and it can't start a game."""

    def known_as(self, name: str) -> bool:
        """Whether Steam knows the tool by `name` (a mapping's or a release's tool name)."""
        return name.lower() in self.names or name.lower() == self.folder.lower()

    @property
    def build(self) -> Build | None:
        return next((build for name in (self.folder, *sorted(self.names)) if (build := build_of(name))), None)


def newest_first(tools: list[Tool]) -> list[Tool]:
    """The device's own tools, newest first, then the system's."""
    return sorted(tools, key=lambda tool: (tool.system, -tool.modified))


def versions(build_id: str, releases: list[Release], tools: list[Tool]) -> list[release_assets.Row]:
    """The download dialog's rows for a build: its newest releases, then the build's installed tools no longer
    among them (they stay listed)."""
    def installed(name: str) -> bool:
        return any(tool.known_as(name) for tool in tools)

    rows = [
        release_assets.Row(r.tool, r.tag, r.date, release_assets.row_state(installed(r.tool), r.unsupported), r.unsupported, r.size)
        for r in releases
    ]
    listed = [r.tool for r in releases]
    rows += [
        release_assets.Row(tool.folder, tool.folder, "", release_assets.INSTALLED, None, 0)
        for tool in tools
        if tool.build == BUILDS[build_id] and not any(tool.known_as(name) for name in listed)
    ]
    return rows


def chosen_for(tool: Tool, forced: ForcedMappings) -> tuple[list[str], bool]:
    """The games whose user chose the tool, and whether it is the tool chosen for every game."""
    games = sorted(appid for appid, name in forced.games.items() if tool.known_as(name))
    return games, forced.global_tool is not None and tool.known_as(forced.global_tool)


# ── Installing ───────────────────────────────────────────────────────────────

SPACE_FACTOR = 7
"""Free space an install needs, as a multiple of the archive: the archive plus its unpacked build. Proton-CachyOS'
.tar.xz unpacks to about 4.9 times its size (347 MB → 1.69 GB), so the OptiScaler library's 5 is too little."""


def space_needed(archive_size: int) -> int:
    return archive_size * SPACE_FACTOR


def check_extracted(top_entries: list[str], tool: str, has_manifest: bool, has_toolmanifest: bool, declared: frozenset[str]) -> str | None:
    """What an unpacked archive lacks to be the build it was published as, or None when it is whole: one top
    directory named after the tool, holding the manifests Steam reads, declaring the tool's name."""
    if top_entries != [tool]:
        return f"holds {', '.join(sorted(top_entries)) or 'nothing'} instead of one {tool} directory"
    if not has_manifest:
        return "lacks compatibilitytool.vdf"
    if not has_toolmanifest:
        return "lacks toolmanifest.vdf"
    if tool.lower() not in declared:
        return f"does not declare a tool named {tool}"
    return None


# ── Moving games to a newer build ─────────────────────────────────────────────


@dataclass(frozen=True)
class PendingMove:
    """Games to offer a newer build to once Steam lists it: an update installs the newer build next to the old
    ones, and Steam sees it only after a restart, which the plugin doesn't outlive."""

    target: str
    """The newer build's tool name."""
    sources: frozenset[str]
    """Every name the older builds of the same build are known by, lowercased."""
    appids: tuple[str, ...]


def older_of_build(new: Release, releases: list[Release], tools: list[Tool]) -> list[Tool]:
    """The installed tools of `new`'s build that are older than it: released before it, or no longer among the
    newest releases at all."""
    def published(tool: Tool) -> str | None:
        return next((r.published_at for r in releases if tool.known_as(r.tool)), None)

    return [
        tool
        for tool in tools
        if tool.build == BUILDS[new.build] and ((at := published(tool)) is None or at < new.published_at)
    ]


def pending_move(new: Release, releases: list[Release], tools: list[Tool], forced: ForcedMappings) -> PendingMove | None:
    """What installing `new` leaves to offer: the games whose user chose an older build of the same build."""
    chosen = {tool: games for tool in older_of_build(new, releases, tools) if (games := chosen_for(tool, forced)[0])}
    appids = sorted({appid for games in chosen.values() for appid in games})
    if not appids:
        return None
    names = frozenset(name for tool in chosen for name in (tool.folder.lower(), *tool.names))
    return PendingMove(new.tool, names, tuple(appids))


def merge(earlier: PendingMove | None, later: PendingMove | None) -> PendingMove | None:
    """A second update before the games moved: they move to the latest build, from any of the older ones."""
    if earlier is None or later is None:
        return later or earlier
    return PendingMove(later.target, earlier.sources | later.sources, tuple(sorted({*earlier.appids, *later.appids})))


def still_to_move(pending: PendingMove, tools: list[Tool], forced: ForcedMappings) -> list[str]:
    """The games to offer the move now: still on an older build (not moved by hand meanwhile), while the newer
    build is still installed."""
    if not any(tool.known_as(pending.target) for tool in tools):
        return []
    return [appid for appid in pending.appids if forced.games.get(appid, "").lower() in pending.sources]


def moved(pending: PendingMove, appids: list[str]) -> PendingMove | None:
    """What is left once these games moved; None when nothing is."""
    left = tuple(appid for appid in pending.appids if appid not in appids)
    return PendingMove(pending.target, pending.sources, left) if left else None


def pending_to_json(moves: dict[str, PendingMove]) -> dict:
    return {build: {"target": m.target, "sources": sorted(m.sources), "appids": list(m.appids)} for build, m in moves.items()}


def parse_pending(data: object) -> dict[str, PendingMove]:
    """The pending moves a file holds, per build; anything that isn't one is left out."""
    moves: dict[str, PendingMove] = {}
    for build, entry in (data.items() if isinstance(data, dict) else []):
        if build not in BUILDS or not isinstance(entry, dict):
            continue
        target, sources, appids = entry.get("target"), entry.get("sources"), entry.get("appids")
        if isinstance(target, str) and isinstance(sources, list) and isinstance(appids, list) and appids:
            moves[build] = PendingMove(target, frozenset(str(s).lower() for s in sources), tuple(str(a) for a in appids))
    return moves

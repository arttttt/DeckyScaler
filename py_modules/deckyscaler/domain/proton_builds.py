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

NO_ASSET = "no archive for this build"
SEVERAL_ASSETS = "more than one archive"


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
        return self.published_at[:10].replace("-", "")


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
        return Release(tag, build.id, tag, published_at, "", "", 0, SEVERAL_ASSETS if matches else NO_ASSET)
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

    def known_as(self, name: str) -> bool:
        """Whether Steam knows the tool by `name` (a mapping's or a release's tool name)."""
        return name.lower() in self.names or name.lower() == self.folder.lower()

    @property
    def build(self) -> Build | None:
        return next((build for name in (self.folder, *sorted(self.names)) if (build := build_of(name))), None)


INSTALLED = "installed"
AVAILABLE = "available"
UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Row:
    """A release in the download dialog."""

    id: str
    version: str
    date: str
    state: str
    reason: str | None
    size: int


def versions(build_id: str, releases: list[Release], tools: list[Tool]) -> list[Row]:
    """The download dialog's rows for a build: its newest releases, then the build's installed tools no longer
    among them (they stay listed)."""
    def installed(name: str) -> bool:
        return any(tool.known_as(name) for tool in tools)

    rows = [
        Row(r.tool, r.tag, r.date, INSTALLED if installed(r.tool) else UNSUPPORTED if r.unsupported else AVAILABLE, r.unsupported, r.size)
        for r in releases
    ]
    listed = [r.tool for r in releases]
    rows += [
        Row(tool.folder, tool.folder, "", INSTALLED, None, 0)
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

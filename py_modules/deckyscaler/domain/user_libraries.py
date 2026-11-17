"""Libraries the user adds to games beside OptiScaler 10: what OptiScaler takes, how a library is recognised,
how the device keeps one, and where one can be downloaded.

OptiScaler 10 takes two kinds of library. A provider is a folder `<name>/<kind>/` with a DLL in it, copied into
OptiScaler's `custom/` folder and selected by its name (ANR is a `dlssg` provider). A DLL is one of the files
OptiScaler loads itself (libxess.dll, amd_fidelityfx_upscaler_dx12.dll…), pointed at by its key in the ini's
[Libraries] section. The tables below are the only place that names either: a new file or kind is a row.

A library serves slots: the upscaler, frame generation. Picked for a slot, its files go into the game and the
ini keys that select and find them are set (domain/library_placement).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from . import release_assets
from .settings_layers import Key

UPSCALER = "upscaler"
FRAME_GENERATION = "frame-generation"
SLOTS = (UPSCALER, FRAME_GENERATION)

DX11: Key = ("Upscalers", "Dx11Upscaler")
DX12: Key = ("Upscalers", "Dx12Upscaler")
VULKAN: Key = ("Upscalers", "VulkanUpscaler")
RAY_RECONSTRUCTION: Key = ("Upscalers", "RRUpscaler")
FG_INPUT: Key = ("FrameGen", "FGInput")
FG_REPLACEMENT: Key = ("FrameGen", "FGNvngxReplacement")
FSR_FG_PROVIDER: Key = ("FSRFG", "Provider")
LIBRARIES = "Libraries"
"""The ini section of the per-DLL path keys."""


# ── What OptiScaler takes ────────────────────────────────────────────────────


@dataclass(frozen=True)
class KnownDll:
    name: str
    """The file name, lowercase."""
    path_key: str
    """Its key in [Libraries]."""
    slots: frozenset[str]
    """The slots it serves; none for a file that only comes along with its library."""
    upscaler: tuple[tuple[Key, str], ...] = ()
    """What picking it as the upscaler selects, per API (OptiScaler.ini [Upscalers]: DX11 and Vulkan run the
    DX12 FFX and XeSS libraries through their DX12 bridges, `_12`)."""


_FFX_DX12 = ((DX12, "ffx"), (DX11, "ffx_12"), (VULKAN, "ffx_12"))

DLLS: tuple[KnownDll, ...] = (
    # The order is the priority when two files of a library select the same key.
    KnownDll("libxess.dll", "XeSSPath", frozenset({UPSCALER}), ((DX12, "xess"), (VULKAN, "xess"), (DX11, "xess_12"))),
    KnownDll("libxess_dx11.dll", "XeSSDx11Path", frozenset({UPSCALER}), ((DX11, "xess"),)),
    KnownDll("amd_fidelityfx_upscaler_dx12.dll", "FfxDx12SRPath", frozenset({UPSCALER}), _FFX_DX12),
    KnownDll("amd_fidelityfx_dx12.dll", "FfxDx12Path", frozenset({UPSCALER, FRAME_GENERATION}), _FFX_DX12),
    KnownDll("amd_fidelityfx_loader_dx12.dll", "FfxDx12Path", frozenset({UPSCALER, FRAME_GENERATION}), _FFX_DX12),
    KnownDll("amd_fidelityfx_upscaler_vk.dll", "FfxVkSRPath", frozenset({UPSCALER}), ((VULKAN, "ffx"),)),
    KnownDll("amd_fidelityfx_vk.dll", "FfxVkPath", frozenset({UPSCALER, FRAME_GENERATION}), ((VULKAN, "ffx"),)),
    KnownDll("amd_fidelityfx_loader_vk.dll", "FfxVkPath", frozenset({UPSCALER, FRAME_GENERATION}), ((VULKAN, "ffx"),)),
    KnownDll("nvngx_dlss.dll", "NvngxDlssPath", frozenset({UPSCALER}), ((DX12, "dlss"), (VULKAN, "dlss"), (DX11, "dlss"))),
    KnownDll("amd_fidelityfx_framegeneration_dx12.dll", "FfxDx12FGPath", frozenset({FRAME_GENERATION})),
    KnownDll("amd_fidelityfx_framegeneration_vk.dll", "FfxVkFGPath", frozenset({FRAME_GENERATION})),
    KnownDll("libxess_fg.dll", "XeFGPath", frozenset({FRAME_GENERATION})),
    KnownDll("libxell.dll", "XeLLPath", frozenset({FRAME_GENERATION})),
    KnownDll("amd_fidelityfx_denoiser_dx12.dll", "FfxDx12RRPath", frozenset()),
    KnownDll("amd_fidelityfx_radiancecache_dx12.dll", "FfxDx12RCPath", frozenset()),
)
_DLLS = {dll.name: dll for dll in DLLS}


@dataclass(frozen=True)
class ProviderKind:
    name: str
    """The folder under the provider's own that holds its DLL."""
    slot: str
    selects: tuple[Key, ...]
    """The keys set to the provider's name (OptiScaler.ini: "or the name of a custom …")."""
    sets: tuple[tuple[Key, str], ...] = ()
    """Other keys the kind needs, with their values."""


KINDS: tuple[ProviderKind, ...] = (
    ProviderKind("ffx", UPSCALER, (DX12, DX11, VULKAN)),
    ProviderKind("ffx_vk", UPSCALER, (VULKAN,)),
    ProviderKind("dlss", UPSCALER, (DX12, DX11, VULKAN)),
    # Ray reconstruction is part of upscaling: a dlssd provider is picked as the upscaler.
    ProviderKind("dlssd", UPSCALER, (RAY_RECONSTRUCTION,)),
    # OptiScaler reads FGNvngxReplacement only with nvngxfg input (Config.cpp, canUseNvngxReplacement).
    ProviderKind("dlssg", FRAME_GENERATION, (FG_REPLACEMENT,), ((FG_INPUT, "nvngxfg"),)),
    ProviderKind("ffx_fg", FRAME_GENERATION, (FSR_FG_PROVIDER,)),
    ProviderKind("ffx_fg_vk", FRAME_GENERATION, (FSR_FG_PROVIDER,)),
)
_KINDS = {kind.name: kind for kind in KINDS}

RESERVED_NAMES = frozenset({
    "auto", "default", "none", "xess", "xess_12", "fsr21", "fsr22", "fsr31", "fsr21_12", "fsr22_12", "ffx", "ffx_12",
    "dlss", "dlssd", "nukems", "arturs", "combo", *_KINDS,
})
"""Words OptiScaler reads as its own values in the keys a provider's name goes into: a provider can't be named so."""


def known_dll(name: str) -> KnownDll | None:
    return _DLLS.get(name.lower())


def kind(name: str) -> ProviderKind | None:
    return _KINDS.get(name)


# ── Recognising a library ────────────────────────────────────────────────────

NOTHING_KNOWN = "nothing-known"
RESERVED_NAME = "reserved-name"
ALREADY_ADDED = "already-added"
"""Why something can't be added, as kinds the frontend words."""


@dataclass(frozen=True)
class Provider:
    name: str
    kinds: tuple[str, ...]
    folder: str
    """Where its folder is among the library's files."""


@dataclass(frozen=True)
class Dll:
    name: str
    """The table's name of the file (KnownDll.name)."""
    path: str
    """Where it is among the library's files."""


@dataclass(frozen=True)
class Contents:
    providers: tuple[Provider, ...]
    dlls: tuple[Dll, ...]
    files: tuple[str, ...]
    """What of the picked files makes the library: its providers' folders and its DLLs."""


def recognize(paths: frozenset[str]) -> Contents | str:
    """What a zip's members, a folder's files or one DLL hold (paths with '/'): providers, then known DLLs outside
    their folders, the one nearest the top for each name. Anything else in them is left out. The reason as a kind
    when nothing is a library."""
    folders: dict[str, set[str]] = {}
    for path in paths:
        parts = PurePosixPath(path).parts
        if len(parts) >= 3 and parts[-1].lower().endswith(".dll") and parts[-2] in _KINDS:
            folders.setdefault("/".join(parts[:-2]), set()).add(parts[-2])
    providers: dict[str, Provider] = {}
    for folder in sorted(folders, key=lambda f: (f.count("/"), f)):
        name = PurePosixPath(folder).name
        providers.setdefault(name, Provider(name, tuple(k.name for k in KINDS if k.name in folders[folder]), folder))
    if any(name.lower() in RESERVED_NAMES for name in providers):
        return RESERVED_NAME

    def in_provider(path: str) -> bool:
        return any(path.startswith(f"{provider.folder}/") for provider in providers.values())

    dlls: dict[str, Dll] = {}
    for path in sorted((p for p in paths if not in_provider(p)), key=lambda p: (p.count("/"), p)):
        known = known_dll(PurePosixPath(path).name)
        if known is not None:
            dlls.setdefault(known.name, Dll(known.name, path))
    if not _slots(tuple(providers.values()), tuple(dlls.values())):
        return NOTHING_KNOWN
    kept = sorted(p for p in paths if in_provider(p)) + sorted(dll.path for dll in dlls.values())
    return Contents(
        tuple(providers[name] for name in sorted(providers)),
        tuple(dll for known in DLLS if (dll := dlls.get(known.name))),
        tuple(kept),
    )


def _slots(providers: tuple[Provider, ...], dlls: tuple[Dll, ...]) -> tuple[str, ...]:
    """The slots providers and DLLs serve, in SLOTS order."""
    served = {_KINDS[k].slot for provider in providers for k in provider.kinds}
    served |= {slot for dll in dlls for slot in _DLLS[dll.name].slots}
    return tuple(slot for slot in SLOTS if slot in served)


# ── A library on the device ──────────────────────────────────────────────────

MAX_BYTES = 1_000_000_000
"""The most a library may take on the device: what is kept of a zip, a folder or a download is refused past it
(a library is DLLs and their data: ANR's is about 6 MB, Intel's XeSS DLLs well under 100 MB)."""

SPACE_FACTOR = 4
"""Free space a download needs, as a multiple of the zip: the zip, and what it unpacks to (ANR's 3.4 MB zip unpacks
to 5.7 MB)."""


def space_needed(download_size: int) -> int:
    return download_size * SPACE_FACTOR

DOWNLOADED = "downloaded"
YOUR_FILE = "file"
ENTRY_FILENAME = "entry.json"
FILES_DIRNAME = "files"
"""libraries/<id>/files holds the library's files as they were picked; libraries/<id>/entry.json describes it."""


@dataclass(frozen=True)
class Library:
    id: str
    name: str
    version: str | None
    origin: str
    """DOWNLOADED or YOUR_FILE."""
    source: str | None
    """The source it was downloaded from; None for the user's own file."""
    providers: tuple[Provider, ...]
    dlls: tuple[Dll, ...]
    files: tuple[str, ...]
    """Every file it keeps, relative to its files' directory: its providers' folders and its DLLs."""
    settings: tuple[tuple[Key, str], ...]
    """Other keys its source sets along with it (ANR's own installer's)."""
    added_at: str

    @property
    def label(self) -> str:
        """What the plugin calls it: its name and version."""
        return f"{self.name} {self.version}" if self.version else self.name

    @property
    def slots(self) -> tuple[str, ...]:
        return _slots(self.providers, self.dlls)

    @property
    def turns_on(self) -> tuple[str, ...]:
        """The slots picking it switches on by itself: a provider is selected by name, a DLL picked as the upscaler
        selects its upscaler. A frame generation DLL is only pointed at: OptiScaler's FG settings turn it on."""
        selecting = {_KINDS[k].slot for provider in self.providers for k in provider.kinds}
        if any(_DLLS[dll.name].upscaler for dll in self.dlls):
            selecting.add(UPSCALER)
        return tuple(slot for slot in self.slots if slot in selecting)


def library_json(library: Library, size: int, games: list[str]) -> dict:
    """A library as the plugin's pages list it: `size` its bytes on the device, `games` those whose patch placed it."""
    return {
        "id": library.id,
        "label": library.label,
        "origin": library.origin,
        "slots": list(library.slots),
        "turns_on": list(library.turns_on),
        "size": size,
        "games": games,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def added(
    contents: Contents, picked: str, version: str | None, taken: set[str], added_at: str
) -> Library | str:
    """A library made of what the user picked (`picked` is the file or folder name; `version` a lone DLL's file
    version): named after its one provider or its one DLL, else after what was picked. ALREADY_ADDED when the
    device has a library of that name and version."""
    if len(contents.providers) == 1 and not contents.dlls:
        name = contents.providers[0].name
    elif len(contents.dlls) == 1 and not contents.providers:
        name = PurePosixPath(contents.dlls[0].path).name
    else:
        name = re.sub(r"\.zip$", "", PurePosixPath(picked).name, flags=re.IGNORECASE)
    lone_dll = len(contents.dlls) == 1 and not contents.providers
    library_version = version if lone_dll else None
    library_id = _slug(f"{name} {library_version or ''}")
    if library_id in taken:
        return ALREADY_ADDED
    return Library(
        library_id, name, library_version, YOUR_FILE, None, contents.providers, contents.dlls, contents.files, (), added_at
    )


def entry_json(library: Library) -> dict:
    return {
        "id": library.id,
        "name": library.name,
        "version": library.version,
        "origin": library.origin,
        "source": library.source,
        "providers": [{"name": p.name, "kinds": list(p.kinds), "folder": p.folder} for p in library.providers],
        "dlls": [{"name": d.name, "path": d.path} for d in library.dlls],
        "files": list(library.files),
        "settings": [{"section": section, "key": key, "value": value} for (section, key), value in library.settings],
        "added_at": library.added_at,
    }


def _items(data: dict, key: str) -> list:
    value = data[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} isn't a list")
    return value


def parse_entry(data: object) -> Library | None:
    """An entry.json's library, or None when the file isn't one (the directory is then not a library)."""
    if not isinstance(data, dict):
        return None
    try:
        providers = tuple(
            Provider(str(p["name"]), tuple(str(k) for k in p["kinds"] if str(k) in _KINDS), str(p["folder"]))
            for p in _items(data, "providers")
        )
        dlls = tuple(Dll(str(d["name"]), str(d["path"])) for d in _items(data, "dlls") if str(d["name"]) in _DLLS)
        files = tuple(str(f) for f in _items(data, "files"))
        settings = tuple(((str(s["section"]), str(s["key"])), str(s["value"])) for s in _items(data, "settings"))
        library = Library(
            str(data["id"]), str(data["name"]), None if data["version"] is None else str(data["version"]),
            str(data["origin"]), None if data["source"] is None else str(data["source"]), providers, dlls, files,
            settings, str(data["added_at"]),
        )
    except (KeyError, TypeError):
        return None
    return library if library.slots else None


# ── Where libraries can be downloaded ────────────────────────────────────────

ANR = "anr"

SHOWN = 10
"""Releases offered at a time: the newest ones (downloaded ones stay listed regardless)."""


@dataclass(frozen=True)
class Source:
    id: str
    label: str
    repository: str
    asset: re.Pattern[str]
    """The asset to download; its group is the version."""
    settings: tuple[tuple[Key, str], ...] = ()
    """Other keys set along with the library, as the project's own installer sets them."""


SOURCES = {
    ANR: Source(
        ANR,
        "Apex Neural Rendering FG",
        "apex-compute/ANR",
        # anr-fg-V.B19-addon.zip: the frame generation provider alone (the -full zip carries its own OptiScaler).
        re.compile(r"^anr-fg-(V\.B\d+)-addon\.zip$"),
        # install.sh: "ANR FG draws the HUD over the HUD-less color; keep OptiScaler from stripping it".
        ((("FrameGen", "DisableHudless"), "false"),),
    ),
}


def sources_json() -> list[dict]:
    """The sources the download dialog offers."""
    return [{"id": source.id, "label": source.label} for source in SOURCES.values()]


@dataclass(frozen=True)
class Release:
    id: str
    source: str
    version: str
    published_at: str
    url: str
    sha256: str
    size: int
    unsupported: str | None
    """Why it can't be downloaded, or None when it can."""


def release_id(source: str, version: str) -> str:
    return _slug(f"{source} {version}")


def releases(source_id: str, listing: object) -> list[Release]:
    """A source's newest releases, each either downloadable or saying why not."""
    source = SOURCES[source_id]
    found = [_release(source, release) for release in release_assets.releases(listing, prerelease=False)]
    return release_assets.newest(found, lambda r: r.published_at, lambda r: r.id, SHOWN)


def _release(source: Source, release: dict) -> Release:
    assets = [a for a in release.get("assets") or [] if isinstance(a, dict)]
    matches = [(a, m) for a in assets if (m := source.asset.match(str(a.get("name", ""))))]
    tag = str(release.get("tag_name", ""))
    published_at = str(release.get("published_at") or "")
    if len(matches) != 1:
        reason = release_assets.SEVERAL_ARCHIVES if matches else release_assets.NO_ARCHIVE
        return Release(release_id(source.id, tag), source.id, tag, published_at, "", "", 0, reason)
    asset, match = matches[0]
    return Release(
        id=release_id(source.id, match.group(1)),
        source=source.id,
        version=match.group(1),
        published_at=published_at,
        url=str(asset.get("browser_download_url", "")),
        sha256=release_assets.sha256(asset) or "",
        size=int(asset.get("size") or 0),
        unsupported=release_assets.problem(asset, source.repository, tag),
    )


def downloaded(release: Release, contents: Contents, added_at: str) -> Library:
    """The library a downloaded release becomes."""
    source = SOURCES[release.source]
    return Library(
        release.id, source.label, release.version, DOWNLOADED, source.id, contents.providers, contents.dlls,
        contents.files, source.settings, added_at,
    )


def rows(
    source_id: str, releases_: list[Release], installed: list[Library], sizes: dict[str, int]
) -> list[release_assets.Row]:
    """A source's download dialog rows: its newest releases, then those downloaded from it no longer among them."""
    installed_ids = {library.id for library in installed}
    listed = [
        release_assets.Row(
            r.id, r.version, release_assets.day(r.published_at),
            release_assets.row_state(r.id in installed_ids, r.unsupported), r.unsupported,
            sizes.get(r.id, r.size) if r.id in installed_ids else r.size,
        )
        for r in releases_
    ]
    listed_ids = {r.id for r in releases_}
    listed += [
        release_assets.Row(library.id, library.version or "", "", release_assets.INSTALLED, None, sizes.get(library.id, 0))
        for library in installed
        if library.source == source_id and library.id not in listed_ids
    ]
    return listed

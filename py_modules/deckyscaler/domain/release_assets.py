"""GitHub releases and their assets: which releases a listing offers, in what order, and whether an asset can be
downloaded. The OptiScaler library, Proton builds and the plugin's own updates all read releases this way."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypeVar

_SHA256_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")

# Why a release can't be downloaded, as kinds the frontend words (presentation/releases.ts).
UPLOADING = "uploading"
NO_CHECKSUM = "no-checksum"
ELSEWHERE = "elsewhere"
NO_ARCHIVE = "no-archive"
"""No asset of the release is an archive the plugin reads."""
SEVERAL_ARCHIVES = "several-archives"
"""More than one asset could be the archive: which one is meant can't be told."""


def sha256(asset: dict) -> str | None:
    """The asset's sha256 from GitHub's `digest` ("sha256:<hex>"); None when it has no usable one."""
    match = _SHA256_DIGEST.match(str(asset.get("digest", "")))
    return match.group(1) if match else None


def download_url(repository: str, tag: str, name: str) -> str:
    """Where GitHub serves a release's asset from the repository's own release downloads."""
    return f"https://github.com/{repository}/releases/download/{tag}/{name}"


def problem(asset: dict, repository: str, tag: str) -> str | None:
    """Why an asset can't be downloaded, or None when it can: it is fully uploaded, has a sha256 to check the
    download against, and is served from the release itself."""
    if asset.get("state") != "uploaded":
        return UPLOADING
    if sha256(asset) is None:
        return NO_CHECKSUM
    if str(asset.get("browser_download_url", "")) != download_url(repository, tag, str(asset.get("name", ""))):
        return ELSEWHERE
    return None


def releases(listing: object, prerelease: bool) -> list[dict]:
    """The published releases of one kind (prereleases or not) in a release list; drafts and anything that
    isn't a release are left out."""
    return [
        release
        for release in (listing if isinstance(listing, list) else [])
        if isinstance(release, dict) and not release.get("draft") and bool(release.get("prerelease")) == prerelease
    ]


T = TypeVar("T")


def newest(items: list[T], published_at: Callable[[T], str], identity: Callable[[T], str], shown: int | None) -> list[T]:
    """Newest first, whatever order GitHub sent; something released twice (a fixed re-upload as a new release)
    is offered once, from the newest release; at most `shown` of them when there is a limit."""
    ordered = sorted(items, key=published_at, reverse=True)
    kept: list[T] = []
    seen: set[str] = set()
    for item in ordered:
        if identity(item) not in seen:
            kept.append(item)
            seen.add(identity(item))
    return kept if shown is None else kept[:shown]

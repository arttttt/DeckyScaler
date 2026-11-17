import pytest

from deckyscaler.domain import release_assets

HEX = "575cb4df866116093df75af607e37fd70e10f5163e0f23fd5c804142e80ef0ad"


def test_the_sha256_comes_from_githubs_digest():
    assert release_assets.sha256({"digest": f"sha256:{HEX}"}) == HEX


@pytest.mark.parametrize("asset", [{}, {"digest": None}, {"digest": f"md5:{HEX}"}, {"digest": f"sha256:{HEX[:-1]}"},
                                   {"digest": f"sha256:{HEX.upper()}"}])
def test_anything_else_is_no_usable_checksum(asset):
    assert release_assets.sha256(asset) is None


# ── whether an asset can be downloaded ───────────────────────────────────────

REPO, TAG, NAME = "owner/repo", "v1", "build.tar.gz"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{NAME}"


def asset(**changes) -> dict:
    return {"name": NAME, "state": "uploaded", "digest": f"sha256:{HEX}", "browser_download_url": URL} | changes


def test_an_uploaded_checksummed_asset_of_the_release_itself_can_be_downloaded():
    assert release_assets.download_url(REPO, TAG, NAME) == URL
    assert release_assets.problem(asset(), REPO, TAG) is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"state": "starter"}, release_assets.UPLOADING),
        ({"state": None}, release_assets.UPLOADING),
        ({"digest": None}, release_assets.NO_CHECKSUM),
        ({"digest": f"md5:{HEX}"}, release_assets.NO_CHECKSUM),
        ({"browser_download_url": "https://example.com/build.tar.gz"}, release_assets.ELSEWHERE),
        ({"browser_download_url": f"https://github.com/other/repo/releases/download/{TAG}/{NAME}"}, release_assets.ELSEWHERE),
        ({"name": "other.tar.gz"}, release_assets.ELSEWHERE),  # the URL serves another file than the asset says
        # several problems: the first in upload → checksum → origin order
        ({"state": "starter", "digest": None, "browser_download_url": "x"}, release_assets.UPLOADING),
        ({"digest": None, "browser_download_url": "x"}, release_assets.NO_CHECKSUM),
    ],
)
def test_anything_else_says_why_it_cant(changes, reason):
    assert release_assets.problem(asset(**changes), REPO, TAG) == reason


# ── which releases a listing offers ──────────────────────────────────────────


def release(tag: str, published_at: str, prerelease: bool = False, draft: bool = False) -> dict:
    return {"tag_name": tag, "published_at": published_at, "prerelease": prerelease, "draft": draft}


def test_a_listing_offers_the_published_releases_of_one_kind():
    listing = [release("a", "1"), release("b", "2", prerelease=True), release("c", "3", draft=True), "junk", release("d", "4")]

    assert [r["tag_name"] for r in release_assets.releases(listing, prerelease=False)] == ["a", "d"]
    assert [r["tag_name"] for r in release_assets.releases(listing, prerelease=True)] == ["b"]
    assert release_assets.releases({"message": "API rate limit exceeded"}, prerelease=False) == []


def test_releases_come_newest_first_once_each_and_up_to_a_limit():
    items = [("x", "2026-01-02"), ("y", "2026-01-05"), ("x", "2026-01-04"), ("z", "2026-01-01"), ("w", "2026-01-03")]
    published_at, identity = (lambda item: item[1]), (lambda item: item[0])

    assert release_assets.newest(items, published_at, identity, None) == [
        ("y", "2026-01-05"), ("x", "2026-01-04"), ("w", "2026-01-03"), ("z", "2026-01-01")
    ]
    assert release_assets.newest(items, published_at, identity, 2) == [("y", "2026-01-05"), ("x", "2026-01-04")]
    assert release_assets.newest([], published_at, identity, 10) == []


def test_the_frontend_words_every_reason_the_backend_gives():
    import re

    from conftest import REPO_ROOT
    from deckyscaler.domain import library

    reasons = {release_assets.UPLOADING, release_assets.NO_CHECKSUM, release_assets.ELSEWHERE, release_assets.NO_ARCHIVE,
               release_assets.SEVERAL_ARCHIVES, library.UNKNOWN_FAMILY}
    wording = (REPO_ROOT / "src" / "presentation" / "releases.ts").read_text()
    table = wording[wording.index("const REASONS") : wording.index("};", wording.index("const REASONS"))]

    assert set(re.findall(r'^\s*"?([a-z-]+)"?:', table, re.MULTILINE)) == reasons


def test_a_dialog_says_a_release_is_on_the_device_else_whether_it_can_be_downloaded():
    assert release_assets.row_state(True, release_assets.UPLOADING) == release_assets.INSTALLED
    assert release_assets.row_state(False, release_assets.UPLOADING) == release_assets.UNSUPPORTED
    assert release_assets.row_state(False, None) == release_assets.AVAILABLE


def test_a_release_is_dated_by_the_day_github_published_it():
    assert release_assets.day("2026-11-17T00:20:54Z") == "20261117"

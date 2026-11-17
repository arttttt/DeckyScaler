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

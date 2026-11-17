"""Proton builds: which builds and releases are offered, which installed tool is which, whether an unpacked build
is whole (unit)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from deckyscaler.domain import proton_builds as pb
from deckyscaler.domain.compat_tools import ForcedMappings

FIXTURES = Path(__file__).parent / "fixtures"


def ge() -> list:
    return json.loads((FIXTURES / "ge_proton.json").read_text())


def cachyos() -> list:
    return json.loads((FIXTURES / "proton_cachyos.json").read_text())


# ── which releases are offered ───────────────────────────────────────────────


def test_ge_offers_its_ten_newest_x86_64_releases_newest_first():
    releases = pb.available(pb.GE_PROTON, ge())

    assert [r.tool for r in releases] == [
        "GE-Proton11-12-x86_64", "GE-Proton11-11-x86_64", "GE-Proton11-10-x86_64", "GE-Proton11-9-x86_64",
        "GE-Proton11-8-x86_64", "GE-Proton11-7-x86_64", "GE-Proton11-6-x86_64", "GE-Proton11-5-x86_64",
        "GE-Proton11-4-x86_64", "GE-Proton11-3",  # before 11-4 the x86_64 archive had no suffix
    ]
    newest = releases[0]
    assert (newest.tag, newest.date, newest.size, newest.unsupported) == ("GE-Proton11-12", "20261103", 566859228, None)
    assert newest.url == (
        "https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton11-12/GE-Proton11-12-x86_64.tar.gz"
    )
    assert newest.sha256 == "0595159e417c3dbbfb7cc3ae0d3ed15a617cc607aa23ef756ea79029d7af5d70"


@pytest.mark.parametrize(
    ("build_id", "tool"),
    [
        (pb.PROTON_CACHYOS, "proton-cachyos-11.0-20261015-slr-x86_64"),
        (pb.PROTON_CACHYOS_V3, "proton-cachyos-11.0-20261015-slr-x86_64_v3"),
    ],
)
def test_each_cachyos_variant_is_a_build_of_its_own_and_arm_is_never_offered(build_id, tool):
    releases = pb.available(build_id, cachyos())

    assert releases[0].tool == tool and releases[0].unsupported is None
    assert all(pb.BUILDS[build_id].tool.match(r.tool) for r in releases)
    assert not any("arm64" in r.tool for r in releases)


def test_a_release_without_a_downloadable_archive_says_why_and_the_older_ones_stay_downloadable():
    listing = ge()
    listing[0]["assets"] = [a | {"state": "starter"} if a["name"].endswith("x86_64.tar.gz") else a for a in listing[0]["assets"]]
    listing[1]["assets"] = [a for a in listing[1]["assets"] if "x86_64" not in a["name"]]
    listing[2]["assets"].append(copy.deepcopy(next(a for a in listing[2]["assets"] if a["name"].endswith("x86_64.tar.gz"))))

    releases = pb.available(pb.GE_PROTON, listing)

    assert [(r.tool, r.unsupported) for r in releases[:4]] == [
        ("GE-Proton11-12-x86_64", "still uploading"),
        ("GE-Proton11-11", pb.NO_ASSET),
        ("GE-Proton11-10", pb.SEVERAL_ASSETS),
        ("GE-Proton11-9-x86_64", None),
    ]


def test_drafts_prereleases_and_junk_are_not_offered():
    listing = ge()
    listing[0]["draft"] = True
    listing[1]["prerelease"] = True

    tools = [r.tool for r in pb.available(pb.GE_PROTON, listing)]

    assert tools[0] == "GE-Proton11-10-x86_64"
    assert pb.available(pb.GE_PROTON, {"message": "API rate limit exceeded"}) == []


# ── which installed tool is which ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "build"),
    [
        ("GE-Proton11-12-x86_64", pb.GE_PROTON),
        ("ge-proton11-12-x86_64", pb.GE_PROTON),  # Steam compares names case-insensitively
        ("GE-Proton10-34", pb.GE_PROTON),
        ("GE-Proton11-12-aarch64", None),
        ("GE-Proton11-60-x86_64", pb.GE_PROTON),
        ("proton-cachyos-11.0-20261015-slr-x86_64", pb.PROTON_CACHYOS),
        ("proton-cachyos-10.0-sunset-slr-x86_64", pb.PROTON_CACHYOS),
        ("proton-cachyos-11.0-20261015-slr-x86_64_v3", pb.PROTON_CACHYOS_V3),
        ("proton-cachyos-11.0-20261015-slr-arm64", None),
        ("Proton-EM-10.0-37", None),
        ("proton_experimental", None),
    ],
)
def test_a_tool_belongs_to_the_build_its_name_matches(name, build):
    found = pb.build_of(name)

    assert (found.id if found else None) == build


def test_a_tool_is_known_by_its_folder_or_any_name_it_declares():
    tool = pb.Tool("GE-Proton11-12-x86_64", frozenset({"ge-proton11-12-x86_64"}))
    renamed = pb.Tool("my-proton", frozenset({"ge-proton11-11-x86_64"}))

    assert tool.known_as("GE-Proton11-12-x86_64") and tool.known_as("ge-proton11-12-x86_64")
    assert not tool.known_as("GE-Proton11-1")  # exact names, not prefixes
    assert renamed.known_as("GE-Proton11-11-x86_64") and renamed.known_as("MY-PROTON")
    assert renamed.build == pb.BUILDS[pb.GE_PROTON]
    assert pb.Tool("Proton-EM-10.0-37", frozenset({"proton-em-10.0-37"})).build is None


# ── the download dialog's rows ───────────────────────────────────────────────


def tool(name: str, system: bool = False) -> pb.Tool:
    return pb.Tool(name, frozenset({name.lower()}), system)


def test_releases_say_whether_they_are_installed_and_installed_builds_stay_listed():
    listing = ge()
    listing[1]["assets"] = []
    releases = pb.available(pb.GE_PROTON, listing)
    installed = [tool("GE-Proton11-12-x86_64"), tool("GE-Proton10-34"), tool("proton-cachyos-11.0-20261015-slr-x86_64")]

    rows = pb.versions(pb.GE_PROTON, releases, installed)

    assert rows[0] == pb.Row("GE-Proton11-12-x86_64", "GE-Proton11-12", "20261103", pb.INSTALLED, None, 566859228)
    assert rows[1] == pb.Row("GE-Proton11-11", "GE-Proton11-11", "20261019", pb.UNSUPPORTED, pb.NO_ASSET, 0)
    assert rows[2].state == pb.AVAILABLE
    assert rows[-1] == pb.Row("GE-Proton10-34", "GE-Proton10-34", "", pb.INSTALLED, None, 0)  # fell out of the ten
    assert len(rows) == len(releases) + 1  # the CachyOS tool is another build's


# ── who uses a tool ──────────────────────────────────────────────────────────


def test_a_tool_is_used_by_the_games_whose_user_chose_it_and_may_be_the_one_for_every_game():
    forced = ForcedMappings({"730": "GE-Proton11-12-x86_64", "570": "ge-proton11-12-x86_64", "440": "GE-Proton11-11-x86_64"},
                            "GE-Proton11-12-x86_64")

    assert pb.chosen_for(tool("GE-Proton11-12-x86_64"), forced) == (["570", "730"], True)
    assert pb.chosen_for(tool("GE-Proton11-11-x86_64"), forced) == (["440"], False)
    assert pb.chosen_for(tool("GE-Proton11-11-x86_64"), ForcedMappings({}, None)) == ([], False)


# ── installing ───────────────────────────────────────────────────────────────


def test_an_install_needs_room_for_the_archive_and_the_unpacked_build():
    # Proton-CachyOS: 347 MB of .tar.xz unpacks to 1.69 GB, so the archive and the build together take 5.9 times it.
    assert pb.space_needed(347_335_620) >= 347_335_620 + 1_690_000_000


TOOL = "GE-Proton11-12-x86_64"


@pytest.mark.parametrize(
    ("top", "manifest", "toolmanifest", "declared", "problem"),
    [
        ([TOOL], True, True, frozenset({TOOL.lower()}), None),
        ([], True, True, frozenset({TOOL.lower()}), f"holds nothing instead of one {TOOL} directory"),
        ([TOOL, "extra"], True, True, frozenset({TOOL.lower()}), f"holds {TOOL}, extra instead of one {TOOL} directory"),
        (["GE-Proton11-12"], True, True, frozenset({TOOL.lower()}), f"holds GE-Proton11-12 instead of one {TOOL} directory"),
        ([TOOL], False, True, frozenset({TOOL.lower()}), "lacks compatibilitytool.vdf"),
        ([TOOL], True, False, frozenset({TOOL.lower()}), "lacks toolmanifest.vdf"),
        ([TOOL], True, True, frozenset({"ge-proton11-11-x86_64"}), f"does not declare a tool named {TOOL}"),
    ],
)
def test_an_unpacked_build_is_whole_or_says_what_it_lacks(top, manifest, toolmanifest, declared, problem):
    assert pb.check_extracted(top, TOOL, manifest, toolmanifest, declared) == problem


# ── moving games to a newer build ────────────────────────────────────────────


def ge_releases() -> list[pb.Release]:
    return pb.available(pb.GE_PROTON, ge())


def test_the_older_builds_of_an_update_are_those_released_before_it_or_no_longer_listed():
    releases = ge_releases()
    new = releases[1]  # GE-Proton11-11
    tools = [tool("GE-Proton11-12-x86_64"), tool("GE-Proton11-10-x86_64"), tool("GE-Proton10-34"),
             tool("GE-Proton11-11-x86_64"), tool("proton-cachyos-11.0-20261015-slr-x86_64")]

    older = pb.older_of_build(new, releases, tools)

    assert [t.folder for t in older] == ["GE-Proton11-10-x86_64", "GE-Proton10-34"]


def forced(games: dict[str, str]) -> ForcedMappings:
    return ForcedMappings(games, None)


def test_an_update_leaves_the_games_on_older_builds_of_the_same_build_to_move():
    releases = ge_releases()
    renamed = pb.Tool("my-ge", frozenset({"ge-proton11-10-x86_64"}))
    tools = [tool("GE-Proton11-11-x86_64"), renamed, tool("GE-Proton10-34"), tool("proton-cachyos-11.0-20261015-slr-x86_64")]
    chosen = forced({"730": "GE-Proton11-11-x86_64", "440": "GE-Proton11-10-x86_64", "570": "GE-Proton10-34",
                     "620": "proton-cachyos-11.0-20261015-slr-x86_64"})

    pending = pb.pending_move(releases[0], releases, tools, chosen)

    assert pending == pb.PendingMove(
        "GE-Proton11-12-x86_64",
        frozenset({"ge-proton11-11-x86_64", "my-ge", "ge-proton11-10-x86_64", "ge-proton10-34"}),
        ("440", "570", "730"),
    )
    assert pb.pending_move(releases[0], releases, tools, forced({"620": "proton-cachyos-11.0-20261015-slr-x86_64"})) is None
    # going back to an older release: the newer build's games stay where they are
    assert pb.pending_move(releases[5], releases, [tool("GE-Proton11-11-x86_64")], chosen) is None


def test_a_second_update_before_the_move_moves_the_games_to_the_latest_from_any_older_build():
    first = pb.PendingMove("GE-Proton11-12-x86_64", frozenset({"ge-proton11-11-x86_64"}), ("730",))
    second = pb.PendingMove("GE-Proton11-13-x86_64", frozenset({"ge-proton11-12-x86_64"}), ("440",))

    assert pb.merge(first, second) == pb.PendingMove(
        "GE-Proton11-13-x86_64", frozenset({"ge-proton11-11-x86_64", "ge-proton11-12-x86_64"}), ("440", "730")
    )
    assert pb.merge(None, second) == second and pb.merge(first, None) == first and pb.merge(None, None) is None


def test_only_games_still_on_an_older_build_are_offered_while_the_newer_one_is_installed():
    pending = pb.PendingMove("GE-Proton11-12-x86_64", frozenset({"ge-proton11-11-x86_64"}), ("440", "570", "730"))
    tools = [tool("GE-Proton11-12-x86_64"), tool("GE-Proton11-11-x86_64")]
    now = forced({"730": "GE-Proton11-11-x86_64", "440": "GE-Proton11-12-x86_64"})  # 440 moved by hand, 570 cleared

    assert pb.still_to_move(pending, tools, now) == ["730"]
    assert pb.still_to_move(pending, [tool("GE-Proton11-11-x86_64")], now) == []  # the newer build was removed


def test_moved_games_are_offered_no_more():
    pending = pb.PendingMove("GE-Proton11-12-x86_64", frozenset({"ge-proton11-11-x86_64"}), ("440", "730"))

    assert pb.moved(pending, ["730"]) == pb.PendingMove(pending.target, pending.sources, ("440",))
    assert pb.moved(pending, ["730", "440"]) is None


def test_pending_moves_survive_a_file_and_junk_in_it_doesnt():
    moves = {pb.GE_PROTON: pb.PendingMove("GE-Proton11-12-x86_64", frozenset({"ge-proton11-11-x86_64"}), ("730",))}

    assert pb.parse_pending(json.loads(json.dumps(pb.pending_to_json(moves)))) == moves
    junk = {"valve-proton": {"target": "x", "sources": [], "appids": ["1"]}, pb.PROTON_CACHYOS: {"target": "x", "sources": ["a"], "appids": []},
            pb.PROTON_CACHYOS_V3: "x", pb.GE_PROTON: {"target": "GE", "sources": ["A"], "appids": [730]}}
    assert pb.parse_pending(junk) == {pb.GE_PROTON: pb.PendingMove("GE", frozenset({"a"}), ("730",))}
    assert pb.parse_pending([]) == {}

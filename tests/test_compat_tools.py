"""Steam's compatibility-tool data: which tool runs a game, which ones the user chose, what a manifest declares (unit)."""

from __future__ import annotations

import pytest

from deckyscaler.domain import compat_tools, keyvalues


def mapping(entries: dict[str, str], priority: str | None = "250") -> keyvalues.KeyValues:
    entry = lambda name: {"name": name, "config": ""} | ({} if priority is None else {"priority": priority})  # noqa: E731
    return {"installconfigstore": {"software": {"valve": {"steam": {"compattoolmapping": {
        appid: entry(name) for appid, name in entries.items()
    }}}}}}


@pytest.mark.parametrize(
    ("entries", "tool"),
    [
        ({"730": "GE-Proton11-11", "0": "proton_experimental"}, "GE-Proton11-11"),  # the game's own choice wins
        ({"0": "proton-cachyos"}, "proton-cachyos"),  # else the one for every game
        ({"730": "", "0": "GE-Proton11-1"}, "GE-Proton11-1"),  # an empty name is no choice
        ({}, None),  # Steam's default, which no file names
    ],
)
def test_the_games_tool_is_its_own_choice_else_the_global_one(entries, tool):
    assert compat_tools.compat_tool(mapping(entries), "730") == tool


def test_no_mapping_section_means_steams_default():
    assert compat_tools.compat_tool({}, "730") is None


def test_a_tool_manifest_names_its_tools_and_where_they_are():
    manifest = keyvalues.parse('"compatibilitytools" { "compat_tools" { "GE-Proton11-11" { "install_path" "." } "x" { } } }')

    assert compat_tools.custom_tools(manifest) == {"ge-proton11-11": ".", "x": "."}
    assert compat_tools.custom_tools({}) == {}


# ── the tools the user chose ─────────────────────────────────────────────────


def test_the_user_chose_the_tools_steam_ranks_at_250_or_more_and_the_one_for_every_game_stays_apart():
    config = mapping({"730": "GE-Proton11-12-x86_64", "1091500": "proton-cachyos-11.0-20261015-slr-x86_64", "0": "GE-Proton11-12-x86_64"})

    chosen = compat_tools.forced_mappings(config)

    assert chosen.games == {"730": "GE-Proton11-12-x86_64", "1091500": "proton-cachyos-11.0-20261015-slr-x86_64"}
    assert chosen.global_tool == "GE-Proton11-12-x86_64"


@pytest.mark.parametrize(
    ("priority", "chosen"),
    [("250", True), ("300", True), ("249", False), ("75", False), (None, False), ("high", False)],
)
def test_steams_own_picks_rank_lower_and_are_not_the_users(priority, chosen):
    games = compat_tools.forced_mappings(mapping({"730": "GE-Proton11-12-x86_64"}, priority)).games

    assert (games == {"730": "GE-Proton11-12-x86_64"}) is chosen


def test_the_tool_for_every_game_counts_whatever_its_priority():
    assert compat_tools.forced_mappings(mapping({"0": "GE-Proton11-12-x86_64"}, "75")).global_tool == "GE-Proton11-12-x86_64"


def test_names_keep_the_case_steam_wrote_them_in_and_junk_is_no_choice():
    config = mapping({"730": "GE-Proton11-12-x86_64"})
    config["installconfigstore"]["software"]["valve"]["steam"]["compattoolmapping"].update(
        {"440": "not a section", "570": {"name": "", "priority": "250"}, "620": {"priority": "250"}}
    )

    chosen = compat_tools.forced_mappings(config)

    assert chosen.games == {"730": "GE-Proton11-12-x86_64"}
    assert chosen.global_tool is None
    assert compat_tools.forced_mappings({}) == compat_tools.ForcedMappings({}, None)


@pytest.mark.parametrize(
    ("toolmanifest", "target"),
    [
        ('"manifest" { "version" "2" "commandline" "/proton %verb%" }', "proton"),  # every Proton
        ('"manifest" { "commandline" "/luxtorpeda.sh %verb%" }', "luxtorpeda.sh"),
        ('"manifest" { "commandline" "/run-dosbox" }', "run-dosbox"),  # Boxtron: no %verb%
        ('"manifest" { "commandline_waitforexitandrun" "/steamtinkerlaunch %verb%" }', "steamtinkerlaunch"),
        ('"manifest" { "version" "2" }', None),  # names none: nothing proves the tool broken
        ('"manifest" { "commandline" "" }', None),
        ("", None),
    ],
)
def test_a_tools_launch_file_is_the_first_word_of_its_command_line(toolmanifest, target):
    assert compat_tools.launch_target(keyvalues.parse(toolmanifest)) == target

"""Which libraries go into which games: the user's choice and what a patch places by it."""

from __future__ import annotations

import pytest

from deckyscaler.domain import library_choice as lc
from deckyscaler.domain.library import FAMILIES
from deckyscaler.domain import user_libraries as ul
from deckyscaler.domain.library_choice import GLOBAL, NONE, Choices

FG, UP = ul.FRAME_GENERATION, ul.UPSCALER
V10, V09 = FAMILIES["10"], FAMILIES["0.9"]


def _library(library_id: str, *files: str) -> ul.Library:
    contents = ul.recognize(frozenset(files))
    return ul.Library(library_id, library_id, None, ul.YOUR_FILE, None, contents.providers, contents.dlls, contents.files, (), "")


ANR = _library("anr", "ANR/dlssg/nvngx_dlssg.dll")
XESS = _library("xess", "libxess.dll", "libxess_fg.dll")
FSR = _library("fsr", "amd_fidelityfx_upscaler_dx12.dll")


def test_choices_are_stored_and_read_back_and_anything_else_is_no_choice():
    choices = Choices({UP: "xess"}, {"620": {FG: "anr", UP: NONE}})

    assert lc.parse(lc.to_json(choices)) == choices
    assert lc.parse(None) == Choices({}, {})
    assert lc.parse({GLOBAL: {UP: NONE, "slot": "x", FG: ""}, "games": {"1": "x", "2": {FG: "anr", "x": "y"}}}) == Choices(
        {}, {"2": {FG: "anr"}}
    )


def test_the_global_choice_is_a_library_or_none():
    choices = lc.with_choice(Choices({}, {}), GLOBAL, UP, "xess")

    assert choices.global_choice == {UP: "xess"}
    assert lc.with_choice(choices, GLOBAL, UP, None).global_choice == {}
    assert lc.with_choice(choices, GLOBAL, UP, NONE).global_choice == {}


def test_a_games_choice_is_a_library_none_or_following_the_global_one():
    choices = lc.with_choice(Choices({UP: "xess"}, {}), "620", UP, NONE)

    assert choices.games == {"620": {UP: NONE}}
    assert lc.with_choice(choices, "620", UP, "fsr").games == {"620": {UP: "fsr"}}
    assert lc.with_choice(choices, "620", UP, None).games == {"620": {}}
    assert lc.to_json(lc.with_choice(choices, "620", UP, None))["games"] == {}


def test_only_a_slot_can_be_chosen_for():
    with pytest.raises(ValueError):
        lc.with_choice(Choices({}, {}), GLOBAL, "sharpening", "x")


def test_a_game_follows_the_global_choice_unless_it_has_its_own():
    choices = Choices({UP: "xess", FG: "anr"}, {"620": {UP: "fsr", FG: NONE}})

    assert lc.resolved(choices, "620") == {UP: "fsr"}
    assert lc.resolved(choices, "570") == {UP: "xess", FG: "anr"}
    assert lc.resolved(choices, None) == {UP: "xess", FG: "anr"}


def test_a_patch_places_the_chosen_libraries_still_on_the_device_that_serve_their_slot():
    chosen = {FG: "anr", UP: "xess"}

    assert lc.to_place(chosen, [ANR, XESS, FSR], V10) == ((UP, XESS), (FG, ANR))
    assert lc.to_place(chosen, [XESS], V10) == ((UP, XESS),)
    assert lc.to_place({UP: "anr", FG: "fsr"}, [ANR, FSR], V10) == ()  # neither serves the slot it was picked for


def test_optiscaler_0_9_takes_no_libraries():
    assert lc.to_place({FG: "anr", UP: "xess"}, [ANR, XESS], V09) == ()


def test_a_marker_records_picks_and_anything_else_records_none():
    recorded = [{"slot": UP, "id": "xess", "label": "xess"}, {"slot": "x", "id": "y"}, {"slot": FG}, "z"]

    assert lc.picks(((UP, XESS), (FG, ANR))) == ((UP, "xess"), (FG, "anr"))
    assert lc.recorded_picks(recorded) == ((UP, "xess"),)
    assert lc.recorded_picks(None) == ()


def test_the_wrapper_keeps_what_a_game_has_while_it_is_on_the_device():
    assert lc.kept(((UP, "xess"), (FG, "anr")), [XESS]) == {UP: "xess"}


def test_a_librarys_users_are_the_games_whose_patch_placed_it():
    patched = [("Hades II", [{"slot": FG, "id": "anr"}]), ("Cyberpunk 2077", [{"slot": FG, "id": "anr"}]), ("Elden Ring", [])]

    assert lc.users("anr", patched) == ["Cyberpunk 2077", "Hades II"]
    assert lc.users("xess", patched) == []


def test_the_wrappers_patch_keeps_what_the_game_has_and_any_other_goes_by_the_choice():
    choices = Choices({UP: "fsr"}, {})

    assert lc.to_patch_with(choices, "620", ((UP, "xess"), (FG, "gone")), [XESS, FSR]) == {UP: "xess"}
    assert lc.to_patch_with(choices, "620", (), [XESS, FSR]) == {}
    assert lc.to_patch_with(choices, "620", None, [XESS, FSR]) == {UP: "fsr"}


def test_a_game_needs_its_choice_applied_while_a_patch_would_place_other_libraries():
    recorded = [{"slot": UP, "id": "xess", "label": "xess"}]

    assert not lc.needs_applying(recorded, {UP: "xess"}, [XESS], V10)
    assert lc.needs_applying(recorded, {UP: "fsr"}, [XESS, FSR], V10)
    assert lc.needs_applying(recorded, {UP: "xess"}, [], V10)  # the library left the device
    assert not lc.needs_applying([], {UP: "xess"}, [XESS], V09)  # 0.9 takes none


def test_a_slot_takes_none_following_or_a_library_serving_it():
    assert lc.can_choose(UP, None, []) and lc.can_choose(UP, NONE, [])
    assert lc.can_choose(UP, "xess", [XESS])
    assert not lc.can_choose(FG, "fsr", [FSR])  # FSR's upscaler file serves no frame generation
    assert not lc.can_choose(UP, "gone", [XESS])


def test_a_library_that_left_the_device_is_nobodys_choice():
    choices = Choices({UP: "xess", FG: "anr"}, {"620": {UP: "xess", FG: NONE}, "570": {UP: "fsr"}})

    assert lc.without(choices, "xess") == Choices({FG: "anr"}, {"620": {FG: NONE}, "570": {UP: "fsr"}})

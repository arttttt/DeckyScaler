"""Which libraries go into which games: the user's choice per slot, for every game and for one, and what a patch
places by it.

The global choice names a library per slot, or none. A game's own choice is either absent (the game follows the
global one), NONE, or a library. A patch from the plugin's pages picks what the game's choice resolves to; the
launch wrapper's patch keeps what the game's patch picked, as it keeps the game's OptiScaler version, so a new
global choice reaches patched games only when the user applies it.

A pick selects a library; every other library OptiScaler's own menu can offer goes in beside it, selected by
nothing, whatever the choice: a library on the device is there to pick in the game too.
"""

from __future__ import annotations

from dataclasses import dataclass

from .library import Family
from .user_libraries import SLOTS, Library

GLOBAL = "global"
NONE = "none"
"""A game's choice of no library for a slot, whatever the global choice is."""

Pick = tuple[str, str]
"""(slot, library id): a library placed for a slot."""

Placed = tuple[str | None, str]
"""(slot, library id) for a library placed for a slot, (None, library id) for one only offered in OptiScaler's menu."""


@dataclass(frozen=True)
class Choices:
    global_choice: dict[str, str]
    """slot → library id."""
    games: dict[str, dict[str, str]]
    """appid → slot → library id or NONE."""


def parse(data: object) -> Choices:
    """The stored choices; anything that isn't one reads as no choice."""
    data = data if isinstance(data, dict) else {}
    stored_global = data.get(GLOBAL) if isinstance(data.get(GLOBAL), dict) else {}
    stored_games = data.get("games") if isinstance(data.get("games"), dict) else {}
    return Choices(
        {slot: str(value) for slot, value in stored_global.items() if slot in SLOTS and value and value != NONE},
        {
            str(appid): {slot: str(value) for slot, value in slots.items() if slot in SLOTS and value}
            for appid, slots in stored_games.items()
            if isinstance(slots, dict)
        },
    )


def to_json(choices: Choices) -> dict:
    return {GLOBAL: dict(choices.global_choice), "games": {appid: dict(slots) for appid, slots in choices.games.items() if slots}}


def with_choice(choices: Choices, scope: str, slot: str, value: str | None) -> Choices:
    """The choices with one slot changed: for every game (GLOBAL) a library, or None for none; for a game a
    library, NONE, or None for following the global choice."""
    if slot not in SLOTS:
        raise ValueError(f"Not a slot: {slot}")
    if scope == GLOBAL:
        changed = {s: v for s, v in choices.global_choice.items() if s != slot}
        if value is not None and value != NONE:
            changed[slot] = value
        return Choices(changed, choices.games)
    game = {s: v for s, v in choices.games.get(scope, {}).items() if s != slot}
    if value is not None:
        game[slot] = value
    return Choices(choices.global_choice, {**choices.games, scope: game})


def can_choose(slot: str, value: str | None, installed: list[Library]) -> bool:
    """Whether a slot can be set to `value`: following the global choice or none (None, NONE), or a library on the
    device that serves the slot."""
    if value is None or value == NONE:
        return True
    return any(library.id == value and slot in library.slots for library in installed)


def without(choices: Choices, library_id: str) -> Choices:
    """The choices once a library has left the device: no game is left choosing it. A game that chose it follows
    the global choice again."""
    return Choices(
        {slot: value for slot, value in choices.global_choice.items() if value != library_id},
        {appid: {slot: value for slot, value in slots.items() if value != library_id} for appid, slots in choices.games.items()},
    )


def resolved(choices: Choices, appid: str | None) -> dict[str, str]:
    """slot → the library a game's choice comes to: its own, else the global one; a game patched by a path, with
    no appid, takes the global one."""
    own = choices.games.get(appid, {}) if appid else {}
    picked = {**choices.global_choice, **own}
    return {slot: value for slot, value in picked.items() if value != NONE}


@dataclass(frozen=True)
class ToPlace:
    picked: tuple[tuple[str, Library], ...]
    """(slot, library), in slot order: selected for the slot."""
    offered: tuple[Library, ...]
    """The other libraries OptiScaler's menu offers (Library.in_menu), by label: in the game, selected by nothing."""


def _picked(chosen: dict[str, str], installed: list[Library]) -> tuple[tuple[str, Library], ...]:
    """Each chosen library still on the device that serves its slot, in slot order, but one naming a provider an
    earlier slot's library already has: a provider is found by its folder's name, so the game would run the earlier
    library's under it."""
    by_id = {library.id: library for library in installed}
    picked: list[tuple[str, Library]] = []
    owners: dict[str, str] = {}  # a provider's name, lowercase → the picked library placing it
    for slot in SLOTS:
        library = by_id.get(chosen.get(slot, ""))
        if library is None or slot not in library.slots:
            continue
        names = {provider.name.lower() for provider in library.providers}
        if any(owners.get(name, library.id) != library.id for name in names):
            continue
        owners.update(dict.fromkeys(names, library.id))
        picked.append((slot, library))
    return tuple(picked)


def to_place(chosen: dict[str, str], installed: list[Library], family: Family) -> ToPlace:
    """The libraries a patch with a version of `family` places: the picked ones (`_picked`) and every other one
    OptiScaler's menu offers; none for a family that takes no libraries.

    A provider is found by its folder's name, so one name is one library's in a game (two versions of one project
    share it): the first pick's in slot order, the upscaler's, else the one added last's. A library goes in whole
    or not at all."""
    if not family.libraries:
        return ToPlace((), ())
    picked = _picked(chosen, installed)
    # The picked libraries' providers take their names first: none is offered again, nor one sharing a name.
    taken = {provider.name.lower() for _, library in picked for provider in library.providers}
    offered: list[Library] = []
    for library in sorted(installed, key=lambda item: (item.added_at, item.id), reverse=True):
        names = {provider.name.lower() for provider in library.providers}
        if not library.in_menu or names & taken:
            continue
        taken |= names
        offered.append(library)
    return ToPlace(picked, tuple(sorted(offered, key=lambda item: (item.label.lower(), item.id))))


def left_out(chosen: dict[str, str], installed: list[Library]) -> tuple[str, ...]:
    """The slots whose chosen library serves them and is on the device, yet can't go into a game: an earlier slot's
    library names one of its providers."""
    by_id = {library.id: library for library in installed}
    picked = {slot for slot, _ in _picked(chosen, installed)}
    return tuple(
        slot
        for slot in SLOTS
        if slot not in picked and (library := by_id.get(chosen.get(slot, ""))) is not None and slot in library.slots
    )


def missing(chosen: dict[str, str], installed: list[Library]) -> tuple[str, ...]:
    """The slots whose chosen library isn't on the device: its files went missing, or it was taken away by hand.
    Nothing goes in for them until it is downloaded or added again, or another is picked."""
    on_device = {library.id for library in installed}
    return tuple(slot for slot in SLOTS if slot in chosen and chosen[slot] not in on_device)


def placed(to_place: ToPlace) -> tuple[Placed, ...]:
    return tuple((slot, library.id) for slot, library in to_place.picked) + tuple(
        (None, library.id) for library in to_place.offered
    )


def recorded_placed(recorded: object) -> tuple[Placed, ...]:
    """What a game's marker records of the libraries its patch placed; a marker from before libraries, or anything
    else, records none."""
    if not isinstance(recorded, list):
        return ()
    return tuple(
        (None if item.get("slot") is None else str(item["slot"]), str(item["id"]))
        for item in recorded
        if isinstance(item, dict) and (item.get("slot") is None or item.get("slot") in SLOTS) and item.get("id")
    )


def recorded_picks(recorded: object) -> tuple[Pick, ...]:
    """The picks a game's marker records."""
    return tuple((slot, library_id) for slot, library_id in recorded_placed(recorded) if slot is not None)


def kept(recorded: tuple[Pick, ...], installed: list[Library]) -> dict[str, str]:
    """The choice the launch wrapper patches with for a patched game: what its patch placed, still on the device."""
    on_device = {library.id for library in installed}
    return {slot: library_id for slot, library_id in recorded if library_id in on_device}


def to_patch_with(
    choices: Choices, appid: str | None, recorded: tuple[Pick, ...] | None, installed: list[Library]
) -> dict[str, str]:
    """The choice a patch goes by: what the game's patch placed when the patch keeps it (`recorded`, the launch
    wrapper's patch of a game it patched before), else what the game's choice resolves to."""
    return resolved(choices, appid) if recorded is None else kept(recorded, installed)


def needs_applying(recorded: object, chosen: dict[str, str], installed: list[Library], family: Family) -> bool:
    """Whether patching a game again would place other libraries than its marker records: its choice changed, or a
    library came onto the device or left it."""
    return recorded_placed(recorded) != placed(to_place(chosen, installed, family))


def users(library_id: str, patched: list[tuple[str, object]]) -> list[str]:
    """The games, by name, whose patch placed a library, picked or offered: `patched` pairs each game's name with
    what its marker recorded."""
    return sorted(name for name, recorded in patched if any(item[1] == library_id for item in recorded_placed(recorded)))

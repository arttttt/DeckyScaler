"""Which libraries go into which games: the user's choice per slot, for every game and for one, and what a patch
places by it.

The global choice names a library per slot, or none. A game's own choice is either absent (the game follows the
global one), NONE, or a library. A patch from the plugin's pages places what the game's choice resolves to; the
launch wrapper's patch keeps what the game's patch placed, as it keeps the game's OptiScaler version, so a new
global choice reaches patched games only when the user applies it.
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


def to_place(chosen: dict[str, str], installed: list[Library], family: Family) -> tuple[tuple[str, Library], ...]:
    """The libraries a patch with a version of `family` places, in slot order: each chosen one still on the device
    that serves its slot; none for a family that takes no libraries."""
    if not family.libraries:
        return ()
    by_id = {library.id: library for library in installed}
    return tuple(
        (slot, library)
        for slot in SLOTS
        if (library := by_id.get(chosen.get(slot, ""))) is not None and slot in library.slots
    )


def picks(placed: tuple[tuple[str, Library], ...]) -> tuple[Pick, ...]:
    return tuple((slot, library.id) for slot, library in placed)


def recorded_picks(recorded: object) -> tuple[Pick, ...]:
    """The picks a game's marker recorded; a marker from before libraries, or anything else, records none."""
    if not isinstance(recorded, list):
        return ()
    return tuple(
        (str(item["slot"]), str(item["id"]))
        for item in recorded
        if isinstance(item, dict) and item.get("slot") in SLOTS and item.get("id")
    )


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
    """Whether patching a game again would place other libraries than its marker records: its choice changed, or
    a library it has left the device."""
    return recorded_picks(recorded) != picks(to_place(chosen, installed, family))


def users(library_id: str, patched: list[tuple[str, object]]) -> list[str]:
    """The games, by name, whose patch placed a library: `patched` pairs each game's name with what its marker
    recorded."""
    return sorted(name for name, recorded in patched if any(pick[1] == library_id for pick in recorded_picks(recorded)))

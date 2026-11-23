"""The marker (DECKYSCALER_PATCH) the plugin leaves in a directory it patched."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import library_choice, settings_layers
from .launch_options import is_managed


@dataclass(frozen=True)
class SteamGame:
    """What a patch made through the Steam game list records about the game."""

    appid: str
    name: str
    original_launch_options: str
    launch_options: str = ""
    """The launch options this patch has Steam set: what the next patch tells its own from."""




def build(
    *,
    dll_name: str,
    target_dir: Path,
    backed_up_files: list[str],
    optiscaler_version: str,
    family: str,
    patched_at: str,
    steam_game: SteamGame | None = None,
    libraries: tuple[dict, ...] = (),
    library_layer: settings_layers.LibraryLayer | None = None,
) -> dict:
    """The marker's details; every patch writes one, a Steam patch also records the game.

    `optiscaler_version` is the library version's id (stable-0.9.4, nightly-20261023). `libraries` is what the
    patch placed of the user's libraries, picked or offered (domain/library_placement), and `library_layer` the
    ini keys they own: the game's later settings writes read them from here, whatever the device holds by then.
    """
    return {
        "appid": steam_game.appid if steam_game else "",
        "game_name": steam_game.name if steam_game else "",
        "dll_name": dll_name,
        "target_dir": str(target_dir),
        "original_launch_options": steam_game.original_launch_options if steam_game else "",
        **({"launch_options": steam_game.launch_options} if steam_game else {}),
        "backed_up_files": backed_up_files,
        "optiscaler_version": optiscaler_version,
        "family": family,
        "patched_at": patched_at,
        "libraries": list(libraries),
        "library_settings": settings_layers.library_layer_json(library_layer or {}),
    }


def shown_name(details: dict, directory: Path) -> str:
    """What the plugin's pages call a patched directory: the game its patch recorded, else the directory itself (a
    patch by path, or the launch wrapper's, records none)."""
    return str(details.get("game_name") or directory)


def describes(details: dict, version_id: str, dll_name: str, placed: tuple[library_choice.Placed, ...] = ()) -> bool:
    """Whether a marker records a finished patch with this version under this proxy name and these libraries:
    patching again would place the same."""
    return (
        details.get("complete") is True
        and details.get("optiscaler_version") == version_id
        and details.get("dll_name") == dll_name
        and library_choice.recorded_placed(details.get("libraries")) == placed
    )


def library_layer(details: dict) -> settings_layers.LibraryLayer:
    """The ini keys the libraries a marker's patch placed own; a marker from before libraries owns none."""
    return settings_layers.parse_library_layer(details.get("library_settings"))


def original_launch_options(current: str | None, stored: str | None, patched_with: str) -> str | None:
    """The user's own launch options, to keep in the marker of a patch with the proxy `patched_with` and restore on
    unpatch.

    Options stored by an earlier patch (None when there was none) win over the current ones, which may be ours; options
    the plugin itself wrote are never treated as the user's. `current` is None when Steam didn't say what they are:
    then only stored options can be kept, and without them the user's are unknown (None): a patch would lose them for
    good, so it mustn't happen.
    """
    if stored and not is_managed(stored, patched_with):
        return stored
    if current is None:
        return None if stored is None else ""
    return "" if is_managed(current, patched_with) else current


def launch_options_after_unpatch(current: str | None, stored: str | None, patched_with: str | None) -> str | None:
    """A game's launch options once it is unpatched, or None to leave them as they are: the user's own come back, or
    none, while the current ones are still exactly the plugin's for its proxy (`patched_with`, any when unknown); ones
    the user changed since aren't the plugin's to touch, nor ones Steam didn't say."""
    if current is None or not is_managed(current, patched_with):
        return None
    return stored if stored and not is_managed(stored, patched_with) else ""


def launch_options_after_patch(written: str | None, needed: str, current: str | None) -> str | None:
    """What a Steam game's launch options are set to as it is patched, or None to leave them: options Steam didn't say
    (every patched game patched again at once doesn't read them) stay as they are while the plugin's would be what
    its last patch set (`written`, None for a marker from before it was kept): they are that, or the user's edit since.
    Otherwise they are the plugin's (`needed`)."""
    if current is None and written == needed:
        return None
    return needed

"""How the libraries picked for a game go into it: what is copied where, and the ini keys that select and find them.

Every file is a copy, never a link: a game keeps the library it was patched with when the library leaves the device,
and a provider writes into its own folder (its settings, its logs) for this game alone. A provider's folder goes into
OptiScaler's `custom/` folder, where OptiScaler looks for it by name; a DLL goes into a folder of the plugin's own
beside it, never over OptiScaler's copy, and its [Libraries] key points at it. A relative [Libraries] path is joined
onto the directory of the proxy DLL, the game's (OptiScaler Config.cpp, Util::DllPath).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from .patch_plan import Copy
from .settings_layers import Key, LibraryLayer, Owned
from .user_libraries import LIBRARIES, UPSCALER, Library, kind, known_dll

CUSTOM_DIRNAME = "custom"
USER_LIBRARIES_DIRNAME = "user-libraries"


@dataclass(frozen=True)
class Placement:
    copies: tuple[Copy, ...]
    """From the libraries on the device (absolute) into the game directory."""
    layer: LibraryLayer
    settings_files: frozenset[str]
    """Placed files a provider keeps its settings in: rewritten by it, so ours whatever they hold (a rewrite doesn't
    break the patch). Patching the game again puts a fresh copy in: changes made to them in the game don't last."""
    owned_dirs: tuple[str, ...]
    """Provider folders: everything in them is the library's, its logs too."""
    recorded: tuple[dict, ...]
    """What the game's marker records of the libraries: slot, id and label."""


def _dll_serves(slot: str, dll_name: str) -> bool:
    slots = known_dll(dll_name).slots
    # A file that serves no slot comes along with its library, whichever slot it is placed for.
    return slot in slots or not slots


def place(picked: tuple[tuple[str, Library], ...], main_dir: str, files_dirs: dict[str, str]) -> Placement:
    """Where the libraries picked for a game's slots go, from their files on the device (`files_dirs`: library id →
    its files' absolute directory), into a game whose OptiScaler files are in `main_dir`.

    For each slot, in order: the library's providers of a kind serving it, set by name in the keys their kind
    selects, and its DLLs serving it, each pointed at by its key; picked as the upscaler, the first DLL selecting
    an API's upscaler (in the table's order) selects it. What an earlier slot placed or set stays: the upscaler's
    library wins a file or key both slots' libraries have."""
    copies: dict[str, Copy] = {}
    layer: LibraryLayer = {}
    settings_files: set[str] = set()
    owned: list[str] = []
    for slot, library in picked:
        files = files_dirs[library.id]

        def own(key: Key, value: str) -> None:
            layer.setdefault(key, Owned(value, library.label))

        for provider in library.providers:
            kinds = [k for name in provider.kinds if (k := kind(name)) is not None and k.slot == slot]
            if not kinds:
                continue
            folder = f"{main_dir}/{CUSTOM_DIRNAME}/{provider.name}"
            for path in library.files:
                if not path.startswith(f"{provider.folder}/"):
                    continue
                destination = f"{folder}/{path.removeprefix(f'{provider.folder}/')}"
                copies.setdefault(destination, Copy(f"{files}/{path}", destination))
                if path.lower().endswith(".ini"):
                    settings_files.add(destination)
            if folder not in owned:
                owned.append(folder)
            for k in kinds:
                for key in k.selects:
                    own(key, provider.name)
                for key, value in k.sets:
                    own(key, value)
        for dll in library.dlls:
            if not _dll_serves(slot, dll.name):
                continue
            known = known_dll(dll.name)
            destination = f"{main_dir}/{USER_LIBRARIES_DIRNAME}/{known.name}"
            copies.setdefault(destination, Copy(f"{files}/{dll.path}", destination))
            own((LIBRARIES, known.path_key), str(PureWindowsPath(*PurePosixPath(destination).parts)))
            if slot == UPSCALER:
                for key, value in known.upscaler:
                    own(key, value)
        for key, value in library.settings:
            own(key, value)
    return Placement(
        tuple(copies.values()),
        layer,
        frozenset(settings_files),
        tuple(owned),
        tuple({"slot": slot, "id": library.id, "label": library.label} for slot, library in picked),
    )


def released(previous: LibraryLayer, current: LibraryLayer) -> frozenset[Key]:
    """The keys the game's libraries set before a patch and no longer do: they go back to the user's values."""
    return frozenset(previous) - frozenset(current)


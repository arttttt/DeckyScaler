"""How a patched game is started: Wine DLL overrides and the Steam launch options."""

from __future__ import annotations

import shlex

from .bundle import DEFAULT_PROXY_DLL, PROXY_DLLS, VALID_DLL_NAMES
from .fsr4 import UPGRADE_VARIABLE

WRAPPER_PATCH = "~/deckyscaler/patch %command%"
"""Launch options that patch the game through the launch wrapper on every start."""
WRAPPER_UNPATCH = "~/deckyscaler/unpatch %command%"
"""Launch options that unpatch the game through the wrapper on its next start."""

_ASI_PROXY = "OptiScaler.asi"
_OUR_WRAPPERS = ("/deckyscaler/patch", "/deckyscaler/unpatch")
"""This plugin's launch wrapper's scripts, by whatever path they are given."""
_WRAPPERS = (*_OUR_WRAPPERS, "/fgmod/fgmod")
"""The launch wrapper's scripts, this plugin's and the original Decky Framegen's."""


def override_entry(dll_name: str) -> str | None:
    """The WINEDLLOVERRIDES entry that loads our proxy natively before Wine's builtin DLL.

    An .asi proxy is loaded by the game's ASI loader and needs none.
    """
    if dll_name == _ASI_PROXY:
        return None
    return f"{dll_name.replace('.dll', '')}=n,b"


def wine_dll_overrides(current: str, dll_name: str) -> str:
    """WINEDLLOVERRIDES with our proxy's entry added; Wine separates entries with ';'."""
    entry = override_entry(dll_name)
    if entry is None:
        return current
    return f"{current};{entry}" if current else entry


def managed(dll_name: str, fsr4_upgrade: bool = False) -> str:
    """The Steam launch options for a game patched with the given proxy DLL; `fsr4_upgrade` also asks
    the game's Proton to fetch FSR 4."""
    entry = override_entry(dll_name)
    variables = ([f"WINEDLLOVERRIDES={entry}"] if entry else []) + ([f"{UPGRADE_VARIABLE}=1"] if fsr4_upgrade else [])
    return " ".join([*variables, "SteamDeck=0 %command%"])


def setup_json() -> dict:
    """Everything the panel offers for starting a game: the proxy DLLs, each with when to pick it and
    the launch options it needs, and the wrapper's commands. The panel builds none of these itself."""
    return {
        "default": DEFAULT_PROXY_DLL,
        "proxies": [
            {"name": name, "hint": hint, "launch_options": managed(name)} for name, hint in PROXY_DLLS.items()
        ],
        "wrapper": {"patch": WRAPPER_PATCH, "unpatch": WRAPPER_UNPATCH},
    }


def _normalized(options: str) -> str:
    # Decky Framegen also wrote the override quoted: WINEDLLOVERRIDES="dxgi=n,b".
    return " ".join(options.replace('"', "").replace("'", "").split())


def is_managed(options: str, patched_with: str | None = None) -> bool:
    """Whether launch options are exactly what the plugin or the original Decky Framegen writes for a game patched with
    the proxy `patched_with` (with any proxy when None), FSR 4's upgrade variable or not, or either's launch wrapper
    alone. Anything the user added to them makes them the user's: theirs to keep, never ours to clear."""
    words = _normalized(options).split(" ")
    if len(words) == 2 and words[0].endswith(_WRAPPERS) and words[1].lower() == "%command%":
        return True
    proxies = [patched_with] if patched_with else sorted(VALID_DLL_NAMES)
    return _normalized(options) in {_normalized(managed(dll, upgrade)) for dll in proxies for upgrade in (False, True)}


def without_wrapper(options: str | None) -> str | None:
    """Launch options with this plugin's launch wrapper taken out and the rest as the user wrote it ("" when nothing
    but %command% is left), or None when the wrapper isn't in them, or Steam didn't say what they are."""
    if options is None:
        return None
    try:
        words = shlex.split(options, posix=False)  # quotes stay in the words: the rest comes back as written
    except ValueError:
        return None
    rest = [word for word in words if not word.strip("\"'").endswith(_OUR_WRAPPERS)]
    if len(rest) == len(words):
        return None
    return "" if [word.lower() for word in rest] in ([], ["%command%"]) else " ".join(rest)

"""How a patched game is started: Wine DLL overrides and the Steam launch options."""

from __future__ import annotations

import shlex

from .bundle import DEFAULT_PROXY_DLL, PROXY_DLLS, VALID_DLL_NAMES

WRAPPER_PATCH = "~/deckyscaler/patch %command%"
"""Launch options that patch the game through the launch wrapper on every start."""
WRAPPER_UNPATCH = "~/deckyscaler/unpatch %command%"
"""Launch options that unpatch the game through the wrapper on its next start."""

EARLIER_FSR4_VARIABLE = "PROTON_FSR4_UPGRADE=1"
"""What earlier versions of the plugin added to a game's launch options for Proton to fetch AMD's FSR 4 driver DLL,
which OptiScaler's own FSR 4 has made unneeded: options with it are still the plugin's, for a patch to replace."""

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


def managed(dll_name: str) -> str:
    """The Steam launch options for a game patched with the given proxy DLL."""
    return _options(dll_name)


def _options(dll_name: str, *variables: str) -> str:
    entry = override_entry(dll_name)
    return " ".join([*([f"WINEDLLOVERRIDES={entry}"] if entry else []), *variables, "SteamDeck=0 %command%"])


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
    the proxy `patched_with` (with any proxy when None), with EARLIER_FSR4_VARIABLE as earlier versions wrote them or
    not, or either's launch wrapper alone. Anything the user added to them makes them the user's: theirs to keep, never
    ours to clear."""
    words = _normalized(options).split(" ")
    if len(words) == 2 and words[0].endswith(_WRAPPERS) and words[1].lower() == "%command%":
        return True
    proxies = [patched_with] if patched_with else sorted(VALID_DLL_NAMES)
    ours = {_normalized(_options(dll, *earlier)) for dll in proxies for earlier in ((), (EARLIER_FSR4_VARIABLE,))}
    return _normalized(options) in ours


def carries_earlier_fsr4(options: str | None) -> bool:
    """Whether launch options hold EARLIER_FSR4_VARIABLE, as earlier versions of the plugin wrote it."""
    return options is not None and EARLIER_FSR4_VARIABLE in _normalized(options).split(" ")


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

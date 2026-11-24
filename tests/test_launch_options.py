import pytest

from deckyscaler.domain import bundle, launch_options


@pytest.mark.parametrize(
    ("dll_name", "expected"),
    [
        ("dxgi.dll", "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%"),
        ("winhttp.dll", "WINEDLLOVERRIDES=winhttp=n,b SteamDeck=0 %command%"),
        ("OptiScaler.asi", "SteamDeck=0 %command%"),
    ],
)
def test_managed_options_per_proxy(dll_name, expected):
    assert launch_options.managed(dll_name) == expected


@pytest.mark.parametrize("dll_name", ["dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "winhttp.dll", "wininet.dll"])
def test_options_written_for_a_dll_proxy_are_recognised_as_managed(dll_name):
    assert launch_options.is_managed(launch_options.managed(dll_name))


def test_is_managed_tolerates_extra_whitespace_and_recognises_the_wrapper():
    assert launch_options.is_managed("  WINEDLLOVERRIDES=dxgi=n,b    SteamDeck=0 %command%  ")
    assert launch_options.is_managed("~/deckyscaler/patch %command%")
    assert launch_options.is_managed("~/deckyscaler/unpatch %command%")
    assert launch_options.is_managed("~/fgmod/fgmod %command%")  # the original Decky Framegen's wrapper
    assert launch_options.is_managed("/home/deck/fgmod/fgmod %COMMAND%")  # as its own script printed it


@pytest.mark.parametrize(
    "options",
    [
        "~/deckyscaler/patch %command% -dx12",  # the wrapper, and the game's own arguments
        "gamemoderun ~/deckyscaler/patch %command%",
        "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 gamemoderun %command%",
        "PROTON_FSR4_UPGRADE=1 %command%",
        "~/deckyscaler/patcher %command%",
        "~/my-deckyscaler/patch %command%",  # someone else's script of that name
    ],
)
def test_options_holding_the_plugins_words_and_the_users_are_the_users(options):
    assert not launch_options.is_managed(options)


def test_the_plugins_options_are_told_by_the_proxy_the_game_is_patched_with():
    assert launch_options.is_managed("SteamDeck=0 %command%", "OptiScaler.asi")
    assert not launch_options.is_managed("SteamDeck=0 %command%", "dxgi.dll")  # a tweak of the user's own, then
    assert not launch_options.is_managed(launch_options.managed("winmm.dll"), "dxgi.dll")
    assert launch_options.is_managed(launch_options.managed("dxgi.dll", True), "dxgi.dll")
    assert launch_options.is_managed("SteamDeck=0 %command%")  # with no proxy to go by: any proxy's


@pytest.mark.parametrize("quote", ['"', "'"])
def test_is_managed_recognises_the_quoted_override_earlier_versions_wrote(quote):
    assert launch_options.is_managed(f"WINEDLLOVERRIDES={quote}dxgi=n,b{quote} SteamDeck=0 %command%")


@pytest.mark.parametrize("options", ["", "   ", "mangohud %command%", "WINEDLLOVERRIDES=d3d11=n,b %command%"])
def test_user_options_are_not_managed(options):
    assert not launch_options.is_managed(options)


@pytest.mark.parametrize(
    ("current", "dll_name", "expected"),
    [
        ("", "dxgi.dll", "dxgi=n,b"),
        ("d3d11=n", "winmm.dll", "d3d11=n;winmm=n,b"),
        ("d3d11,dxgi=n;xinput1_3=b", "version.dll", "d3d11,dxgi=n;xinput1_3=b;version=n,b"),
        ("d3d11=n", "OptiScaler.asi", "d3d11=n"),
    ],
)
def test_wine_dll_overrides_append_our_entry_with_wines_separator(current, dll_name, expected):
    assert launch_options.wine_dll_overrides(current, dll_name) == expected


@pytest.mark.parametrize("fsr4_upgrade", [False, True])
@pytest.mark.parametrize("dll_name", ["dxgi.dll", "OptiScaler.asi"])
def test_every_shape_the_plugin_writes_is_recognised_as_managed(dll_name, fsr4_upgrade):
    # Unpatch hands the user's own options back only when it knows the current ones are the plugin's.
    assert launch_options.is_managed(launch_options.managed(dll_name, fsr4_upgrade))


def test_the_panel_gets_every_proxy_with_its_launch_options_and_the_wrapper_commands():
    setup = launch_options.setup_json()

    assert setup["default"] == "dxgi.dll"
    assert [proxy["name"] for proxy in setup["proxies"]][0] == "dxgi.dll"
    assert {proxy["name"] for proxy in setup["proxies"]} == bundle.VALID_DLL_NAMES
    by_name = {proxy["name"]: proxy for proxy in setup["proxies"]}
    assert by_name["winmm.dll"]["launch_options"] == launch_options.managed("winmm.dll")
    assert by_name["OptiScaler.asi"]["launch_options"] == "SteamDeck=0 %command%"
    assert all(proxy["hint"] for proxy in setup["proxies"])
    assert setup["wrapper"] == {"patch": "~/deckyscaler/patch %command%", "unpatch": "~/deckyscaler/unpatch %command%"}


def test_the_wrapper_command_is_recognised_as_the_plugins():
    assert launch_options.is_managed(launch_options.WRAPPER_PATCH)

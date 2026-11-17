"""Libraries the user adds to games: the table of what OptiScaler takes (pinned against its own ini), recognising a
library, the device's entries, and downloading ANR (against a real GitHub listing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deckyscaler.domain import ini_schema, release_assets
from deckyscaler.domain import user_libraries as ul

FIXTURES = Path(__file__).parent / "fixtures"
MASTER_INI = ini_schema.parse((FIXTURES / "optiscaler-ini" / "master-03b37db7.ini").read_text())
SETTINGS = {(s.section, s.key): s for section in MASTER_INI for s in section.settings}
ANR_LISTING = json.loads((FIXTURES / "anr.json").read_text())

# The members of anr-fg-V.B19-addon.zip, as GitHub served it.
ANR_PROVIDER = "Apex Neural Rendering FG"
ANR_MEMBERS = frozenset({
    f"{ANR_PROVIDER}/dlssg/adapters/pack.nrx",
    f"{ANR_PROVIDER}/dlssg/kernels/pack.nrx",
    f"{ANR_PROVIDER}/dlssg/nr_fg.ini",
    f"{ANR_PROVIDER}/dlssg/nvngx_dlssg.dll",
    f"{ANR_PROVIDER}/dlssg/path_table.json",
    f"{ANR_PROVIDER}/dlssg/programs/fg-lite-any-portable-srgb8/pack.nrx",
    f"{ANR_PROVIDER}/dlssg/size_table.json",
    "README.txt", "install.cmd", "install.ps1", "install.sh", "nr_fg_package.json",
    "uninstall.cmd", "uninstall.ps1", "uninstall.sh",
})
# Intel's XeSS SDK zip: its DLLs under bin/, and copies elsewhere (one sorting before bin/).
XESS_SDK = frozenset({
    "bin/libxess.dll", "bin/libxess_dx11.dll", "bin/libxess_fg.dll", "bin/libxell.dll",
    "samples/basic/bin/libxess.dll", "Docs/samples/libxess.dll", "doc/XeSS_SDK_Developer_Guide.pdf", "LICENSE.txt",
})


# ── The table, against OptiScaler's own ini ──────────────────────────────────


@pytest.mark.parametrize("dll", ul.DLLS, ids=lambda dll: dll.name)
def test_every_known_dll_has_its_key_and_selects_values_optiscaler_lists(dll):
    assert (ul.LIBRARIES, dll.path_key) in SETTINGS
    for key, value in dll.upscaler:
        assert value in SETTINGS[key].help.replace(",", " ").split()


@pytest.mark.parametrize("kind", ul.KINDS, ids=lambda kind: kind.name)
def test_every_provider_kind_selects_keys_that_take_a_custom_name(kind):
    for key in kind.selects:
        assert "custom" in SETTINGS[key].help
    for key, value in kind.sets:
        assert value in SETTINGS[key].help.replace(",", " ").split()


def test_a_source_sets_only_keys_optiscaler_has():
    for source in ul.SOURCES.values():
        assert all(key in SETTINGS for key, _ in source.settings)


def test_a_provider_cant_take_a_name_optiscaler_reads_as_its_own_value():
    assert {"auto", "ffx", "dlss", "xess_12", "nukems", "dlssg"} <= ul.RESERVED_NAMES


# ── Recognising a library ────────────────────────────────────────────────────


def test_anrs_zip_is_one_frame_generation_provider_and_its_folder_without_the_installers():
    contents = ul.recognize(ANR_MEMBERS)

    assert contents.providers == (ul.Provider(ANR_PROVIDER, ("dlssg",), ANR_PROVIDER),)
    assert contents.dlls == ()
    assert set(contents.files) == {p for p in ANR_MEMBERS if p.startswith(f"{ANR_PROVIDER}/")}


def test_the_xess_sdk_is_its_dlls_nearest_the_top_in_the_tables_order():
    contents = ul.recognize(XESS_SDK)

    assert contents.providers == ()
    assert contents.dlls == (
        ul.Dll("libxess.dll", "bin/libxess.dll"),
        ul.Dll("libxess_dx11.dll", "bin/libxess_dx11.dll"),
        ul.Dll("libxess_fg.dll", "bin/libxess_fg.dll"),
        ul.Dll("libxell.dll", "bin/libxell.dll"),
    )
    assert contents.files == ("bin/libxell.dll", "bin/libxess.dll", "bin/libxess_dx11.dll", "bin/libxess_fg.dll")


def test_a_dll_is_known_whatever_the_case_of_its_name():
    contents = ul.recognize(frozenset({"LibXess.DLL"}))

    assert contents.dlls == (ul.Dll("libxess.dll", "LibXess.DLL"),)


def test_a_standard_name_inside_a_provider_is_the_providers_not_a_dll_of_its_own():
    contents = ul.recognize(frozenset({"Uniscaler/ffx/amd_fidelityfx_upscaler_dx12.dll", "Uniscaler/ffx_vk/x.dll"}))

    assert contents.providers == (ul.Provider("Uniscaler", ("ffx", "ffx_vk"), "Uniscaler"),)
    assert contents.dlls == ()


@pytest.mark.parametrize(
    "paths",
    [
        frozenset({"README.txt", "setup.exe"}),
        frozenset({"amd_fidelityfx_denoiser_dx12.dll"}),  # comes along with a library, serves no slot alone
        frozenset({"Thing/notakind/x.dll"}),
        frozenset({"Thing/ffx/readme.txt"}),
    ],
)
def test_nothing_a_slot_can_use_is_no_library(paths):
    assert ul.recognize(paths) == ul.NOTHING_KNOWN


def test_a_provider_named_as_one_of_optiscalers_own_values_is_refused():
    assert ul.recognize(frozenset({"Auto/ffx/x.dll"})) == ul.RESERVED_NAME


# ── A library on the device ──────────────────────────────────────────────────


def test_a_library_serves_the_slots_of_its_providers_and_dlls_and_is_called_by_name_and_version():
    library = ul.Library("x", "XeSS SDK", "3.0.2", ul.YOUR_FILE, None, (), ul.recognize(XESS_SDK).dlls, (), (), "")

    assert library.slots == (ul.UPSCALER, ul.FRAME_GENERATION)
    assert library.label == "XeSS SDK 3.0.2"
    assert ul.Library("y", "ANR", None, ul.YOUR_FILE, None, (), (), (), (), "").label == "ANR"


def test_what_the_user_picked_is_named_after_its_one_provider_or_dll_else_after_the_pick():
    provider = ul.added(ul.recognize(ANR_MEMBERS), "anr-fg-V.B19-addon.zip", None, set(), "t")
    lone_dll = ul.added(ul.recognize(frozenset({"libxess.dll"})), "libxess.dll", "2.0.2.68", set(), "t")
    sdk = ul.added(ul.recognize(XESS_SDK), "XeSS_SDK_3.0.2.zip", "2.0.2.68", set(), "t")

    assert (provider.id, provider.name, provider.version, provider.origin) == ("apex-neural-rendering-fg", ANR_PROVIDER, None, ul.YOUR_FILE)
    assert (lone_dll.id, lone_dll.name, lone_dll.version) == ("libxess-dll-2-0-2-68", "libxess.dll", "2.0.2.68")
    assert (sdk.id, sdk.name, sdk.version) == ("xess-sdk-3-0-2", "XeSS_SDK_3.0.2", None)


def test_the_same_library_isnt_added_twice():
    contents = ul.recognize(frozenset({"libxess.dll"}))

    assert ul.added(contents, "libxess.dll", "2.0.2.68", {"libxess-dll-2-0-2-68"}, "t") == ul.ALREADY_ADDED


def test_an_entry_reads_back_as_the_library_it_was_written_from():
    library = ul.downloaded(ul.releases(ul.ANR, ANR_LISTING)[0], ul.recognize(ANR_MEMBERS), "2026-11-17T00:00:00+00:00")

    assert ul.parse_entry(json.loads(json.dumps(ul.entry_json(library)))) == library


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"id": "x"},
        {**ul.entry_json(ul.added(ul.recognize(frozenset({"libxess.dll"})), "a", None, set(), "t")), "dlls": []},
        {**ul.entry_json(ul.added(ul.recognize(frozenset({"libxess.dll"})), "a", None, set(), "t")), "files": "libxess.dll"},
    ],
)
def test_an_entry_that_isnt_a_library_is_none(data):
    assert ul.parse_entry(data) is None


# ── Downloading ANR ──────────────────────────────────────────────────────────


def test_anr_offers_its_ten_newest_addons_with_their_checksums():
    releases = ul.releases(ul.ANR, ANR_LISTING)

    assert len(releases) == ul.SHOWN
    newest = releases[0]
    assert (newest.id, newest.version, newest.size, newest.unsupported) == ("anr-v-b19", "V.B19", 3418118, None)
    assert newest.url == "https://github.com/apex-compute/ANR/releases/download/FG-V.B19/anr-fg-V.B19-addon.zip"
    assert newest.sha256 == "70107373e0f9744875fcbb7f46133432202ce7f132fdfff14259b8a85fba3f13"
    assert [r.version for r in releases[:3]] == ["V.B19", "V.B18", "V.B17"]


def test_a_release_without_one_addon_says_why():
    addon = next(a for a in ANR_LISTING[0]["assets"] if a["name"].endswith("-addon.zip"))
    listing = [
        {"tag_name": "FG-V.B20", "published_at": "2026-11-18T00:00:00Z", "prerelease": False, "assets": []},
        {**ANR_LISTING[0], "assets": [{**addon, "state": "starter"}]},
    ]

    releases = ul.releases(ul.ANR, listing)

    assert releases[0].unsupported == release_assets.NO_ARCHIVE
    assert releases[1].unsupported == release_assets.UPLOADING


def test_a_downloaded_release_becomes_its_sources_library_with_the_sources_settings():
    library = ul.downloaded(ul.releases(ul.ANR, ANR_LISTING)[0], ul.recognize(ANR_MEMBERS), "t")

    assert (library.id, library.name, library.version, library.source) == ("anr-v-b19", ANR_PROVIDER, "V.B19", ul.ANR)
    assert library.label == "Apex Neural Rendering FG V.B19"
    assert library.settings == ((("FrameGen", "DisableHudless"), "false"),)


def test_the_dialog_lists_the_newest_releases_then_downloaded_ones_no_longer_among_them():
    releases = ul.releases(ul.ANR, ANR_LISTING)
    contents = ul.recognize(ANR_MEMBERS)
    b19 = ul.downloaded(releases[0], contents, "t")
    old = ul.Library("anr-v-b01", ANR_PROVIDER, "V.B01", ul.DOWNLOADED, ul.ANR, contents.providers, (), contents.files, (), "t")
    mine = ul.added(contents, "x.zip", None, set(), "t")

    rows = ul.rows(ul.ANR, releases, [b19, old, mine], {"anr-v-b19": 5_000_000})

    assert rows[0] == release_assets.Row("anr-v-b19", "V.B19", "20261117", release_assets.INSTALLED, None, 5_000_000)
    assert rows[1].state == release_assets.AVAILABLE and rows[1].size == 3161126
    assert rows[-1] == release_assets.Row("anr-v-b01", "V.B01", "", release_assets.INSTALLED, None, 0)
    assert len(rows) == ul.SHOWN + 1


def test_of_two_providers_of_one_name_the_one_nearest_the_top_is_kept():
    contents = ul.recognize(frozenset({"a/b/Uniscaler/ffx/x.dll", "zz/Uniscaler/ffx/x.dll"}))

    assert contents.providers == (ul.Provider("Uniscaler", ("ffx",), "zz/Uniscaler"),)


def test_a_library_is_listed_with_what_it_serves_takes_and_which_games_have_it():
    library = ul.downloaded(ul.releases(ul.ANR, ANR_LISTING)[0], ul.recognize(ANR_MEMBERS), "t")

    assert ul.library_json(library, 5_700_000, ["Hades II"]) == {
        "id": "anr-v-b19", "label": "Apex Neural Rendering FG V.B19", "origin": ul.DOWNLOADED,
        "slots": [ul.FRAME_GENERATION], "turns_on": [ul.FRAME_GENERATION], "size": 5_700_000, "games": ["Hades II"],
    }
    assert ul.space_needed(3_418_118) == 4 * 3_418_118


def test_a_provider_and_an_upscaler_dll_switch_on_by_themselves_and_a_frame_generation_dll_doesnt():
    sdk = ul.added(ul.recognize(XESS_SDK), "sdk.zip", None, set(), "t")
    fg_only = ul.added(ul.recognize(frozenset({"libxess_fg.dll"})), "fg", None, set(), "t")

    assert sdk.slots == (ul.UPSCALER, ul.FRAME_GENERATION) and sdk.turns_on == (ul.UPSCALER,)
    assert fg_only.turns_on == ()
    assert ul.added(ul.recognize(ANR_MEMBERS), "anr.zip", None, set(), "t").turns_on == (ul.FRAME_GENERATION,)


def test_the_frontend_words_every_slot_and_every_refusal_the_backend_gives():
    import re

    wording = (Path(__file__).parent.parent / "src" / "presentation" / "libraries.ts").read_text()

    def table(name: str) -> set[str]:
        body = wording[wording.index(f"const {name}") : wording.index("};", wording.index(f"const {name}"))]
        return set(re.findall(r'^\s*"?([a-z-]+)"?:', body, re.MULTILINE))

    assert table("SLOT_LABELS") == set(ul.SLOTS)
    assert table("REFUSALS") == {ul.NOTHING_KNOWN, ul.RESERVED_NAME, ul.ALREADY_ADDED}


def test_a_source_says_what_its_library_serves_and_where_it_comes_from():
    library = ul.downloaded(ul.releases(ul.ANR, ANR_LISTING)[0], ul.recognize(ANR_MEMBERS), "t")

    assert ul.sources_json() == [
        {"id": ul.ANR, "label": ANR_PROVIDER, "slots": [ul.FRAME_GENERATION], "repository": "apex-compute/ANR"},
    ]
    assert library.slots == ul.SOURCES[ul.ANR].slots  # what the page says before the download is what it serves

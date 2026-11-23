"""How a game's libraries go into it: copies, and the ini keys that select and find the picked ones."""

from __future__ import annotations

from deckyscaler.domain import library_placement as lp
from deckyscaler.domain import user_libraries as ul
from deckyscaler.domain.library_choice import ToPlace
from deckyscaler.domain.patch_plan import Copy
from deckyscaler.domain.settings_layers import Owned

FG, UP = ul.FRAME_GENERATION, ul.UPSCALER
ANR_NAME = "Apex Neural Rendering FG"


def _library(library_id: str, *files: str, settings=()) -> ul.Library:
    contents = ul.recognize(frozenset(files))
    return ul.Library(
        library_id, library_id.upper(), "1", ul.YOUR_FILE, None, contents.providers, contents.dlls, contents.files, settings, ""
    )


ANR = _library(
    "anr",
    f"{ANR_NAME}/dlssg/nvngx_dlssg.dll", f"{ANR_NAME}/dlssg/nr_fg.ini", f"{ANR_NAME}/dlssg/programs/a/pack.nrx", "install.sh",
    settings=((("FrameGen", "DisableHudless"), "false"),),
)
XESS = _library("xess", "bin/libxess.dll", "bin/libxess_dx11.dll", "bin/libxess_fg.dll", "bin/libxell.dll")


def picked(*picks) -> ToPlace:
    return ToPlace(tuple(picks), ())


FILES = {"anr": "/lib/anr/files", "xess": "/lib/xess/files", "a": "/lib/a/files", "b": "/lib/b/files", "u": "/lib/u/files"}


def test_a_frame_generation_provider_is_copied_into_custom_and_selected_with_what_its_kind_and_source_need():
    placement = lp.place(picked((FG, ANR)), "OptiScaler", FILES)

    folder = f"OptiScaler/custom/{ANR_NAME}"
    assert set(placement.copies) == {
        Copy(f"/lib/anr/files/{ANR_NAME}/dlssg/nvngx_dlssg.dll", f"{folder}/dlssg/nvngx_dlssg.dll"),
        Copy(f"/lib/anr/files/{ANR_NAME}/dlssg/nr_fg.ini", f"{folder}/dlssg/nr_fg.ini"),
        Copy(f"/lib/anr/files/{ANR_NAME}/dlssg/programs/a/pack.nrx", f"{folder}/dlssg/programs/a/pack.nrx"),
    }
    assert placement.layer == {
        ("FrameGen", "FGNvngxReplacement"): Owned(ANR_NAME, "ANR 1"),
        ("FrameGen", "FGInput"): Owned("nvngxfg", "ANR 1"),
        ("FrameGen", "DisableHudless"): Owned("false", "ANR 1"),
    }
    assert placement.settings_files == {f"{folder}/dlssg/nr_fg.ini"}
    assert placement.owned_dirs == (folder,)
    assert placement.recorded == ({"slot": FG, "id": "anr", "label": "ANR 1"},)


def test_dlls_picked_as_the_upscaler_go_beside_optiscaler_and_select_their_upscaler_per_api():
    placement = lp.place(picked((UP, XESS)), "OptiScaler", FILES)

    assert placement.copies == (
        Copy("/lib/xess/files/bin/libxess.dll", "OptiScaler/user-libraries/libxess.dll"),
        Copy("/lib/xess/files/bin/libxess_dx11.dll", "OptiScaler/user-libraries/libxess_dx11.dll"),
    )
    assert placement.layer == {
        ("Libraries", "XeSSPath"): Owned("OptiScaler\\user-libraries\\libxess.dll", "XESS 1"),
        ("Upscalers", "Dx12Upscaler"): Owned("xess", "XESS 1"),
        ("Upscalers", "VulkanUpscaler"): Owned("xess", "XESS 1"),
        # libxess.dll comes first in the table: DX11 runs it through DX12 rather than the Arc-only DX11 one.
        ("Upscalers", "Dx11Upscaler"): Owned("xess_12", "XESS 1"),
        ("Libraries", "XeSSDx11Path"): Owned("OptiScaler\\user-libraries\\libxess_dx11.dll", "XESS 1"),
    }
    assert placement.owned_dirs == () and placement.settings_files == frozenset()


def test_dlls_picked_for_frame_generation_are_only_pointed_at():
    placement = lp.place(picked((FG, XESS)), "OptiScaler", FILES)

    assert [copy.destination for copy in placement.copies] == [
        "OptiScaler/user-libraries/libxess_fg.dll", "OptiScaler/user-libraries/libxell.dll",
    ]
    assert set(placement.layer) == {("Libraries", "XeFGPath"), ("Libraries", "XeLLPath")}


def test_one_library_in_both_slots_is_placed_once_with_both_slots_keys():
    placement = lp.place(picked((UP, XESS), (FG, XESS)), "OptiScaler", FILES)

    assert len(placement.copies) == 4
    assert ("Libraries", "XeFGPath") in placement.layer and ("Upscalers", "Dx12Upscaler") in placement.layer
    assert placement.recorded == ({"slot": UP, "id": "xess", "label": "XESS 1"}, {"slot": FG, "id": "xess", "label": "XESS 1"})


def test_a_file_both_slots_libraries_have_is_the_upscalers():
    upscaler = _library("a", "amd_fidelityfx_dx12.dll")
    frame_generation = _library("b", "amd_fidelityfx_dx12.dll")

    placement = lp.place(picked((UP, upscaler), (FG, frame_generation)), "OptiScaler", FILES)

    assert placement.copies == (Copy("/lib/a/files/amd_fidelityfx_dx12.dll", "OptiScaler/user-libraries/amd_fidelityfx_dx12.dll"),)
    assert placement.layer[("Libraries", "FfxDx12Path")].library == "A 1"


def test_a_file_serving_no_slot_comes_along_with_its_library():
    library = _library("a", "amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_denoiser_dx12.dll")

    placement = lp.place(picked((UP, library)), "OptiScaler", FILES)

    assert ("Libraries", "FfxDx12RRPath") in placement.layer


def test_a_providers_kinds_for_another_slot_select_nothing():
    library = _library("u", "Uniscaler/ffx/u.dll", "Uniscaler/dlssg/u.dll")

    placement = lp.place(picked((UP, library)), "OptiScaler", FILES)

    assert placement.layer[("Upscalers", "Dx12Upscaler")] == Owned("Uniscaler", "U 1")
    assert ("FrameGen", "FGNvngxReplacement") not in placement.layer
    assert len(placement.copies) == 2 and placement.owned_dirs == ("OptiScaler/custom/Uniscaler",)


def test_a_picked_librarys_provider_for_another_slot_goes_in_too_selected_by_nothing():
    library = _library("u", "Upscaling/ffx/u.dll", "Generating/dlssg/g.dll")

    placement = lp.place(picked((UP, library)), "OptiScaler", FILES)

    assert placement.owned_dirs == ("OptiScaler/custom/Generating", "OptiScaler/custom/Upscaling")
    assert ("FrameGen", "FGNvngxReplacement") not in placement.layer


def test_an_offered_library_goes_in_for_optiscalers_menu_and_sets_nothing():
    placement = lp.place(ToPlace(((UP, XESS),), (ANR,)), "OptiScaler", FILES)

    folder = f"OptiScaler/custom/{ANR_NAME}"
    assert Copy(f"/lib/anr/files/{ANR_NAME}/dlssg/nvngx_dlssg.dll", f"{folder}/dlssg/nvngx_dlssg.dll") in placement.copies
    assert placement.owned_dirs == (folder,) and placement.settings_files == {f"{folder}/dlssg/nr_fg.ini"}
    assert placement.layer == lp.place(picked((UP, XESS)), "OptiScaler", FILES).layer  # nor DisableHudless, its source's
    assert placement.recorded == (
        {"slot": UP, "id": "xess", "label": "XESS 1"}, {"slot": None, "id": "anr", "label": "ANR 1"},
    )


def test_nothing_picked_places_nothing():
    assert lp.place(picked(), "OptiScaler", FILES) == lp.Placement((), {}, frozenset(), (), ())


def test_keys_the_games_libraries_no_longer_set_are_released():
    previous = {("FrameGen", "FGInput"): Owned("nvngxfg", "ANR"), ("Upscalers", "Dx12Upscaler"): Owned("xess", "X")}

    assert lp.released(previous, {("Upscalers", "Dx12Upscaler"): Owned("ffx", "Y")}) == {("FrameGen", "FGInput")}


def test_a_providers_folder_holds_its_own_files_and_the_librarys_dlls_go_beside_optiscaler():
    library = _library("u", "Uniscaler/ffx/u.dll", "libxess.dll")

    placement = lp.place(picked((UP, library)), "OptiScaler", FILES)

    assert [copy.destination for copy in placement.copies] == [
        "OptiScaler/custom/Uniscaler/ffx/u.dll", "OptiScaler/user-libraries/libxess.dll",
    ]


def test_a_provider_serving_both_slots_is_one_folder_of_the_game():
    library = _library("u", "Uniscaler/ffx/u.dll", "Uniscaler/dlssg/u.dll")

    placement = lp.place(picked((UP, library), (FG, library)), "OptiScaler", FILES)

    assert placement.owned_dirs == ("OptiScaler/custom/Uniscaler",)
    assert placement.layer[("FrameGen", "FGNvngxReplacement")] == Owned("Uniscaler", "U 1")


def test_a_file_picked_for_frame_generation_never_selects_the_upscaler():
    placement = lp.place(picked((FG, _library("a", "amd_fidelityfx_dx12.dll"))), "OptiScaler", FILES)

    assert set(placement.layer) == {("Libraries", "FfxDx12Path")}


def test_the_folders_only_the_plugins_libraries_fill_are_user_libraries_and_each_providers():
    assert lp.plugin_dirs("OptiScaler", [ANR, XESS]) == (
        "OptiScaler/user-libraries", f"OptiScaler/custom/{ANR_NAME}",
    )
    assert lp.plugin_dirs("OptiScaler", [ANR, ANR]) == ("OptiScaler/user-libraries", f"OptiScaler/custom/{ANR_NAME}")
    assert lp.plugin_dirs("OptiScaler", []) == ("OptiScaler/user-libraries",)

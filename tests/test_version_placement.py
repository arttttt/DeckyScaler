"""Placing a library version in a game directory: the plan (unit) against the real archives' file lists."""

from __future__ import annotations

import pytest

from deckyscaler.domain import library
from deckyscaler.domain.patch_plan import Copy, Link, Move, PlanError
from deckyscaler.domain.patch_record import PatchRecord, Placed
from deckyscaler.domain.version_placement import (
    placed_dirs,
    Request, is_for_the_game, linked_files, lost_files, placed_every_file, plan_patch,
)

# The files of the real OptiScaler 0.9.4 and nightly-20261023 archives (7zzs l).
V094 = frozenset({
    "!!.txt", "D3D12_Optiscaler/D3D12Core.dll", "Licenses/DirectX_LICENSE.txt", "Licenses/XeSS_LICENSE.txt",
    "OptiScaler.dll", "OptiScaler.ini", "amd_fidelityfx_dx12.dll", "amd_fidelityfx_framegeneration_dx12.dll",
    "amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_vk.dll", "dlssg_to_fsr3_amd_is_better.dll", "fakenvapi.dll",
    "fakenvapi.ini", "libxell.dll", "libxess.dll", "libxess_dx11.dll", "libxess_fg.dll", "setup_linux.sh",
    "setup_windows.bat",
})
V10 = frozenset({
    "Licenses/DirectX_LICENSE.txt", "OptiScaler.dll", "OptiScaler.ini", "OptiScaler/D3D12_OptiScaler/D3D12Core.dll",
    "OptiScaler/Streamlined_fetcher_windows.bat", "OptiScaler/amd_fidelityfx_upscaler_dx12.dll",
    "OptiScaler/libxess.dll", "OptiScaler/dlssg_to_fsr3_amd_is_better.dll", "setup_linux.sh", "setup_windows.bat",
})


def placed(operations) -> dict[str, str]:
    return {op.destination: op.source for op in operations if isinstance(op, Copy | Link)}


def test_v10_mirrors_its_archive_with_the_support_files_in_the_subfolder():
    operations = plan_patch(frozenset({"Game.exe"}), V10, library.FAMILIES["10"], Request("dxgi.dll"))

    assert placed(operations) == {
        "dxgi.dll": "OptiScaler.dll",
        "OptiScaler.ini": "OptiScaler.ini",
        "OptiScaler/D3D12_OptiScaler/D3D12Core.dll": "OptiScaler/D3D12_OptiScaler/D3D12Core.dll",
        "OptiScaler/amd_fidelityfx_upscaler_dx12.dll": "OptiScaler/amd_fidelityfx_upscaler_dx12.dll",
        "OptiScaler/libxess.dll": "OptiScaler/libxess.dll",
        "OptiScaler/dlssg_to_fsr3_amd_is_better.dll": "OptiScaler/dlssg_to_fsr3_amd_is_better.dll",
    }


def test_0_9_puts_everything_next_to_the_proxy_and_leaves_out_what_is_for_people():
    operations = plan_patch(frozenset({"Game.exe"}), V094, library.FAMILIES["0.9"], Request("winmm.dll"))
    files = placed(operations)

    assert files["winmm.dll"] == "OptiScaler.dll"
    assert {"libxess.dll", "fakenvapi.ini", "D3D12_Optiscaler/D3D12Core.dll"} <= files.keys()
    assert not {"!!.txt", "setup_linux.sh", "setup_windows.bat", "Licenses/XeSS_LICENSE.txt", "OptiScaler.dll"} & files.keys()


@pytest.mark.parametrize("path", ["Licenses/X.txt", "!!.txt", "setup_linux.sh", "OptiScaler/fetch.bat"])
def test_licenses_notes_and_setup_scripts_stay_in_the_archive(path):
    assert not is_for_the_game(path)


def test_the_games_files_are_backed_up_and_only_one_proxy_loads():
    entries = frozenset({"Game.exe", "libxess.dll", "version.dll", "dxgi.dll"})

    operations = plan_patch(entries, V094, library.FAMILIES["0.9"], Request("dxgi.dll"))

    assert Move("version.dll", "version.dll.b") in operations  # another proxy would load OptiScaler again
    assert Move("dxgi.dll", "dxgi.dll.b") in operations
    assert operations.index(Move("libxess.dll", "libxess.dll.b")) < operations.index(Link("libxess.dll", "libxess.dll"))


def test_a_fresh_ini_is_the_versions_and_a_kept_one_stays():
    fresh = plan_patch(frozenset(), V10, library.FAMILIES["10"], Request("dxgi.dll"))
    kept = plan_patch(frozenset({"OptiScaler.ini"}), V10, library.FAMILIES["10"], Request("dxgi.dll"))

    # The user's settings go in after placing (Patcher.apply_settings).
    assert Copy("OptiScaler.ini", "OptiScaler.ini") in fresh
    assert Copy("OptiScaler.ini", "OptiScaler.ini") not in kept


def test_asking_to_reset_the_ini_backs_up_the_games_and_places_the_versions():
    operations = plan_patch(frozenset({"OptiScaler.ini"}), V10, library.FAMILIES["10"], Request("dxgi.dll", True))

    assert operations.index(Move("OptiScaler.ini", "OptiScaler.ini.b")) < operations.index(
        Copy("OptiScaler.ini", "OptiScaler.ini")
    )


@pytest.mark.parametrize(
    ("files", "request_", "message"),
    [
        (V10, Request("d3d11.dll"), "Invalid proxy DLL name: d3d11.dll"),
        (V10 - {"OptiScaler.ini"}, Request("dxgi.dll"), "lacks OptiScaler.ini"),
    ],
)
def test_what_cannot_be_placed_is_refused(files, request_, message):
    with pytest.raises(PlanError, match=message):
        plan_patch(frozenset(), files, library.FAMILIES["10"], request_)


def test_the_files_linked_at_their_own_paths_are_those_for_the_game_but_the_injector_and_the_ini():
    files = frozenset({"OptiScaler.dll", "OptiScaler.ini", "libxess.dll", "OptiScaler/D3D12Core.dll", "!!.txt"})

    assert linked_files(files) == {"libxess.dll", "OptiScaler/D3D12Core.dll"}
    assert linked_files(V094) == {  # what a patch links at its own path: the rule plan_patch follows
        destination for destination, source in placed(plan_patch(frozenset(), V094, library.FAMILIES["0.9"], Request("dxgi.dll"))).items()
        if destination == source and destination != "OptiScaler.ini"
    }


def _installed(files: tuple[str, ...] | None) -> library.Installed:
    return library.Installed("stable-0.9.4", library.STABLE, "0.9.4", "20260718", "0.9", "u", "0" * 64, "t", files)


def test_a_version_has_lost_the_files_a_game_gets_that_are_gone_from_it():
    unpacked = _installed(("OptiScaler.dll", "libxess.dll", "Licenses/XeSS_LICENSE.txt", "!!.txt"))

    assert lost_files(unpacked, frozenset(unpacked.files)) == frozenset()
    assert lost_files(unpacked, frozenset({"Licenses/XeSS_LICENSE.txt", "!!.txt"})) == {"OptiScaler.dll", "libxess.dll"}
    assert lost_files(unpacked, frozenset({"OptiScaler.dll", "libxess.dll"})) == frozenset()  # a licence is no loss to a game
    assert lost_files(_installed(None), frozenset({"OptiScaler.dll"})) == frozenset()  # no list to check against


def test_a_patch_placed_every_file_its_version_links_or_lacks_one_that_came_back():
    patch = PatchRecord((Placed("dxgi.dll", "l"), Placed("libxess.dll", "l"), Placed("OptiScaler.ini", None)), (), ())

    assert placed_every_file(patch, frozenset({"OptiScaler.dll", "OptiScaler.ini", "libxess.dll", "!!.txt"}))
    assert not placed_every_file(patch, frozenset({"OptiScaler.dll", "libxess.dll", "libxess_dx11.dll"}))


def test_everything_but_the_ini_is_a_symlink_into_the_library():
    operations = plan_patch(frozenset({"Game.exe", "libxess.dll"}), V094, library.FAMILIES["0.9"], Request("dxgi.dll"))

    assert Link("OptiScaler.dll", "dxgi.dll") in operations
    assert Link("libxess.dll", "libxess.dll") in operations
    assert Copy("OptiScaler.ini", "OptiScaler.ini") in operations  # OptiScaler writes its ini: never shared
    assert not any(isinstance(op, Copy) and op.destination != "OptiScaler.ini" for op in operations)


DRIVER = "/home/deck/.local/share/Steam/steamapps/compatdata/730/pfx/drive_c/windows/system32/amdxcffx64.dll"


@pytest.mark.parametrize(("files", "family", "where"), [(V10, "10", "OptiScaler/amdxcffx64.dll"), (V094, "0.9", "amdxcffx64.dll")])
def test_the_fsr4_driver_is_linked_where_optiscaler_looks_for_it(files, family, where):
    operations = plan_patch(frozenset({"Game.exe"}), files, library.FAMILIES[family], Request("dxgi.dll", fsr4_driver=DRIVER))

    assert Link(DRIVER, where) in operations


def test_a_driver_dll_already_there_is_the_users_and_stays():
    entries = frozenset({"Game.exe", "OptiScaler/amdxcffx64.dll"})

    operations = plan_patch(entries, V10, library.FAMILIES["10"], Request("dxgi.dll", fsr4_driver=DRIVER))

    assert not any(getattr(op, "destination", None) == "OptiScaler/amdxcffx64.dll" for op in operations)
    assert not any(isinstance(op, Move) and op.source == "OptiScaler/amdxcffx64.dll" for op in operations)


def test_without_a_driver_to_fetch_nothing_is_linked_for_it():
    operations = plan_patch(frozenset(), V10, library.FAMILIES["10"], Request("dxgi.dll"))

    assert not any(str(getattr(op, "destination", "")).endswith("amdxcffx64.dll") for op in operations)


def test_the_users_libraries_are_copied_in_after_the_version_and_whatever_they_replace_is_backed_up():
    copy = Copy("/libraries/anr/files/ANR/dlssg/a.dll", "OptiScaler/custom/ANR/dlssg/a.dll")

    operations = plan_patch(
        frozenset({"Game.exe", "OptiScaler/custom/ANR/dlssg/a.dll"}), V10, library.FAMILIES["10"], Request("dxgi.dll", libraries=(copy,))
    )

    assert operations[-2:] == (Move(copy.destination, f"{copy.destination}.b"), copy)


def test_the_directories_a_version_is_linked_into_go_deepest_first_and_the_games_own_last():
    v10 = frozenset({
        "OptiScaler.dll", "OptiScaler.ini", "OptiScaler/libxess.dll", "OptiScaler/D3D12_OptiScaler/D3D12Core.dll",
        "OptiScaler/Streamlined_fetcher_windows.bat", "Licenses/LICENSE.txt",
    })
    v09 = frozenset({"OptiScaler.dll", "libxess.dll", "D3D12_Optiscaler/D3D12Core.dll"})

    assert placed_dirs(v10) == ("OptiScaler/D3D12_OptiScaler", "OptiScaler", "")
    assert placed_dirs(v09) == ("D3D12_Optiscaler", "")
    assert placed_dirs(frozenset({"OptiScaler.dll"})) == ("",)  # nothing it links but what the game's own holds
    # A directory holding only directories is looked into too: another version may have linked files right in it.
    assert placed_dirs(frozenset({"OptiScaler/D3D12_OptiScaler/D3D12Core.dll"})) == ("OptiScaler/D3D12_OptiScaler", "OptiScaler", "")

"""FSR 4 as OptiScaler brings it: the rules (unit), and what a patched game's status says of it and what a patch no
longer asks of Proton (integration)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conftest import NIGHTLY, STABLE, add_gpu, fixed_file_info, pe_dll, run, write
from deckyscaler.domain import fsr4, launch_options, marker, patch_record

# The class names of the four providers as AMD's upscaler DLL names them (FidelityFX SDK 2.4.0, FSR 4.1.2).
FP8_CLASS, INT8_CLASS = b".?AVffxProvider_FSR4@@", b".?AVffxProvider_FSR4_Int8@@"
RDNA2_CLASS, LITE_CLASS = b".?AVffxProvider_FSR4_Int8_Navi2@@", b".?AVffxProvider_FSR4Lite_Int8@@"
SDK_2_4 = pe_dll({".text": b"code", ".data": b"\0".join([FP8_CLASS, INT8_CLASS, RDNA2_CLASS, LITE_CLASS]),
                  ".rsrc": fixed_file_info(4, 1, 2, 4555)})
SDK_2_3 = pe_dll({".data": b"\0".join([FP8_CLASS, INT8_CLASS]), ".rsrc": fixed_file_info(4, 1, 1, 2740)})

# ── unit: rules ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("rtti", "models"),
    [
        (b"\0".join([b"x", LITE_CLASS, RDNA2_CLASS, INT8_CLASS, FP8_CLASS, b"y"]), (fsr4.FP8, fsr4.INT8, fsr4.INT8_RDNA2, fsr4.INT8_LITE)),
        (b"\0".join([FP8_CLASS, INT8_CLASS]), (fsr4.FP8, fsr4.INT8)),  # SDK 2.3.0, FSR 4.1.1
        (FP8_CLASS, (fsr4.FP8,)),  # SDK 2.2.0, FSR 4.1.0
        (b"\0".join([INT8_CLASS, RDNA2_CLASS, LITE_CLASS]), (fsr4.INT8, fsr4.INT8_RDNA2, fsr4.INT8_LITE)),
        (b".?AVffxProvider_FSR3@@", ()),
        (b"", ()),
    ],
    ids=["sdk-2.4", "sdk-2.3", "sdk-2.2", "int8-family-not-fp8", "fsr3-only", "nothing"],
)
def test_the_models_a_dll_carries_are_its_providers_classes_in_ffxs_order(rtti, models):
    assert fsr4.models(rtti) == models


def test_only_amds_vendor_id_is_amd():
    assert fsr4.is_amd("0x1002\n")
    assert fsr4.is_amd("0X1002")
    assert not fsr4.is_amd("0x10de\n")
    assert not fsr4.is_amd("")


EARLIER_OPTIONS = "WINEDLLOVERRIDES=dxgi=n,b PROTON_FSR4_UPGRADE=1 SteamDeck=0 %command%"
"""The launch options earlier versions of the plugin wrote for a game patched with dxgi.dll on a Proton that fetches FSR
4's driver DLL."""
PREFIX_DLL = "/home/deck/.local/share/Steam/steamapps/compatdata/730/pfx/drive_c/windows/system32/amdxcffx64.dll"


def details(placed: list[dict], options: str = "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%") -> dict:
    record = patch_record.PatchRecord(tuple(patch_record.Placed(p["path"], p["sha256"]) for p in placed), (), ())
    return {**patch_record.to_json(record, True), "launch_options": options}


@pytest.mark.parametrize(
    ("placed", "options", "earlier"),
    [
        ([{"path": "OptiScaler/amdxcffx64.dll", "sha256": f"link:{PREFIX_DLL}"}], "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%", True),
        ([{"path": "amdxcffx64.dll", "sha256": f"link:{PREFIX_DLL}"}], "", True),  # OptiScaler 0.9 keeps it in the root
        ([], EARLIER_OPTIONS, True),
        ([], f'WINEDLLOVERRIDES="dxgi=n,b"  {launch_options.EARLIER_FSR4_VARIABLE} SteamDeck=0 %command%', True),
        ([{"path": "OptiScaler/amdxcffx64.dll", "sha256": "ab" * 32}], "", False),  # a copy is no driver link of ours
        ([{"path": "OptiScaler/libxess.dll", "sha256": "link:/x/libxess.dll"}], "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%", False),
        ([], "PROTON_FSR4_UPGRADE=10 %command%", False),  # a word of the user's own, not the plugin's
    ],
    ids=["driver-link-v10", "driver-link-v0.9", "variable", "variable-quoted", "a-copy", "nothing-earlier", "other-word"],
)
def test_an_earlier_fsr4_patch_is_told_by_its_driver_link_or_its_variable(placed, options, earlier):
    assert marker.earlier_fsr4(details(placed, options)) is earlier


def test_a_record_that_doesnt_read_is_told_by_its_launch_options_alone():
    assert marker.earlier_fsr4({"launch_options": EARLIER_OPTIONS})
    assert not marker.earlier_fsr4({})


# ── integration: through the plugin ──────────────────────────────────────────


def with_upscaler(plugin_home: Path, version_id: str, upscaler: str, data: bytes) -> None:
    """The library version's upscaler DLL, which a game patched with it links to."""
    write(plugin_home / "library" / "versions" / version_id / "files" / upscaler, data)


@pytest.mark.parametrize(
    ("version_id", "upscaler", "dll", "expected"),
    [
        (NIGHTLY, "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", SDK_2_4,
         {"version": "4.1.2.4555", "models": ["fp8", "int8", "int8-rdna2", "int8-lite"]}),
        (STABLE, "amd_fidelityfx_upscaler_dx12.dll", SDK_2_3, {"version": "4.1.1.2740", "models": ["fp8", "int8"]}),
    ],
    ids=["nightly", "stable"],
)
def test_a_patched_game_on_amd_tells_the_fsr4_its_optiscaler_carries(plugin, plugin_home, steam_library, amd_gpu,
                                                                       version_id, upscaler, dll, expected):
    with_upscaler(plugin_home, version_id, upscaler, dll)
    steam_library.add_game("730", "Fsr Game")
    assert run(plugin.patch_game("730", "dxgi.dll", "", version_id))["status"] == "success"

    assert run(plugin.get_game_status("730"))["fsr4"] == expected


def test_an_upscaler_without_fsr4_says_it_carries_none(plugin, plugin_home, steam_library, amd_gpu):
    with_upscaler(plugin_home, NIGHTLY, "OptiScaler/amd_fidelityfx_upscaler_dx12.dll",
                  pe_dll({".data": b".?AVffxProvider_FSR3@@", ".rsrc": fixed_file_info(3, 1, 5, 0)}))
    steam_library.add_game("730", "Fsr Game")
    run(plugin.patch_game("730", "dxgi.dll", "", NIGHTLY))

    assert run(plugin.get_game_status("730"))["fsr4"] == {"version": "3.1.5.0", "models": []}


def test_an_upscaler_that_cant_be_read_tells_nothing(plugin, plugin_home, steam_library, amd_gpu):
    steam_library.add_game("730", "Fsr Game")  # the library's upscaler is a placeholder, not a DLL
    run(plugin.patch_game("730", "dxgi.dll", "", NIGHTLY))

    assert run(plugin.get_game_status("730"))["fsr4"] is None


def test_a_game_not_patched_has_no_fsr4_to_tell(plugin, plugin_home, steam_library, amd_gpu):
    with_upscaler(plugin_home, NIGHTLY, "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", SDK_2_4)
    steam_library.add_game("730", "Fsr Game")

    assert run(plugin.get_game_status("730"))["fsr4"] is None


def test_off_amd_fsr4_is_not_mentioned(plugin, plugin_home, steam_library, tmp_path):
    add_gpu(tmp_path / "sys", "card0", "0x10de")
    with_upscaler(plugin_home, NIGHTLY, "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", SDK_2_4)
    steam_library.add_game("730", "Fsr Game")
    run(plugin.patch_game("730", "dxgi.dll", "", NIGHTLY))

    assert run(plugin.get_game_status("730"))["fsr4"] is None


def test_the_boot_gpu_decides_on_a_machine_with_two(plugin, plugin_home, steam_library, tmp_path):
    add_gpu(tmp_path / "sys", "card0", "0x1002", boot_vga=False)
    add_gpu(tmp_path / "sys", "card1", "0x10de", boot_vga=True)
    (tmp_path / "sys" / "class" / "drm" / "card1-DP-1").mkdir(parents=True)  # a connector, not a card
    with_upscaler(plugin_home, NIGHTLY, "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", SDK_2_4)
    steam_library.add_game("730", "Fsr Game")
    run(plugin.patch_game("730", "dxgi.dll", "", NIGHTLY))

    assert run(plugin.get_game_status("730"))["fsr4"] is None


def test_a_patch_asks_proton_for_nothing_and_links_no_driver_dll(plugin, plugin_home, steam_library, amd_gpu):
    root = steam_library.add_game("730", "Fsr Game")
    steam_library.set_compat_tools({"730": "GE-Proton11-11"})
    prefix_dll = steam_library.steamapps / "compatdata" / "730" / "pfx" / "drive_c" / "windows" / "system32" / "amdxcffx64.dll"
    write(prefix_dll, b"AMD's FSR 4 driver DLL, fetched by GE-Proton")

    patched = run(plugin.patch_game("730", "dxgi.dll", "", NIGHTLY))

    assert patched["launch_options"] == "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%"
    assert not os.path.lexists(root / "OptiScaler" / "amdxcffx64.dll")


def test_a_game_patched_the_earlier_way_says_so_until_patched_again(plugin, plugin_home, steam_library, amd_gpu):
    root = steam_library.add_game("730", "Fsr Game")
    run(plugin.patch_game("730", "dxgi.dll", "", NIGHTLY))
    # What an earlier version left: AMD's driver DLL linked from the prefix next to OptiScaler, and the variable.
    prefix_dll = steam_library.steamapps / "compatdata" / "730" / "pfx" / "drive_c" / "windows" / "system32" / "amdxcffx64.dll"
    write(prefix_dll, b"AMD's FSR 4 driver DLL, fetched by GE-Proton")
    (root / "OptiScaler" / "amdxcffx64.dll").symlink_to(prefix_dll)
    recorded = json.loads((root / "DECKYSCALER_PATCH").read_text())
    recorded["placed"].append({"path": "OptiScaler/amdxcffx64.dll", "sha256": f"link:{prefix_dll}"})
    recorded["launch_options"] = EARLIER_OPTIONS
    (root / "DECKYSCALER_PATCH").write_text(json.dumps(recorded))

    assert run(plugin.get_game_status("730"))["earlier_fsr4"] is True
    assert run(plugin.patched_games())["games"][0]["earlier_fsr4"] is True

    patched = run(plugin.patch_game("730", "dxgi.dll", EARLIER_OPTIONS, NIGHTLY))  # Steam holds what it wrote

    assert patched["launch_options"] == "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%"
    assert not os.path.lexists(root / "OptiScaler" / "amdxcffx64.dll")
    assert prefix_dll.read_bytes() == b"AMD's FSR 4 driver DLL, fetched by GE-Proton"  # Proton's own file stays
    assert run(plugin.get_game_status("730"))["earlier_fsr4"] is False
    assert run(plugin.patched_games())["games"][0]["earlier_fsr4"] is False


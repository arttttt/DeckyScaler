"""FSR 4 as OptiScaler brings it: AMD's FidelityFX upscaler DLL in OptiScaler's own archive, and the models it holds.

OptiScaler 10's nightlies since 2026-10-28 ship FidelityFX SDK 2.4.0, FSR 4.1.2, with a model for every GPU OptiScaler
runs FSR 4 on; it picks the GPU's itself. Under Proton nothing else is needed: AMD's driver DLL (amdxcffx64.dll), which
some Protons fetch, holds an older FSR 4 with fewer models, and earlier versions of the plugin linked it into games.
"""

from __future__ import annotations

from dataclasses import dataclass

AMD_VENDOR = "0x1002"

FP8 = "fp8"
INT8 = "int8"
INT8_RDNA2 = "int8-rdna2"
INT8_LITE = "int8-lite"
RTTI_SECTION = ".data"
"""The section of AMD's FidelityFX upscaler DLL that names its providers' classes (MSVC's run-time type information)."""
_MODEL_CLASSES = (
    (FP8, b".?AVffxProvider_FSR4@@"),
    (INT8, b".?AVffxProvider_FSR4_Int8@@"),
    (INT8_RDNA2, b".?AVffxProvider_FSR4_Int8_Navi2@@"),
    (INT8_LITE, b".?AVffxProvider_FSR4Lite_Int8@@"),
)
"""Each FSR 4 model and the class of its provider, in the order FFX checks them (OptiScaler's fsr4/FSR4Models.cpp)."""


def models(rtti: bytes) -> tuple[str, ...]:
    """The FSR 4 models an upscaler DLL carries, told by its providers' classes in its RTTI_SECTION, without running it.
    OptiScaler picks the GPU's model among them: INT8 Lite for the Steam Deck and Ryzen APUs, INT8 for RDNA 3 cards,
    INT8 RDNA2 for RDNA 2 cards, FP8 for RDNA 4."""
    return tuple(model for model, name in _MODEL_CLASSES if name in rtti)


@dataclass(frozen=True)
class Carried:
    """The FSR 4 a patched game's OptiScaler carries: its upscaler DLL's version, which is FSR 4's (4.1.2.4555), and the
    models the DLL holds."""

    version: str | None
    models: tuple[str, ...]


def carried(amd_gpu: bool, rtti: bytes | None, version: str | None) -> Carried | None:
    """What to tell of the FSR 4 a patched game's OptiScaler carries, from its upscaler DLL's RTTI_SECTION and version:
    nothing off AMD, where FSR 4 isn't the question, nor without a DLL to read (`rtti` None)."""
    if not amd_gpu or rtti is None:
        return None
    return Carried(version, models(rtti))


def is_amd(vendor: str) -> bool:
    """Whether a PCI vendor id (as sysfs gives it, e.g. "0x1002\\n") is AMD's."""
    return vendor.strip().lower() == AMD_VENDOR

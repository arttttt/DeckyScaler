"""Test harness for the Python backend.

`main.py` imports `decky`, which only exists inside Decky Loader. A stand-in
module is registered before `main` is imported; each test then points its
paths at a private temporary directory.

The fixtures build a fake world on disk: a `~/deckyscaler` with an OptiScaler library
(a 0.9 stable version and a newer 10 nightly one, laid out as their real
archives are), game directories and a Steam library. Version files are small
placeholder blobs — the plugin records and compares them by hash, so size does
not matter.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.server
import json
import logging
import os
import shutil
import struct
import sys
import threading
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_decky = types.ModuleType("decky")
_decky.HOME = ""
_decky.DECKY_PLUGIN_DIR = ""
_decky.DECKY_PLUGIN_RUNTIME_DIR = ""
_decky.DECKY_PLUGIN_SETTINGS_DIR = ""
_decky.logger = logging.getLogger("decky")
sys.modules["decky"] = _decky
# Decky puts the plugin's py_modules on sys.path; the repo root holds main.py.
sys.path[:0] = [str(REPO_ROOT / "py_modules"), str(REPO_ROOT)]

import main  # noqa: E402
from deckyscaler.domain import bundle  # noqa: E402
from deckyscaler.infrastructure import drives, gpu, proton  # noqa: E402


# sha256 → label of every placeholder handed out, so snapshots can name content.
KNOWN_CONTENT: dict[str, str] = {}


def _labelled(label: str, data: bytes) -> bytes:
    KNOWN_CONTENT[hashlib.sha256(data).hexdigest()] = label
    return data


def blob(name: str) -> bytes:
    """Deterministic, unique placeholder content for a bundle file."""
    return _labelled(f"bundle:{name}", f"deckyscaler test blob: {name}\n".encode())


def game_file(name: str) -> bytes:
    """Deterministic content for a file the game itself ships."""
    return _labelled(f"game:{name}", f"file shipped by the game: {name}\n".encode())


def run(coro):
    """Run one of the plugin's async methods to completion."""
    return asyncio.run(coro)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def pe_dll(sections: dict[str, bytes], outside: bytes = b"") -> bytes:
    """A Windows PE file holding `sections` (name → raw bytes) one after another; `outside` sits between the headers
    and the first of them."""
    pe_offset = 0x40
    dos = bytearray(pe_offset)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, pe_offset)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, len(sections), 0, 0, 0, 0, 0)
    offset = pe_offset + len(coff) + 40 * len(sections) + len(outside)
    table = b""
    for name, data in sections.items():
        table += name.encode().ljust(8, b"\0") + struct.pack("<IIII", len(data), 0x1000, len(data), offset) + bytes(16)
        offset += len(data)
    return bytes(dos) + coff + table + outside + b"".join(sections.values())


def fixed_file_info(major: int, minor: int, build: int, revision: int, structure: int = 0x00010000) -> bytes:
    """Resources holding a VS_FIXEDFILEINFO with that file version."""
    return b"\0" * 8 + struct.pack("<IIII", 0xFEEF04BD, structure, (major << 16) | minor, (build << 16) | revision)


def install_tools(directory: Path, scripts: dict[str, str]) -> Path:
    """Executable stand-ins for command-line tools, written into `directory`."""
    for name, body in scripts.items():
        write(directory / name, body.encode()).chmod(0o755)
    return directory


def put_tools_on_path(monkeypatch, directory: Path, scripts: dict[str, str]) -> Path:
    """Stand-in tools that shadow the real ones for the rest of the test."""
    install_tools(directory, scripts)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    return directory


def snapshot(root: Path) -> dict[str, str | None]:
    """Map every file to its sha256 and every directory to None, keyed by relative path."""
    state: dict[str, str | None] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        state[rel] = None if path.is_dir() else sha256(path.read_bytes())
    return state


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A private home directory wired into the fake `decky` module."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(_decky, "HOME", str(home_dir))
    monkeypatch.setattr(_decky, "DECKY_PLUGIN_DIR", str(tmp_path / "plugin"))
    monkeypatch.setattr(_decky, "DECKY_PLUGIN_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(_decky, "DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path / "settings"))
    # The machine running the tests has its own GPU and Proton tools; the fake world has none unless a test adds them.
    monkeypatch.setattr(gpu, "SYSFS", tmp_path / "sys")
    monkeypatch.setattr(proton, "SYSTEM_TOOLS", tmp_path / "system-compatibilitytools.d")
    return home_dir


def add_gpu(sysfs: Path, card: str, vendor: str, boot_vga: bool | None = None) -> None:
    """A GPU under a fake /sys: its DRM card node and PCI vendor (and boot_vga, when the machine says)."""
    device = sysfs / "class" / "drm" / card / "device"
    write(device / "vendor", f"{vendor}\n".encode())
    if boot_vga is not None:
        write(device / "boot_vga", b"1\n" if boot_vga else b"0\n")


@pytest.fixture
def amd_gpu(tmp_path) -> None:
    add_gpu(tmp_path / "sys", "card0", "0x1002")


@pytest.fixture
def plugin(home) -> main.Plugin:
    return main.Plugin()


# The files of library versions, as their real archives lay them out (blob labels name the source).
STABLE_FILES = {
    "OptiScaler.dll": "OptiScaler.dll",
    "OptiScaler.ini": None,
    "amd_fidelityfx_dx12.dll": "amd_fidelityfx_dx12.dll",
    "amd_fidelityfx_upscaler_dx12.dll": "amd_fidelityfx_upscaler_dx12.dll",
    "dlssg_to_fsr3_amd_is_better.dll": "dlssg_to_fsr3_amd_is_better.dll",
    "fakenvapi.dll": "fakenvapi.dll",
    "fakenvapi.ini": "fakenvapi.ini",
    "libxess.dll": "libxess.dll",
    "libxess_dx11.dll": "libxess_dx11.dll",
    "D3D12_Optiscaler/D3D12Core.dll": "D3D12Core.dll",
    "Licenses/XeSS_LICENSE.txt": "XeSS_LICENSE.txt",
    "!!.txt": "readme",
    "setup_linux.sh": "setup_linux.sh",
}
NIGHTLY_FILES = {
    "OptiScaler.dll": "v10 OptiScaler.dll",
    "OptiScaler.ini": None,
    "OptiScaler/amd_fidelityfx_upscaler_dx12.dll": "v10 amd_fidelityfx_upscaler_dx12.dll",
    "OptiScaler/libxess.dll": "v10 libxess.dll",
    "OptiScaler/D3D12_OptiScaler/D3D12Core.dll": "v10 D3D12Core.dll",
    "OptiScaler/Streamlined_fetcher_windows.bat": "fetcher",
    "setup_windows.bat": "setup_windows.bat",
}
# Cut from the real files (tests/fixtures/optiscaler-ini): their comments are what the settings are read from.
STABLE_INI = (
    "[FrameGen]\n; nofg, dlssg, nukems, fsrfg, upscaler, fsrfg30 - Default (auto) is nofg\nFGInput=auto\n\n"
    "; nofg, fsrfg, xefg, nukems - Default (auto) is nofg\nFGOutput=auto\n\n"
    "[FSR]\n; true or false - Default (auto) is false\nFsr4Update=auto\n\n"
    "; true or false - Default (auto) is false\nFsr4ForceEnableInt8=auto\n\n"
    "[Menu]\n; true or false - Default (auto) is true\nUseHQFont=auto\n"
)
NIGHTLY_INI = (
    "[FrameGen]\n; nofg, dlssg, nvngxfg, fsrfg, upscaler, fsrfg30, xefg - Default (auto) is nofg\nFGInput=auto\n\n"
    "[FSR]\n; 0 = No override | 1 = FP8 | 2 = INT8 | 3 = INT8-2 | 4 = INT8 Lite\n; From 0 to 4 - Default (auto) is 0\nFsr4GpuSupport=auto\n\n"
    "; 0 = FP8 | 1 = INT8 | 2 = INT8 RDNA2 | 3 = INT8 Lite\n; Default (auto) is the best one the GPU supports\nFsr4Model=auto\n\n"
    "[Menu]\n; true or false - Default (auto) is true\nUseHQFont=auto\n"
)
STABLE, NIGHTLY = "stable-0.9.4", "nightly-20261023"


def install_version(plugin_home: Path, version_id: str, family: str, files: dict[str, str | None], ini: str) -> Path:
    """A version in ~/deckyscaler/library as the library service leaves it."""
    from deckyscaler.domain import library

    root = plugin_home / "library" / "versions" / version_id
    for rel, label in files.items():
        write(root / "files" / rel, ini.encode() if label is None else blob(label))
    channel, _, rest = version_id.partition("-")
    entry = library.Installed(version_id, channel, rest if channel == "stable" else "10.0.0-pre1",
                              "20260718" if channel == "stable" else rest, family, "https://x", "0" * 64, "2026-10-24")
    write(root / "entry.json", json.dumps(library.entry_json(entry)).encode())
    return root


@pytest.fixture
def plugin_home(home) -> Path:
    """~/deckyscaler with the plugin's core and launch scripts, and a library holding OptiScaler 0.9.4
    and a newer v10 nightly."""
    root = home / "deckyscaler"
    shutil.copytree(
        REPO_ROOT / "py_modules" / bundle.CORE_PACKAGE,
        root / bundle.CORE_PACKAGE,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("patch", "unpatch"):
        write(root / name, blob(name))
    install_version(root, STABLE, "0.9", STABLE_FILES, STABLE_INI)
    install_version(root, NIGHTLY, "10", NIGHTLY_FILES, NIGHTLY_INI)
    return root


def make_game_dir(path: Path, files: dict[str, bytes] | None = None) -> Path:
    """A game directory holding an executable plus any game-shipped files given."""
    write(path / "Game.exe", game_file("Game.exe"))
    for rel, data in (files or {}).items():
        write(path / rel, data)
    return path


@dataclass
class Media:
    """A fake /run/media with the kernel's mount list and udev's devices by UUID behind it: a drive put in is mounted
    at /run/media/deck/<label> from its device, and known by its filesystem's UUID."""

    base: Path
    devices: Path
    mounts: Path
    by_uuid: Path
    drawer: Path
    """Where a drive taken out keeps its files, by its UUID, until it is put in again."""
    mounted: dict[Path, Path] = field(default_factory=dict)

    def put_in(self, label: str, uuid: str, device: str = "mmcblk0p1", filesystem: str = "ext4") -> Path:
        point = self.base / "deck" / label
        if (self.drawer / uuid).exists():
            (self.drawer / uuid).rename(point)
        else:
            point.mkdir()
        node = self.devices / device
        node.touch()
        for link in self.by_uuid.iterdir():
            if link.resolve() == node.resolve():
                link.unlink()  # udev renames the slot's device after the card in it
        (self.by_uuid / uuid).symlink_to(node)
        self.mounted[point.resolve()] = node
        self._list(filesystem)
        return point

    def take_out(self, point: Path) -> None:
        node = self.mounted.pop(point.resolve())
        for link in self.by_uuid.iterdir():
            if link.resolve() == node.resolve():
                point.rename(self.drawer / link.name)
                link.unlink()
        self._list("ext4")

    def mount_at(self, point: Path, device: str) -> None:
        """Something mounted at a place of its own choosing, not by putting a drive in."""
        self.mounted[point.resolve()] = self.devices / device
        self._list("ext4")

    def _list(self, filesystem: str) -> None:
        lines = [
            f"{n} 1 179:{n} / {str(point).replace(' ', chr(92) + '040')} rw,relatime shared:{n} - {filesystem} {node} rw"
            for n, (point, node) in enumerate(self.mounted.items(), start=30)
        ]
        self.mounts.write_text("\n".join(["22 1 0:21 / / rw - ext4 /dev/nvme0n1p8 rw", *lines]) + "\n")


@pytest.fixture
def media(tmp_path, monkeypatch) -> Media:
    fake = Media(
        tmp_path / "run" / "media", tmp_path / "dev", tmp_path / "mountinfo", tmp_path / "dev" / "disk" / "by-uuid",
        tmp_path / "drawer",
    )
    (fake.base / "deck").mkdir(parents=True)
    fake.by_uuid.mkdir(parents=True)
    fake.drawer.mkdir()
    fake.mounts.write_text("")
    monkeypatch.setattr(drives, "REMOVABLE_MEDIA", (fake.base,))
    monkeypatch.setattr(drives, "MOUNTS", fake.mounts)
    monkeypatch.setattr(drives, "BY_UUID", fake.by_uuid)
    return fake


@pytest.fixture
def game_dir(tmp_path) -> Path:
    """A clean game directory with nothing but its executable."""
    return make_game_dir(tmp_path / "games" / "Clean Game")


@dataclass
class SteamLibrary:
    """A Steam install under the fake home; `add_game` registers an installed title."""

    steamapps: Path
    games: dict[str, Path] = field(default_factory=dict)

    def add_game(self, appid: str, name: str, files: dict[str, bytes] | None = None) -> Path:
        install_dir = name.replace(" ", "")
        manifest = (
            '"AppState"\n{\n'
            f'\t"appid"\t\t"{appid}"\n'
            f'\t"name"\t\t"{name}"\n'
            f'\t"installdir"\t\t"{install_dir}"\n'
            "}\n"
        )
        write(self.steamapps / f"appmanifest_{appid}.acf", manifest.encode())
        game_root = make_game_dir(self.steamapps / "common" / install_dir, files)
        self.games[appid] = game_root
        return game_root

    @property
    def root(self) -> Path:
        return self.steamapps.parent

    def set_compat_tools(self, mapping: dict[str, str]) -> None:
        """Steam's CompatToolMapping in config.vdf: appid ("0" for every game) → tool's internal name."""
        entries = "".join(
            f'\t\t\t\t\t"{appid}"\n\t\t\t\t\t{{\n\t\t\t\t\t\t"name"\t\t"{name}"\n'
            f'\t\t\t\t\t\t"config"\t\t""\n\t\t\t\t\t\t"priority"\t\t"250"\n\t\t\t\t\t}}\n'
            for appid, name in mapping.items()
        )
        config = (
            '"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
            f'\t\t\t\t"CompatToolMapping"\n\t\t\t\t{{\n{entries}\t\t\t\t}}\n'
            "\t\t\t}\n\t\t}\n\t}\n}\n"
        )
        write(self.root / "config" / "config.vdf", config.encode())


@pytest.fixture
def steam_library(home) -> SteamLibrary:
    steamapps = home / ".local" / "share" / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    return SteamLibrary(steamapps=steamapps)


# ── 7-Zip ────────────────────────────────────────────────────────────────────

FAKE_7Z = f"""#!{sys.executable}
import sys, zipfile
args = sys.argv[1:]
assert args[:2] == ["x", "-y"], args
out_dir = args[2][len("-o"):]
archive, members = args[3], args[4:]
with zipfile.ZipFile(archive) as zf:
    zf.extractall(out_dir, members or None)
"""
"""A stand-in for tools/7zzs: it unpacks zips with 7-Zip's command line."""


# ── GitHub ───────────────────────────────────────────────────────────────────


class FakeDownload:
    """Stands in for github_releases.download: records each URL, writes `content` (or raises `error`) and reports
    the download halfway and done."""

    def __init__(self, content: bytes = b"", error: Exception | None = None):
        self.content, self.error, self.urls = content, error, []

    def __call__(self, url: str, destination: Path, on_progress) -> None:
        self.urls.append(url)
        if self.error:
            raise self.error
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.content)
        on_progress(len(self.content) // 2, len(self.content))
        on_progress(len(self.content), len(self.content))



@pytest.fixture
def github_api(monkeypatch):
    """A local stand-in for api.github.com: every GET answers `.status` and `.body` (a JSON list by default)."""
    from deckyscaler.infrastructure import github_releases

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            server.requests.append(self.path)
            self.send_response(server.status)
            self.end_headers()
            self.wfile.write(server.body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.status, server.body, server.requests = 200, b"[]", []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(github_releases, "API_ROOT", f"http://127.0.0.1:{server.server_port}")
    yield server
    server.shutdown()
    server.server_close()

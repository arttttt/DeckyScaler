"""Unpacking archives: OptiScaler's .7z with the 7-Zip build the plugin ships (tools/7zzs), Proton's tarballs
and the user's libraries' zips with Python's own tarfile and zipfile."""

from __future__ import annotations

import os
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

SEVEN_ZIP = Path("tools") / "7zzs"
"""The static 7-Zip binary inside the plugin directory (CI adds it to every package)."""


def extract_7z(seven_zip: Path, archive_path: Path, output_dir: Path, members: list[str] | None = None) -> None:
    """Extract an archive (or only `members` of it) into `output_dir`; raises RuntimeError on failure."""
    if not seven_zip.is_file():
        raise RuntimeError(f"7-Zip is missing from this plugin build ({seven_zip}).")
    # Decky unpacks the plugin's zip without keeping file modes, so the binary may lose +x.
    mode = seven_zip.stat().st_mode
    if not mode & stat.S_IXUSR:
        seven_zip.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [str(seven_zip), "x", "-y", f"-o{output_dir}", str(archive_path), *(members or [])]
    # The build is static; clearing Decky's library path keeps it from picking up Decky's libraries anyway.
    env = {**os.environ, "LD_LIBRARY_PATH": ""}
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"Failed to extract {archive_path.name}")


def extract_tar(archive_path: Path, output_dir: Path) -> None:
    """Unpack a .tar.gz or .tar.xz into `output_dir`, keeping its relative symlinks and executable bits; raises
    RuntimeError on failure.

    tarfile's "data" filter refuses what has no place in a build: absolute paths, anything that would land or
    link outside `output_dir`, device files. Never 7-Zip for these: it turns symlinks that point up a directory
    into empty files, and a Proton build's default prefix is made of about 1850 of them.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:*") as tar:
            tar.extractall(output_dir, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise RuntimeError(f"Failed to unpack {archive_path.name}: {exc}") from exc


def zip_members(archive_path: Path) -> frozenset[str]:
    """The files a zip holds, as paths with '/'; raises RuntimeError when it isn't a zip it can read."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            return frozenset(info.filename for info in archive.infolist() if not info.is_dir())
    except (zipfile.BadZipFile, OSError) as exc:
        raise RuntimeError(f"Failed to read {archive_path.name}: {exc}") from exc


def extract_zip(archive_path: Path, members: tuple[str, ...], output_dir: Path, max_bytes: int) -> None:
    """Unpack the named members of a zip into `output_dir`, refusing to when they would unpack to more than
    `max_bytes`; raises RuntimeError on failure. zipfile keeps every member inside `output_dir`, whatever its name."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = {info.filename: info for info in archive.infolist()}
            if sum(infos[name].file_size for name in members) > max_bytes:
                raise RuntimeError(f"{archive_path.name} unpacks to more than {max_bytes // 1_000_000} MB.")
            for name in members:
                archive.extract(infos[name], output_dir)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise RuntimeError(f"Failed to unpack {archive_path.name}: {exc}") from exc

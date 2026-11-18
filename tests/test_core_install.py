"""The plugin's core and launch scripts in ~/deckyscaler (integration)."""

import shutil

from conftest import REPO_ROOT, run, write
from deckyscaler.domain import bundle
from deckyscaler.infrastructure import core_install


def test_refreshing_replaces_the_core_and_scripts_and_leaves_the_rest(tmp_path):
    plugin_home = tmp_path / "deckyscaler"
    write(plugin_home / "deckyscaler" / "stale_module.py", b"old core")
    write(plugin_home / "patch", b"old script")
    write(plugin_home / "library" / "versions" / "x" / "entry.json", b"{}")

    core_install.refresh_core(plugin_home, REPO_ROOT / "defaults" / "assets")

    assert not (plugin_home / "deckyscaler" / "stale_module.py").exists()
    assert (plugin_home / "deckyscaler" / "__main__.py").read_bytes() == (core_install.CORE_SOURCE / "__main__.py").read_bytes()
    for installed, source in bundle.LAUNCHER_SCRIPTS.items():
        assert (plugin_home / installed).read_bytes() == (REPO_ROOT / "defaults" / "assets" / source).read_bytes()
        assert (plugin_home / installed).stat().st_mode & 0o111 == 0o111
    assert (plugin_home / "library" / "versions" / "x" / "entry.json").read_bytes() == b"{}"
    assert sorted(p.name for p in plugin_home.iterdir() if p.name.startswith(".")) == []


def test_the_plugin_brings_its_core_into_home_each_time_it_loads(plugin, home, tmp_path):
    shutil.copytree(REPO_ROOT / "defaults" / "assets", tmp_path / "plugin" / "assets")
    write(home / "deckyscaler" / "deckyscaler" / "stale_module.py", b"the core of the plugin before an update")

    run(plugin._main())

    assert not (home / "deckyscaler" / "deckyscaler" / "stale_module.py").exists()
    assert (home / "deckyscaler" / "deckyscaler" / "__main__.py").is_file()
    assert (home / "deckyscaler" / "patch").stat().st_mode & 0o100


def test_a_failed_refresh_doesnt_stop_the_plugin_loading(plugin, home, monkeypatch):
    def refresh(*_args):
        raise OSError("No space left on device")

    monkeypatch.setattr(core_install, "refresh_core", refresh)

    run(plugin._main())  # logged, not raised

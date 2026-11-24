"""One install at a time into a store with a staging directory (integration, on a real filesystem)."""

from __future__ import annotations

import threading

from conftest import write
from deckyscaler.infrastructure.entry_store import EntryStore
from deckyscaler.infrastructure.compat_tools_store import CompatToolsStore


def test_a_second_install_into_a_store_is_turned_away_while_the_first_assembles(tmp_path):
    store = EntryStore(tmp_path / "library", "versions", "entry.json")

    with store.assembling() as first:
        write(store.partial_dir / "v1" / "files" / "OptiScaler.dll", b"half")
        with store.assembling() as second:
            assert (first, second) == (True, False)
        assert (store.partial_dir / "v1").exists()  # the one turned away cleared nothing
        store.clear_when_idle()
        assert (store.partial_dir / "v1").exists()  # nor does the load's clear while an install goes on
    assert not store.partial_dir.exists()  # the install's own staging goes with it
    with store.assembling() as again:
        assert again


def test_the_lock_holds_between_threads_as_the_plugins_rpcs_run(tmp_path):
    store = EntryStore(tmp_path / "library", "versions", "entry.json")
    holding, release, seen = threading.Event(), threading.Event(), []

    def first() -> None:
        with store.assembling() as free:
            seen.append(free)
            holding.set()
            release.wait(5)

    thread = threading.Thread(target=first)
    thread.start()
    holding.wait(5)
    with store.assembling() as free:
        seen.append(free)
    release.set()
    thread.join()

    assert seen == [True, False]


def test_compatibilitytools_d_gets_no_staging_directory_for_a_clear_with_nothing_to_clear(tmp_path):
    tools = tmp_path / "compatibilitytools.d"
    tools.mkdir()
    store = CompatToolsStore(tools)

    store.clear_when_idle()

    assert list(tools.iterdir()) == []  # Steam would need a restart for a new entry

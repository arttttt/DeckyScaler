"""One install at a time into a store that assembles what it installs in a staging directory of its own: a second one
would clear the first's staging under it. The lock is taken on a directory of the store's that stays, so nothing is
added for it: the plugin's threads (each RPC runs in its own) each open it apart and see each other's hold, and a holder
that dies lets it go."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _held(directory: Path) -> Iterator[bool]:
    """Hold a lock on a directory without waiting: whether it was free."""
    directory.mkdir(parents=True, exist_ok=True)
    handle = os.open(directory, os.O_RDONLY)
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(handle)


class Staging:
    """What a store with a staging directory shares: `lock_dir`, a directory of its own that stays, and
    `clear_partial`, which empties the staging."""

    lock_dir: Path

    def clear_partial(self) -> None:
        raise NotImplementedError

    @contextmanager
    def assembling(self) -> Iterator[bool]:
        """One install into the store: whether it may go on (False while another assembles one), its staging cleared
        before and after it."""
        with _held(self.lock_dir) as free:
            if free:
                self.clear_partial()
            try:
                yield free
            finally:
                if free:
                    self.clear_partial()

    def clear_when_idle(self) -> None:
        """Clear what an install the plugin's stop cut short left, unless an install is assembling one now. A store
        whose directory isn't there has nothing to clear, and isn't made for it."""
        if not self.lock_dir.is_dir():
            return
        with _held(self.lock_dir) as free:
            if free:
                self.clear_partial()

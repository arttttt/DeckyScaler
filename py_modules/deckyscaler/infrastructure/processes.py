"""Running processes: their command lines, and when they started."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from datetime import datetime

log = logging.getLogger(__name__)


def command_lines() -> list[str]:
    """One command line per running process; empty when `ps` cannot be run."""
    try:
        result = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True, check=False)
    except OSError as exc:
        log.error(f"[DeckyScaler] running exe scan failed: {exc}")
        return []
    return result.stdout.splitlines()


def wait_while_running(fragment: str, timeout: float, poll: float = 0.5) -> bool:
    """Wait, at most `timeout` seconds, while a running process's command line holds `fragment`: whether none does
    by then."""
    deadline = time.monotonic() + timeout
    while any(fragment in line for line in command_lines()):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll)
    return True


_STARTED = re.compile(r"^\s*(\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.*)$")


def parse_started(line: str) -> tuple[float, str] | None:
    """One line of `ps -eo lstart=,args=` in the C locale ("Fri Nov  7 09:05:01 2026 /usr/bin/x -y"): when the
    process started, as a timestamp of this machine's local time, and its command line."""
    match = _STARTED.match(line)
    if not match:
        return None
    try:
        started = datetime.strptime(" ".join(match.group(1).split()), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return started.timestamp(), match.group(2)


def started_processes() -> list[tuple[float, str]]:
    """When each running process started, and its command line; empty when `ps` cannot be run."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "lstart=,args="],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},  # lstart's date in one known format
        )
    except OSError as exc:
        log.error(f"[DeckyScaler] listing processes failed: {exc}")
        return []
    return [parsed for line in result.stdout.splitlines() if (parsed := parse_started(line))]

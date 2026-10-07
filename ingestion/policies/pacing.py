from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import random
import threading
import time

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_LAST_RUN: dict[str, float] = {}


def pacing_delay(source: str, minimum_seconds: int, maximum_seconds: int, *, now: float | None = None) -> float:
    now = time.monotonic() if now is None else now
    with _LOCKS_GUARD:
        last = _LAST_RUN.get(source)
    if last is None:
        return 0.0
    target = random.uniform(minimum_seconds, maximum_seconds)
    return max(0.0, target - (now - last))


def mark_source_run(source: str, *, now: float | None = None) -> None:
    with _LOCKS_GUARD:
        _LAST_RUN[source] = time.monotonic() if now is None else now


@contextmanager
def source_lock(source: str, root: str | Path):
    """Serialize acquisition per source in-process and, on Linux, across containers sharing the volume."""
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(source, threading.Lock())
    with lock:
        lock_dir = Path(root) / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = (lock_dir / f"{source}.lock").open("a+")
        try:
            try:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            yield
        finally:
            try:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            lock_file.close()

"""Lightweight rotation for append-only JSONL logs."""

from __future__ import annotations

import os
from pathlib import Path


def rotate_if_needed(
    log_path: Path,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Rotate ``log_path`` when it exceeds ``max_bytes``.

    Keeps ``backup_count`` numbered backups (``log_path.1`` through
    ``log_path.{backup_count}``).  Oldest backups are removed.
    """
    path = Path(log_path).expanduser()
    if not path.exists():
        return

    if path.stat().st_size <= max_bytes:
        return

    # Create the log directory if necessary (already true if the log exists).
    path.parent.mkdir(parents=True, exist_ok=True)

    # Remove the oldest backup if it exists.
    oldest = path.parent / f"{path.name}.{backup_count}"
    if oldest.exists():
        try:
            oldest.unlink()
        except OSError:
            pass

    # Shift existing backups up by one.
    for i in range(backup_count - 1, 0, -1):
        src = path.parent / f"{path.name}.{i}"
        dst = path.parent / f"{path.name}.{i + 1}"
        if src.exists():
            try:
                src.rename(dst)
            except OSError:
                pass

    # Rotate the active log to .1
    try:
        path.rename(path.parent / f"{path.name}.1")
    except OSError:
        pass


def cleanup_old_logs(
    log_dir: Path,
    pattern: str = "*.ndjson",
    max_age_days: int = 7,
) -> int:
    """Remove files in ``log_dir`` matching ``pattern`` older than ``max_age_days``.

    Returns the number of removed files.
    """
    import time

    removed = 0
    cutoff = time.time() - (max_age_days * 24 * 60 * 60)
    for f in Path(log_dir).expanduser().glob(pattern):
        try:
            if f.is_file() and os.path.getmtime(f) < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed

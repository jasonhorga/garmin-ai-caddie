"""Private-volume retention maintenance (C10).

The implementation is intentionally introduced behind a small public entry point so the
service can schedule it without coupling startup to filesystem details.
"""
from __future__ import annotations

from pathlib import Path


def cleanup_private_volume(*, root: Path | None = None) -> None:
    """Clean old private artifacts.  The initial compatibility stub preserves old behavior."""
    return None


def start_retention_cleanup(*, root: Path | None = None) -> None:
    """Schedule one cleanup pass without delaying service startup."""
    return None

"""Shared bootstrap helper for root dispatch scripts.

Ensures devin_orchestrator/ (sibling source) or the installed devin_orchestrator
package is on sys.path before any local imports.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_devin_orchestrator_on_path() -> None:
    """Insert the devin_orchestrator directory or installed package into sys.path."""
    script_dir = Path(__file__).parent
    devin_orchestrator_dir = script_dir / "devin_orchestrator"
    if devin_orchestrator_dir.is_dir():
        sys.path.insert(0, str(devin_orchestrator_dir))
        return

    # Fall back to the installed package (e.g. pip install devin-orchestrator).
    try:
        import devin_orchestrator as _devin_orchestrator  # noqa: F401

        sys.path.insert(0, str(Path(_devin_orchestrator.__file__).parent))
    except ModuleNotFoundError as _exc:  # pragma: no cover - build-time guard
        raise FileNotFoundError(
            f"devin_orchestrator directory not found at {devin_orchestrator_dir} "
            "and devin_orchestrator package is not installed. "
            "Run install.py or pip install -e ."
        ) from _exc

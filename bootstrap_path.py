"""Shared bootstrap helper for root dispatch scripts.

Ensures workflow-engine/ (sibling source) or the installed devin_orchestrator
package is on sys.path before any local imports.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_workflow_engine_on_path() -> None:
    """Insert the workflow-engine directory or installed package into sys.path."""
    script_dir = Path(__file__).parent
    workflow_engine_dir = script_dir / "workflow-engine"
    if workflow_engine_dir.is_dir():
        sys.path.insert(0, str(workflow_engine_dir))
        return

    # Fall back to the installed package (e.g. pip install devin-orchestrator).
    try:
        import devin_orchestrator as _devin_orchestrator  # noqa: F401

        sys.path.insert(0, str(Path(_devin_orchestrator.__file__).parent))
    except ModuleNotFoundError as _exc:  # pragma: no cover - build-time guard
        raise FileNotFoundError(
            f"workflow-engine directory not found at {workflow_engine_dir} "
            "and devin_orchestrator package is not installed. "
            "Run install.py or pip install -e ."
        ) from _exc

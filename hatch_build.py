"""Hatch build hook that creates a temporary devin_orchestrator -> workflow-engine symlink.

The package source lives in workflow-engine/ (a hyphenated directory name). Hatchling
can only build packages from valid Python package names, so the hook temporarily
symlinks devin_orchestrator to workflow-engine during the build. The link is removed
after the build finishes so the source tree stays clean.
"""

from __future__ import annotations

import os
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        """Create a devin_orchestrator symlink if one does not already exist."""
        root = Path(self.root)
        source = root / "workflow-engine"
        link = root / "devin_orchestrator"

        if not source.is_dir():
            raise FileNotFoundError(f"Package source directory not found: {source}")

        # If a real directory or file named devin_orchestrator exists, leave it alone.
        if link.exists() or link.is_symlink():
            return

        os.symlink("workflow-engine", link, target_is_directory=True)

    def finalize(self, version: str, build_data: dict, artifact_path: str) -> None:
        """Remove the temporary devin_orchestrator symlink created by initialize."""
        link = Path(self.root) / "devin_orchestrator"
        if link.is_symlink():
            link.unlink()

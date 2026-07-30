#!/usr/bin/env python3
"""
Artifact Validator

Validates stage artifact paths and performs structural validation of stage
outputs. This keeps filesystem and validation concerns separate from stage
execution orchestration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
    sanitize_filename,
)

if TYPE_CHECKING:
    from pathlib import Path

    from devin_orchestrator.orchestration_engine import OrchestrationEngine

logger = logging.getLogger(__name__)


class ArtifactValidator:
    """Validate artifact paths and stage output artifacts."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def validate_artifact_path(self, artifact_name: str, session_dir: Path) -> Path:
        """
        Validate and resolve a stage artifact path so it is contained within
        the session directory.

        The artifact name is sanitized via ``sanitize_filename`` to remove any
        path separators or traversal segments, then joined onto the session
        directory and validated with ``validate_path_safe``. This ensures that
        neither manifest-controlled artifact names nor reviewer-provided names
        can escape the session directory when reading or writing artifacts.

        Args:
            artifact_name: Relative artifact name (e.g. "design.md").
            session_dir: Session directory that must contain the artifact.

        Returns:
            The validated, absolute artifact path inside ``session_dir``.

        Raises:
            InvalidInputError: If the artifact name is invalid.
            PathTraversalError: If the artifact resolves outside the session.
        """
        safe_name = sanitize_filename(artifact_name, max_length=255)
        candidate = session_dir / safe_name
        return self._engine.validate_path_safe(
            session_dir, candidate, allow_absolute=True
        )

    def validate_stage_artifacts(
        self,
        stage_name: str,
        session_dir: Path,
        output_artifacts: list[str],
    ) -> tuple[dict[str, Any], list[Path]]:
        """
        Validate stage output artifacts structurally.

        Returns (validation_result, artifact_paths).
        """
        artifact_paths: list[Path] = []
        for artifact in output_artifacts:
            try:
                artifact_paths.append(
                    self.validate_artifact_path(artifact, session_dir)
                )
            except (InvalidInputError, PathTraversalError) as e:
                logger.error(f"Invalid artifact path for stage {stage_name}: {e}")
                return (
                    {
                        "valid": False,
                        "errors": [f"Invalid artifact path {artifact!r}: {str(e)}"],
                        "artifact_results": {},
                    },
                    [],
                )
        try:
            validation_result = self._engine.validate_structural(
                artifact_paths, required_artifacts=output_artifacts
            )
            logger.info(
                f"Validation completed for stage {stage_name}: "
                f"valid={validation_result['valid']}"
            )
            return validation_result, artifact_paths
        except FileNotFoundError as e:
            logger.error(
                f"Artifact not found during validation for stage {stage_name}: {e}"
            )
            return (
                {
                    "valid": False,
                    "errors": [f"Artifact not found: {str(e)}"],
                    "artifact_results": {},
                },
                artifact_paths,
            )
        except PermissionError as e:
            logger.error(
                f"Permission error during validation for stage {stage_name}: {e}"
            )
            return (
                {
                    "valid": False,
                    "errors": [f"Permission error during validation: {str(e)}"],
                    "artifact_results": {},
                },
                artifact_paths,
            )
        except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
            logger.error(f"Error during validation for stage {stage_name}: {e}")
            return (
                {
                    "valid": False,
                    "errors": [f"Validation error: {str(e)}"],
                    "artifact_results": {},
                },
                artifact_paths,
            )

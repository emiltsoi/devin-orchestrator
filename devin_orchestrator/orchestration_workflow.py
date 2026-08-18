#!/usr/bin/env python3
# mypy: disable-error-code="attr-defined"
"""Workflow execution and continuation logic for the OrchestrationEngine."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from devin_orchestrator.deterministic_tools import (
    WorkflowManifestError,
    session_init,
)
from devin_orchestrator.models import Manifest
from devin_orchestrator.otel_tracing import trace_span
from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
    parse_config_overrides,
    validate_session_id,
)
from devin_orchestrator.session_manager import resolve_session

logger = logging.getLogger(__name__)


class OrchestrationWorkflowMixin:
    """Mixin for loading manifests and executing/continuing workflows."""

    def execute_workflow(
        self,
        manifest_path: Path,
        session_id: str,
        request_content: str,
        skip_brainstorming: bool | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a complete workflow from manifest

        Args:
            manifest_path: Path to workflow manifest
            session_id: Unique session identifier
            request_content: Initial request content
            skip_brainstorming: Override manifest skip_brainstorming setting
            config_overrides: Optional configuration overrides for skills

        Returns:
            Dictionary with execution results
        """
        # Validate inputs and load manifest
        (
            validated_session_id,
            validated_manifest_path,
            manifest,
            error,
        ) = self._validate_and_load_manifest(session_id, manifest_path)
        if error is not None:
            return error
        assert validated_session_id is not None
        assert validated_manifest_path is not None
        assert manifest is not None
        session_id = validated_session_id
        manifest_path = validated_manifest_path
        try:
            config_overrides = parse_config_overrides(config_overrides)
        except InvalidInputError as e:
            logger.error(f"Invalid config_overrides: {e}")
            return {
                "session_id": session_id,
                "manifest": manifest.name,
                "stages": [],
                "final_status": "failed",
                "error": f"Invalid config_overrides: {e}",
            }

        # Initialize session
        session_dir, error = self._init_workflow_session(
            session_id, request_content, manifest
        )
        if error is not None:
            return error
        assert session_dir is not None

        # Persist manifest name in session.json so a later continue_workflow
        # call can locate the manifest without requiring the caller to resupply it.
        self._update_session_manifest(session_dir, manifest.name)

        # Durable state store for idempotency and crash recovery
        self._state_store.init(session_id, session_dir)
        if self._state_store.is_final():
            return self._state_store.as_dict(manifest.name)

        # Override skip_brainstorming if provided
        if skip_brainstorming is not None:
            manifest.skip_brainstorming = skip_brainstorming

        # Start metrics tracking for this workflow
        with trace_span(
            "execute_workflow",
            {"session_id": session_id, "manifest_name": manifest.name},
        ):
            self.metrics.start_workflow(session_id, manifest.name)

            # Execute stages
            self._state_store.set_status("in_progress", "Starting workflow execution")
            results = {
                "session_id": session_id,
                "manifest": manifest.name,
                "stages": [],
                "final_status": "unknown",
            }
            self._run_workflow_stages(
                manifest,
                session_dir,
                session_id,
                config_overrides,
                results,
                resume=False,
            )

            if results["final_status"] == "unknown":
                results["final_status"] = "completed"
            assert isinstance(results["final_status"], str)
            self._state_store.set_status(results["final_status"])

            # Finalize metrics, export, and monitoring
            self._finalize_workflow(session_id, session_dir, results)

            return results

    def continue_workflow(
        self,
        session_id: str,
        gate_verdict: str | None = None,
        gate_notes: str | None = None,
        gate_id: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Resume a workflow that paused at a gate.

        If gate_verdict is provided, it is written to the appropriate gate
        decision file before the workflow resumes. The engine then re-runs
        the workflow manifest, skipping stages that are already completed
        and applying any decisions present in the gate decision files.

        Args:
            session_id: Existing session identifier
            gate_verdict: Optional verdict to write (approve|request_changes|block)
            gate_notes: Optional notes for the gate decision
            gate_id: Optional explicit gate id; if omitted, the first waiting
                     gate found in session.json is used
            config_overrides: Optional configuration overrides for skills

        Returns:
            Dictionary with execution results
        """
        try:
            session_dir = resolve_session(self.work_dir, session_id)
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            logger.error(f"Failed to resolve session {session_id}: {e}")
            return {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"Failed to resolve session: {str(e)}",
            }

        self._state_store.init(session_id, session_dir)

        session_file = session_dir / "session.json"
        try:
            session_data = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read session.json for {session_id}: {e}")
            return {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"Failed to read session: {str(e)}",
            }

        manifest_name = session_data.get("manifest")
        if not manifest_name:
            return {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": "Session manifest not recorded; cannot continue workflow",
            }

        if self._state_store.is_final():
            return self._state_store.as_dict(manifest_name)

        workflows_dir = self.config.get("workflows_dir")
        if workflows_dir:
            workflows_dir = Path(workflows_dir)
        else:
            workflows_dir = self.work_dir.parent / "workflows"
        manifest_path = self.validate_path_safe(
            workflows_dir,
            workflows_dir / f"{manifest_name}.manifest.yaml",
            allow_absolute=True,
        )

        (
            validated_session_id,
            validated_manifest_path,
            manifest,
            error,
        ) = self._validate_and_load_manifest(session_id, manifest_path)
        if error is not None:
            return error
        assert validated_session_id is not None
        assert validated_manifest_path is not None
        assert manifest is not None
        session_id = validated_session_id
        manifest_path = validated_manifest_path
        try:
            config_overrides = parse_config_overrides(config_overrides)
        except InvalidInputError as e:
            logger.error(f"Invalid config_overrides: {e}")
            return {
                "session_id": session_id,
                "manifest": manifest_name,
                "stages": [],
                "final_status": "failed",
                "error": f"Invalid config_overrides: {e}",
            }

        # Write the gate decision if provided
        if gate_verdict is not None:
            waiting_gate_id = gate_id or self._find_waiting_gate_id(session_data)
            if waiting_gate_id:
                decision_file = self._validate_artifact_path(
                    f"gate-{waiting_gate_id}-decision.md", session_dir
                )
                try:
                    decision_file.write_text(
                        f"verdict: {gate_verdict}\nnotes: {gate_notes or ''}\n",
                        encoding="utf-8",
                    )
                    logger.info(
                        f"Wrote gate decision for {waiting_gate_id}: {gate_verdict}"
                    )
                except (OSError, PermissionError) as e:
                    logger.error(f"Failed to write gate decision: {e}")
                    return {
                        "session_id": session_id,
                        "manifest": manifest_name,
                        "stages": [],
                        "final_status": "failed",
                        "error": f"Failed to write gate decision: {str(e)}",
                    }

        # Start/resume metrics tracking
        with trace_span(
            "continue_workflow",
            {
                "session_id": session_id,
                "manifest_name": manifest.name,
                "gate_id": gate_id or "",
            },
        ):
            self.metrics.start_workflow(session_id, manifest.name)

            self._state_store.set_status("in_progress", "Resuming workflow")
            results = {
                "session_id": session_id,
                "manifest": manifest.name,
                "stages": [],
                "final_status": "unknown",
            }
            self._run_workflow_stages(
                manifest,
                session_dir,
                session_id,
                config_overrides,
                results,
                resume=True,
            )

            if results["final_status"] == "unknown":
                results["final_status"] = "completed"
            assert isinstance(results["final_status"], str)
            self._state_store.set_status(results["final_status"])

            self._finalize_workflow(session_id, session_dir, results)
            return results

    def _update_session_manifest(self, session_dir: Path, manifest_name: str) -> None:
        """Write the manifest name into session.json for later continuation."""
        session_file = session_dir / "session.json"
        try:
            session_data = json.loads(session_file.read_text(encoding="utf-8"))
            session_data["manifest"] = manifest_name
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to record manifest in session.json: {e}")

    def _find_waiting_gate_id(self, session_data: dict[str, Any]) -> str | None:
        """Find the most recent gate that is still waiting for input."""
        for entry in reversed(session_data.get("stages", [])):
            stage_name = entry.get("stage", "")
            if stage_name.startswith("gate_") and entry.get("status") == "waiting":
                return stage_name.replace("gate_", "", 1)
        return None

    def _validate_and_load_manifest(
        self, session_id: str, manifest_path: Path
    ) -> tuple[str | None, Path | None, Manifest | None, dict[str, Any] | None]:
        """
        Validate and sanitize inputs, then load the workflow manifest.

        Returns (session_id, manifest_path, manifest, error_dict) where
        error_dict is None on success.
        """
        try:
            try:
                session_id = validate_session_id(session_id)
                # Manifests live in a sibling directory to the session work dir
                # (e.g. workflows/), so validate against the work_dir parent to
                # allow both work/ and workflows/. Resolve the base defensively
                # via os.path.realpath so an absolute work_dir containing
                # traversal segments (e.g. "/x/../y/work") cannot trick the
                # containment check into allowing arbitrary manifest paths.
                base_path = Path(os.path.realpath(str(self.work_dir.parent)))
                manifest_path = self.validate_path_safe(
                    base_path, manifest_path, allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                logger.error(f"Input validation failed: {e}")
                return (
                    None,
                    None,
                    None,
                    {
                        "session_id": session_id,
                        "manifest": "unknown",
                        "stages": [],
                        "final_status": "failed",
                        "error": f"Input validation failed: {str(e)}",
                        "error_type": "InvalidInputError",
                    },
                )

            # Load manifest
            raw_manifest = self.load_manifest(manifest_path)
            # Validate required structure so a malformed manifest (missing
            # name/stages or per-stage skill/name) raises WorkflowManifestError
            # instead of an uncaught KeyError downstream.
            self._validate_manifest_structure(raw_manifest, manifest_path)
            manifest = Manifest.model_validate(raw_manifest)
            logger.info(f"Loaded manifest from {manifest_path}: {manifest.name}")
            return session_id, manifest_path, manifest, None
        except FileNotFoundError as e:
            logger.error(f"Manifest file not found: {manifest_path} - {e}")
            return (
                None,
                None,
                None,
                {
                    "session_id": session_id,
                    "manifest": "unknown",
                    "stages": [],
                    "final_status": "failed",
                    "error": f"Manifest file not found: {manifest_path}",
                    "error_type": "FileNotFoundError",
                },
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in manifest file {manifest_path}: {e}")
            return (
                None,
                None,
                None,
                {
                    "session_id": session_id,
                    "manifest": "unknown",
                    "stages": [],
                    "final_status": "failed",
                    "error": f"Invalid JSON in manifest file: {e}",
                    "error_type": "JSONDecodeError",
                },
            )
        except WorkflowManifestError as e:
            logger.error(f"Invalid YAML in manifest file {manifest_path}: {e}")
            return (
                None,
                None,
                None,
                {
                    "session_id": session_id,
                    "manifest": "unknown",
                    "stages": [],
                    "final_status": "failed",
                    "error": f"Invalid YAML in manifest file: {e}",
                    "error_type": "WorkflowManifestError",
                },
            )
        except (OSError, RuntimeError) as e:
            logger.error(f"System error loading manifest {manifest_path}: {e}")
            return (
                None,
                None,
                None,
                {
                    "session_id": session_id,
                    "manifest": "unknown",
                    "stages": [],
                    "final_status": "failed",
                    "error": f"System error loading manifest: {str(e)}",
                    "error_type": type(e).__name__,
                },
            )

    def _validate_manifest_structure(self, manifest: Any, manifest_path: Path) -> None:
        """Validate that a parsed manifest has the required structure.

        Raises ``WorkflowManifestError`` if the manifest is not a mapping, is
        missing the required ``name`` or ``stages`` keys, or any stage is
        missing its ``name`` or ``skill`` key. This keeps downstream manifest
        access (which uses direct subscripting) from raising uncaught
        ``KeyError`` / ``TypeError`` exceptions.
        """
        if not isinstance(manifest, dict):
            raise WorkflowManifestError(
                f"Manifest {manifest_path} must be a mapping, got "
                f"{type(manifest).__name__}"
            )
        missing = [k for k in ("name", "stages") if k not in manifest]
        if missing:
            raise WorkflowManifestError(
                f"Manifest {manifest_path} missing required key(s): {missing}"
            )
        stages = manifest["stages"]
        if not isinstance(stages, list):
            raise WorkflowManifestError(
                f"Manifest {manifest_path} 'stages' must be a list, got "
                f"{type(stages).__name__}"
            )
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                raise WorkflowManifestError(
                    f"Manifest {manifest_path} stage #{index} must be a "
                    f"mapping, got {type(stage).__name__}"
                )
            stage_missing = [k for k in ("name", "skill") if k not in stage]
            if stage_missing:
                raise WorkflowManifestError(
                    f"Manifest {manifest_path} stage #{index} missing "
                    f"required key(s): {stage_missing}"
                )

    def _init_workflow_session(
        self, session_id: str, request_content: str, manifest: Manifest
    ) -> tuple[Path | None, dict[str, Any] | None]:
        """
        Initialize the session directory.

        Returns (session_dir, error_dict) where error_dict is None on success.
        """
        manifest = Manifest.ensure(manifest)
        try:
            session_dir = session_init(session_id, self.work_dir, request_content)
            logger.info(f"Initialized session {session_id} at {session_dir}")
            return session_dir, None
        except PermissionError as e:
            logger.error(f"Permission error initializing session directory: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.name,
                "stages": [],
                "final_status": "failed",
                "error": f"Permission error initializing session: {str(e)}",
                "error_type": "PermissionError",
            }
        except OSError as e:
            logger.error(f"OS error initializing session directory: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.name,
                "stages": [],
                "final_status": "failed",
                "error": f"OS error initializing session: {str(e)}",
                "error_type": "OSError",
            }
        except (ValueError, InvalidInputError, PathTraversalError) as e:
            logger.error(f"Input error initializing session: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.name,
                "stages": [],
                "final_status": "failed",
                "error": f"Input error initializing session: {str(e)}",
                "error_type": type(e).__name__,
            }

    def _run_workflow_stages(
        self,
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        results: dict[str, Any],
        resume: bool = False,
    ) -> None:
        """Delegate to WorkflowStageExecutor._run_workflow_stages."""
        manifest = Manifest.ensure(manifest)
        return self.workflow_stage_executor._run_workflow_stages(
            manifest, session_dir, session_id, config_overrides, results, resume
        )

    def _finalize_workflow(
        self,
        session_id: str,
        session_dir: Path,
        results: dict[str, Any],
    ) -> None:
        """
        End metrics tracking, export metrics to file, and run monitoring.

        Args:
            session_id: Session identifier
            session_dir: Session directory
            results: Results dictionary containing final status
        """
        # End metrics tracking for this workflow
        self.metrics.end_workflow(session_id, results["final_status"])

        # Export metrics to file
        metrics_file = session_dir / "metrics.json"
        try:
            self.metrics.export_to_file(metrics_file, session_id)
        except (OSError, ValueError) as e:
            logger.error(f"Failed to export metrics to {metrics_file}: {e}")

        # Monitor workflow completion for alerting
        try:
            self.monitoring.monitor_workflow(session_id)
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Error in workflow monitoring: {e}")

#!/usr/bin/env python3
"""
Orchestration Engine - Actual orchestration logic for workflow execution

This engine provides real automation vs manual protocol following.
It reads manifests, executes stages with retry logic, calls deterministic tools,
and manages state transitions.
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from devin_orchestrator.artifact_validator import ArtifactValidator
from devin_orchestrator.config_loader import ConfigLoader
from devin_orchestrator.deterministic_tools import (
    WorkflowManifestError,
    create_placeholder_artifact,  # noqa: F401
    load_manifest,
    load_skill,  # noqa: F401
    session_init,
    update_status,
    validate_structural,  # noqa: F401
    wait_for_file_change,
)
from devin_orchestrator.gate_controller import GateController
from devin_orchestrator.metrics import MetricsCollector
from devin_orchestrator.models import Manifest, Stage
from devin_orchestrator.monitoring import MonitoringSystem
from devin_orchestrator.otel_tracing import trace_span
from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
    parse_config_overrides,
    validate_path_safe,
    validate_session_id,
)
from devin_orchestrator.session_manager import resolve_session
from devin_orchestrator.skill_invoker import SkillInvoker
from devin_orchestrator.stage_skill_dispatcher import StageSkillDispatcher
from devin_orchestrator.state_store import JsonlStateStore
from devin_orchestrator.triage_evaluator import TriageDecision, TriageEvaluator
from devin_orchestrator.workflow_stage_executor import WorkflowStageExecutor

if TYPE_CHECKING:
    from devin_orchestrator.state_store import StateStore

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OrchestrationEngine:
    """Actual orchestration engine for workflow execution"""

    def __getattr__(self, name: str) -> Any:
        """Expose selected module-level helpers so collaborators call patched versions during tests."""
        if name in ("update_status", "load_skill", "validate_path_safe", "validate_structural", "load_manifest", "create_placeholder_artifact"):
            return globals()[name]
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def resume_from_state_store(self, session_id: str) -> dict[str, Any] | None:
        """Rebuild the current session state from disk without re-running any stages."""
        try:
            session_dir = resolve_session(self.work_dir, session_id)
        except (InvalidInputError, PathTraversalError, FileNotFoundError):
            return None
        self._state_store.init(session_id, session_dir)
        return self._state_store.as_dict()

    def __init__(
        self,
        work_dir: Path,
        config: dict[str, Any] | None = None,
        metrics: "MetricsCollector | None" = None,
        monitoring: "MonitoringSystem | None" = None,
        state_store: "StateStore | None" = None,
    ):
        """
        Initialize orchestration engine

        Args:
            work_dir: Base work directory for sessions
            config: Optional configuration dictionary
            metrics: Optional metrics collector (creates a fresh instance by default)
            monitoring: Optional monitoring system (creates a fresh instance by default)
            state_store: Optional workflow state store (defaults to JsonlStateStore)
        """
        try:
            self.work_dir = work_dir
            self.config = config or {}
            self.metrics = metrics if metrics is not None else MetricsCollector()
            self.monitoring = (
                monitoring if monitoring is not None else MonitoringSystem(metrics_collector=self.metrics)
            )
            self.skill_invoker = SkillInvoker(
                demo_mode=self.config.get("demo_mode", False), metrics=self.metrics
            )
            self.artifact_validator = ArtifactValidator(self)
            self.triage_evaluator = TriageEvaluator(self)
            self.stage_skill_dispatcher = StageSkillDispatcher(self)
            self.gate_controller = GateController(self)
            self._state_store = state_store or JsonlStateStore()
            self.workflow_stage_executor = WorkflowStageExecutor(
                self,
                artifact_validator=self.artifact_validator,
                triage_evaluator=self.triage_evaluator,
                stage_skill_dispatcher=self.stage_skill_dispatcher,
                state_store=self._state_store,
            )
            logger.info(f"OrchestrationEngine initialized with work_dir: {work_dir}")
        except Exception as e:
            logger.error(f"Error initializing OrchestrationEngine: {e}")
            raise

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
                manifest, session_dir, session_id, config_overrides, results, resume=False
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
        manifest_path = validate_path_safe(
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
                manifest, session_dir, session_id, config_overrides, results, resume=True
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
                manifest_path = validate_path_safe(
                    base_path, manifest_path, allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                logger.error(f"Input validation failed: {e}")
                return None, None, None, {
                    "session_id": session_id,
                    "manifest": "unknown",
                    "stages": [],
                    "final_status": "failed",
                    "error": f"Input validation failed: {str(e)}",
                    "error_type": "InvalidInputError",
                }

            # Load manifest
            raw_manifest = load_manifest(manifest_path)
            # Validate required structure so a malformed manifest (missing
            # name/stages or per-stage skill/name) raises WorkflowManifestError
            # instead of an uncaught KeyError downstream.
            self._validate_manifest_structure(raw_manifest, manifest_path)
            manifest = Manifest.model_validate(raw_manifest)
            logger.info(
                f"Loaded manifest from {manifest_path}: "
                f"{manifest.name}"
            )
            return session_id, manifest_path, manifest, None
        except FileNotFoundError as e:
            logger.error(f"Manifest file not found: {manifest_path} - {e}")
            return None, None, None, {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"Manifest file not found: {manifest_path}",
                "error_type": "FileNotFoundError",
            }
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in manifest file {manifest_path}: {e}")
            return None, None, None, {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"Invalid JSON in manifest file: {e}",
                "error_type": "JSONDecodeError",
            }
        except WorkflowManifestError as e:
            logger.error(f"Invalid YAML in manifest file {manifest_path}: {e}")
            return None, None, None, {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"Invalid YAML in manifest file: {e}",
                "error_type": "WorkflowManifestError",
            }
        except (OSError, RuntimeError) as e:
            logger.error(
                f"System error loading manifest {manifest_path}: {e}"
            )
            return None, None, None, {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"System error loading manifest: {str(e)}",
                "error_type": type(e).__name__,
            }

    def _validate_manifest_structure(
        self, manifest: Any, manifest_path: Path
    ) -> None:
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

    def _run_workflow_stages(self, manifest: Manifest, session_dir: Path, session_id: str, config_overrides: dict[str, Any] | None, results: dict[str, Any], resume: bool=False) -> None:
        """Delegate to WorkflowStageExecutor._run_workflow_stages."""
        manifest = Manifest.ensure(manifest)
        return self.workflow_stage_executor._run_workflow_stages(manifest, session_dir, session_id, config_overrides, results, resume)

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

    def _execute_stage(self, stage: Stage, manifest: Manifest, session_dir: Path, session_id: str, config_overrides: dict[str, Any] | None=None, correction_artifact: str | None=None, resume: bool=False) -> dict[str, Any]:
        """Delegate to WorkflowStageExecutor._execute_stage."""
        stage = Stage.ensure(stage)
        manifest = Manifest.ensure(manifest)
        return self.workflow_stage_executor._execute_stage(stage, manifest, session_dir, session_id, config_overrides, correction_artifact, resume)


    def _handle_gate(
        self,
        gate_id: str,
        stage_name: str,
        session_dir: Path,
        manifest: Manifest | None = None,
        stage_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Delegate gate handling to GateController."""
        if manifest is not None:
            manifest = Manifest.ensure(manifest)
        return self.gate_controller.handle_gate(
            gate_id, stage_name, session_dir, manifest, stage_result
        )

    def _validate_artifact_path(
        self, artifact_name: str, session_dir: Path
    ) -> Path:
        """Delegate to ArtifactValidator."""
        return self.artifact_validator.validate_artifact_path(
            artifact_name, session_dir
        )

    def _validate_stage_artifacts(
        self,
        stage_name: str,
        session_dir: Path,
        output_artifacts: list[str],
    ) -> tuple[dict[str, Any], list[Path]]:
        """Delegate to ArtifactValidator."""
        return self.artifact_validator.validate_stage_artifacts(
            stage_name, session_dir, output_artifacts
        )

    def _resolve_max_retries(self, stage: Stage) -> int:
        """Delegate to WorkflowStageExecutor._resolve_max_retries."""
        stage = Stage.ensure(stage)
        return self.workflow_stage_executor._resolve_max_retries(stage)

    def _skip_stage(
        self, stage: Stage, session_dir: Path, session_id: str
    ) -> dict[str, Any]:
        """Delegate to WorkflowStageExecutor._skip_stage."""
        stage = Stage.ensure(stage)
        return self.workflow_stage_executor._skip_stage(
            stage, session_dir, session_id
        )

    def _handle_interactive_pause(
        self, stage_name: str, skill_name: str, session_dir: Path
    ) -> dict[str, Any] | None:
        """
        Create a pause file for interactive input and wait for user modification.

        Args:
            stage_name: Name of the stage
            skill_name: Name of the skill being invoked
            session_dir: Session directory

        Returns:
            Error dict if pause file creation fails, None on success
        """
        try:
            pause_file = self._validate_artifact_path(
                f"pause-{stage_name}.md", session_dir
            )
            pause_file.write_text(f"""# Interactive Pause: {stage_name}

The workflow is paused for interactive input.

## Context
Stage: {stage_name}
Skill: {skill_name}

## Instructions
Review the current state and provide any input or feedback needed before proceeding.

## Input Format
```
input: [your input here]
```

Edit this file with your input, then save to continue.
""")
            logger.info(
                f"Created pause file for interactive mode: {pause_file}"
            )
        except PermissionError as e:
            logger.error(f"Permission error creating pause file: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Permission error creating pause file: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Permission error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
        except (OSError, InvalidInputError, PathTraversalError) as e:
            logger.error(f"IO error creating pause file: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"IO error creating pause file: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"IO error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }

        # Wait for pause file to be modified
        self._wait_for_pause_input(pause_file, stage_name, session_dir)
        return None

    def _wait_for_pause_input(
        self, pause_file: Path, stage_name: str, session_dir: Path
    ) -> None:
        """
        Wait for the pause file to be modified with user input.

        Uses filesystem events instead of polling.

        Args:
            pause_file: Path to the pause file
            stage_name: Name of the stage
            session_dir: Session directory
        """
        try:
            max_wait_seconds = self.config.get("pause_timeout_seconds", 3600)
            deadline = time.time() + max_wait_seconds
            initial_content = pause_file.read_text(encoding="utf-8")

            # If the file already contains a valid input, use it immediately.
            initial_input = self._extract_user_input(initial_content)
            if initial_input is not None:
                update_status(
                    session_dir,
                    stage_name,
                    "paused",
                    f"User input received: {initial_input[:50]}...",
                )
                return

            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break

                # Block until the pause file changes or the timeout expires.
                if not wait_for_file_change(pause_file, timeout=remaining):
                    break

                current_content = pause_file.read_text(encoding="utf-8")
                if current_content != initial_content:
                    # Use structured extraction with regex for robust parsing
                    user_input = self._extract_user_input(current_content)

                    if user_input is not None:
                        # Input found and successfully parsed
                        update_status(
                            session_dir,
                            stage_name,
                            "paused",
                            f"User input received: {user_input[:50]}...",
                        )
                        break
                    # If user_input is None, no valid input found yet, continue waiting

            if time.time() >= deadline:
                update_status(
                    session_dir,
                    stage_name,
                    "timeout",
                    f"Interactive pause timeout after {max_wait_seconds} seconds",
                )
        except PermissionError as e:
            logger.error(f"Permission error reading pause file: {e}")
            update_status(
                session_dir,
                stage_name,
                "error",
                f"Permission error reading pause file: {str(e)}",
            )
        except OSError as e:
            logger.error(f"IO error reading pause file: {e}")
            update_status(
                session_dir,
                stage_name,
                "error",
                f"IO error reading pause file: {str(e)}",
            )

    def _extract_user_input(self, content: str) -> str | None:
        """
        Extract user input from pause file content using structured parsing.

        Args:
            content: The pause file content

        Returns:
            Extracted user input, or None if no valid input found
        """
        # Try multiple patterns to extract input, in order of preference
        patterns = [
            # Pattern 1: "input: value" on its own line
            r"^input:\s*(.+)$",
            # Pattern 2: "input: value" anywhere in content (take first match)
            r"input:\s*(.+)",
            # Pattern 3: Markdown code block format
            r"```\s*input:\s*(.+?)\s*```",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                user_input = match.group(1).strip()
                # Validate that we got non-empty input
                if user_input:
                    return user_input

        # No valid input found
        return None

def _print_cli_error(message: str, error_type: str, details: str | None = None) -> NoReturn:
    """Print a CLI error as JSON and exit with code 1."""
    error_data: dict[str, Any] = {"error": message, "error_type": error_type}
    if details is not None:
        error_data["details"] = details
    print(json.dumps(error_data, indent=2))
    sys.exit(1)


def _parse_cli_args() -> tuple:
    """Parse and validate CLI arguments, exiting on usage error."""
    if len(sys.argv) < 4:
        print(
            "Usage: orchestration_engine.py <manifest_path> <session_id> "
            "<request_content> [skip_brainstorming]"
        )
        sys.exit(1)

    manifest_path = Path(sys.argv[1])
    session_id = sys.argv[2]
    request_content = sys.argv[3]
    skip_brainstorming = len(sys.argv) > 4 and sys.argv[4].lower() == "true"
    return manifest_path, session_id, request_content, skip_brainstorming


def _load_cli_config() -> tuple:
    """Load CLI configuration, exiting on error.

    Returns (config, work_dir) on success.
    """
    try:
        config = ConfigLoader.load()
        work_dir = Path(config.session_work_dir)
        logger.info(f"Loaded config, work_dir: {work_dir}")
        return config, work_dir
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        _print_cli_error("Configuration file not found", "FileNotFoundError", str(e))
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        _print_cli_error(
            "Invalid JSON in configuration file", "JSONDecodeError", str(e)
        )
    except (OSError, RuntimeError, ValueError, InvalidInputError, PathTraversalError) as e:
        logger.error(f"Error loading configuration: {e}")
        _print_cli_error(
            "Error loading configuration", type(e).__name__, str(e)
        )


def _create_cli_engine(work_dir: Path, config: Any) -> OrchestrationEngine:
    """Create orchestration engine, exiting on error."""
    try:
        return OrchestrationEngine(work_dir, config.__dict__)
    except (OSError, RuntimeError, ValueError, InvalidInputError, PathTraversalError) as e:
        logger.error(f"Error initializing orchestration engine: {e}")
        _print_cli_error(
            "Error initializing orchestration engine", type(e).__name__, str(e)
        )


def _run_cli_workflow(
    engine: OrchestrationEngine,
    manifest_path: Path,
    session_id: str,
    request_content: str,
    skip_brainstorming: bool,
) -> None:
    """Execute workflow and print results, exiting on error."""
    try:
        results = engine.execute_workflow(
            manifest_path, session_id, request_content, skip_brainstorming
        )
        print(json.dumps(results, indent=2, default=str))
    except (OSError, RuntimeError, ValueError, InvalidInputError, PathTraversalError) as e:
        logger.error(f"Error executing workflow: {e}")
        _print_cli_error(
            "Error executing workflow", type(e).__name__, str(e)
        )


def main():
    """CLI entry point for orchestration engine"""
    try:
        manifest_path, session_id, request_content, skip_brainstorming = (
            _parse_cli_args()
        )

        config, work_dir = _load_cli_config()

        engine = _create_cli_engine(work_dir, config)

        _run_cli_workflow(
            engine, manifest_path, session_id, request_content, skip_brainstorming
        )
    except KeyboardInterrupt:
        logger.info("Workflow execution interrupted by user")
        print(
            json.dumps(
                {
                    "error": "Workflow execution interrupted",
                    "error_type": "KeyboardInterrupt",
                },
                indent=2,
            )
        )
        sys.exit(130)
    except (OSError, RuntimeError, ValueError, InvalidInputError, PathTraversalError) as e:
        logger.error(f"Error in main: {e}")
        print(
            json.dumps(
                {
                    "error": "Error",
                    "error_type": type(e).__name__,
                    "details": str(e),
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

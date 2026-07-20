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
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

from config_loader import ConfigLoader
from deterministic_tools import (
    create_placeholder_artifact,
    load_manifest,
    load_skill,
    record_gate,
    session_init,
    update_status,
    validate_structural,
)
from metrics import get_metrics_collector
from monitoring import get_monitoring_system
from security_utils import (
    InvalidInputError,
    PathTraversalError,
    sanitize_filename,
    validate_path_safe,
    validate_session_id,
)
from skill_invoker import SkillInvoker

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TriageDecision(Enum):
    """Triage decision for stage execution"""

    PROCEED = "proceed"
    RETRY = "retry"
    ESCALATE = "escalate"


class OrchestrationEngine:
    """Actual orchestration engine for workflow execution"""

    def __init__(self, work_dir: Path, config: dict[str, Any] | None = None):
        """
        Initialize orchestration engine

        Args:
            work_dir: Base work directory for sessions
            config: Optional configuration dictionary
        """
        try:
            self.work_dir = work_dir
            self.config = config or {}
            self.skill_invoker = SkillInvoker(demo_mode=config.get("demo_mode", False))
            self.metrics = get_metrics_collector()
            self.monitoring = get_monitoring_system()
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
        session_id, manifest_path, manifest, error = self._validate_and_load_manifest(
            session_id, manifest_path
        )
        if error is not None:
            return error

        # Initialize session
        session_dir, error = self._init_workflow_session(
            session_id, request_content, manifest
        )
        if error is not None:
            return error

        # Override skip_brainstorming if provided
        if skip_brainstorming is not None:
            manifest["skip_brainstorming"] = skip_brainstorming

        # Start metrics tracking for this workflow
        self.metrics.start_workflow(session_id, manifest["name"])

        # Execute stages
        results = {
            "session_id": session_id,
            "manifest": manifest["name"],
            "stages": [],
            "final_status": "unknown",
        }
        self._run_workflow_stages(
            manifest, session_dir, session_id, config_overrides, results
        )

        if results["final_status"] == "unknown":
            results["final_status"] = "completed"

        # Finalize metrics, export, and monitoring
        self._finalize_workflow(session_id, session_dir, results)

        return results

    def _validate_and_load_manifest(
        self, session_id: str, manifest_path: Path
    ) -> tuple:
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
            manifest = load_manifest(manifest_path)
            logger.info(
                f"Loaded manifest from {manifest_path}: "
                f"{manifest.get('name', 'unknown')}"
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
        except Exception as e:
            logger.error(
                f"Unexpected error loading manifest {manifest_path}: {e}"
            )
            return None, None, None, {
                "session_id": session_id,
                "manifest": "unknown",
                "stages": [],
                "final_status": "failed",
                "error": f"Unexpected error loading manifest: {str(e)}",
                "error_type": type(e).__name__,
            }

    def _init_workflow_session(
        self, session_id: str, request_content: str, manifest: dict[str, Any]
    ) -> tuple:
        """
        Initialize the session directory.

        Returns (session_dir, error_dict) where error_dict is None on success.
        """
        try:
            session_dir = session_init(session_id, self.work_dir, request_content)
            logger.info(f"Initialized session {session_id} at {session_dir}")
            return session_dir, None
        except PermissionError as e:
            logger.error(f"Permission error initializing session directory: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.get("name", "unknown"),
                "stages": [],
                "final_status": "failed",
                "error": f"Permission error initializing session: {str(e)}",
                "error_type": "PermissionError",
            }
        except OSError as e:
            logger.error(f"OS error initializing session directory: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.get("name", "unknown"),
                "stages": [],
                "final_status": "failed",
                "error": f"OS error initializing session: {str(e)}",
                "error_type": "OSError",
            }
        except Exception as e:
            logger.error(f"Unexpected error initializing session: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.get("name", "unknown"),
                "stages": [],
                "final_status": "failed",
                "error": f"Unexpected error initializing session: {str(e)}",
                "error_type": type(e).__name__,
            }

    def _run_workflow_stages(
        self,
        manifest: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        results: dict[str, Any],
    ) -> None:
        """Execute all stages in the manifest, updating results in place."""
        for stage in manifest["stages"]:
            try:
                stage_result = self._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id,
                    config_overrides=config_overrides,
                )
                results["stages"].append(stage_result)
            except Exception as e:
                logger.error(
                    f"Unexpected error executing stage "
                    f"{stage.get('name', 'unknown')}: {e}"
                )
                results["stages"].append(
                    {
                        "stage": stage.get("name", "unknown"),
                        "skill": stage.get("skill", "unknown"),
                        "success": False,
                        "output": None,
                        "error": f"Unexpected error during stage execution: {str(e)}",
                        "validation": {
                            "valid": False,
                            "errors": [f"Unexpected error: {str(e)}"],
                            "artifact_results": {},
                        },
                        "triage_decision": TriageDecision.ESCALATE,
                    }
                )
                results["final_status"] = "escalated"
                update_status(
                    session_dir,
                    stage.get("name", "unknown"),
                    "error",
                    f"Unexpected error: {str(e)}",
                )
                break

            # Check triage decision
            if stage_result["triage_decision"] == TriageDecision.ESCALATE:
                results["final_status"] = "escalated"
                update_status(
                    session_dir,
                    stage["name"],
                    "escalated",
                    "Workflow escalated to human",
                )
                break
            elif stage_result["triage_decision"] == TriageDecision.RETRY:
                should_break = self._retry_stage_execution(
                    stage,
                    manifest,
                    session_dir,
                    session_id,
                    config_overrides,
                    stage_result,
                    results,
                )
                if should_break:
                    break

            # Handle gate if present
            if "gate" in stage and stage["gate"] != "none":
                gate_result = self._handle_gate(
                    gate_id=stage["gate"],
                    stage_name=stage["name"],
                    session_dir=session_dir,
                )
                if gate_result["blocked"]:
                    results["final_status"] = "blocked"
                    break

    def _retry_stage_execution(
        self,
        stage: dict[str, Any],
        manifest: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        stage_result: dict[str, Any],
        results: dict[str, Any],
    ) -> bool:
        """
        Retry a failed stage with exponential backoff and correction artifacts.

        Returns True if the outer stage loop should break (retries exhausted).
        """
        max_retries = self._resolve_max_retries(stage)
        retry_count = 0
        last_error = stage_result["error"]

        while retry_count < max_retries:
            retry_count += 1
            update_status(
                session_dir,
                stage["name"],
                "retrying",
                f"Retry {retry_count}/{max_retries}: {last_error}",
            )

            # Exponential backoff: 2^retry_count seconds
            backoff_seconds = 2**retry_count
            time.sleep(backoff_seconds)

            # Re-dispatch with correction artifact
            try:
                correction_artifact = self._validate_artifact_path(
                    f"correction-{stage['name']}-attempt{retry_count}.md",
                    session_dir,
                )
                correction_artifact.write_text(
                    f"# Correction for {stage['name']}\n\n"
                    f"Error: {last_error}\n\n"
                    "Please fix the issue and re-run the stage."
                )
                logger.info(
                    f"Created correction artifact: {correction_artifact}"
                )
            except (OSError, PermissionError, InvalidInputError, PathTraversalError) as e:
                logger.error(f"Error creating correction artifact: {e}")
                update_status(
                    session_dir,
                    stage["name"],
                    "error",
                    f"Failed to create correction artifact: {str(e)}",
                )
                break

            stage_result = self._execute_stage(
                stage=stage,
                manifest=manifest,
                session_dir=session_dir,
                session_id=session_id,
                config_overrides=config_overrides,
                correction_artifact=str(correction_artifact),
            )

            if stage_result["triage_decision"] == TriageDecision.PROCEED:
                break
            last_error = stage_result["error"]

        if (
            retry_count >= max_retries
            and stage_result["triage_decision"] != TriageDecision.PROCEED
        ):
            results["final_status"] = "escalated"
            update_status(
                session_dir,
                stage["name"],
                "escalated",
                f"Max retries ({max_retries}) exceeded: {last_error}",
            )
            # Log retry exhaustion
            logger.warning(
                f"Retry attempts exhausted for stage {stage['name']} "
                f"after {max_retries} attempts: {last_error}"
            )
            return True

        return False

    def _resolve_max_retries(self, stage: dict[str, Any]) -> int:
        """Resolve max retry count for a stage from its configuration.

        Falls back to the default of 3 and clamps to a sane range.
        Invalid values are logged and treated as the default.
        """
        default_max = 3
        stage_name = stage.get("name", "<unknown>")
        raw_max = stage.get("max_retries", default_max)
        try:
            max_retries = int(raw_max)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid max_retries value for stage {stage_name}: "
                f"{raw_max!r}; using default {default_max}"
            )
            return default_max
        if max_retries < 0:
            logger.warning(
                f"max_retries cannot be negative for stage {stage_name}; "
                f"using {default_max}"
            )
            return default_max
        if max_retries > 10:
            logger.warning(
                f"max_retries too large for stage {stage_name}; clamping to 10"
            )
            return 10
        return max_retries

    def _finalize_workflow(
        self,
        session_id: str,
        session_dir: Path,
        results: dict[str, Any],
    ) -> None:
        """End metrics tracking, export metrics to file, and run monitoring."""
        # End metrics tracking for this workflow
        self.metrics.end_workflow(session_id, results["final_status"])

        # Export metrics to file
        metrics_file = session_dir / "metrics.json"
        self.metrics.export_to_file(metrics_file, session_id)

        # Monitor workflow completion for alerting
        try:
            self.monitoring.monitor_workflow(session_id)
        except Exception as e:
            logger.error(f"Error in workflow monitoring: {e}")

    def _execute_stage(
        self,
        stage: dict[str, Any],
        manifest: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None = None,
        correction_artifact: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a single stage

        Args:
            stage: Stage configuration from manifest
            manifest: Full manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills

        Returns:
            Dictionary with stage execution results
        """
        stage_name = stage["name"]
        skill_name = stage["skill"]

        update_status(
            session_dir, stage_name, "in_progress", f"Starting stage: {stage_name}"
        )

        # Check if stage should be skipped
        if manifest.get("skip_brainstorming", False) and stage_name == "brainstorming":
            return self._skip_stage(stage, session_dir, session_id)

        # Track stage execution with metrics
        with self.metrics.track_stage(stage_name, skill_name):
            # Check if interactive mode is enabled for this stage
            if config_overrides and config_overrides.get("interactive_mode", False):
                error = self._handle_interactive_pause(
                    stage_name, skill_name, session_dir
                )
                if error is not None:
                    return error

            # Load skill
            skill_error = self._load_stage_skill(skill_name, stage_name)
            if skill_error is not None:
                return skill_error

            # Dispatch skill with metrics tracking
            with self.metrics.track_skill_invocation(
                skill_name,
                session_id,
                stage.get("skill") == "requesting-code-review",
            ):
                result, dispatch_error = self._dispatch_stage_skill(
                    skill_name,
                    stage_name,
                    stage,
                    session_dir,
                    session_id,
                    config_overrides,
                    correction_artifact,
                )
                if dispatch_error is not None:
                    return dispatch_error

            # Validate output artifacts
            validation_result, artifact_paths = self._validate_stage_artifacts(
                stage_name, session_dir, stage.get("output_artifacts", [])
            )

            # Dispatch reviewer, make triage decision, and build result
            return self._evaluate_stage_and_triage(
                stage_name,
                skill_name,
                session_dir,
                session_id,
                result,
                validation_result,
                artifact_paths,
                correction_artifact,
            )

    def _handle_interactive_pause(
        self, stage_name: str, skill_name: str, session_dir: Path
    ) -> dict[str, Any] | None:
        """
        Create a pause file for interactive input and wait for user modification.

        Returns an error dict if pause file creation fails, None on success.
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
        """Wait for the pause file to be modified with user input."""
        try:
            import time

            max_wait_seconds = self.config.get("pause_timeout_seconds", 3600)
            check_interval = self.config.get("pause_check_interval", 5)
            waited_seconds = 0
            initial_content = pause_file.read_text(encoding="utf-8")

            while waited_seconds < max_wait_seconds:
                time.sleep(check_interval)
                waited_seconds += check_interval

                current_content = pause_file.read_text(encoding="utf-8")
                if (
                    current_content != initial_content
                    and "input:" in current_content
                ):
                    # Parse user input
                    user_input = ""
                    for line in current_content.split("\n"):
                        if line.startswith("input:"):
                            user_input = line.split(":", 1)[1].strip()
                            break

                    update_status(
                        session_dir,
                        stage_name,
                        "paused",
                        f"User input received: {user_input[:50]}...",
                    )
                    break

            if waited_seconds >= max_wait_seconds:
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

    def _load_stage_skill(
        self, skill_name: str, stage_name: str
    ) -> dict[str, Any] | None:
        """
        Load a skill definition from the configured skills directory.

        Returns an error dict on failure, None on success.
        """
        try:
            from config_loader import ConfigLoader

            config = ConfigLoader.load()
            skills_dir = config.skills_dir
            load_skill(skills_dir, skill_name)
            logger.info(f"Loaded skill {skill_name} from {skills_dir}")
            return None
        except FileNotFoundError as e:
            logger.error(f"Skill directory or file not found for {skill_name}: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Skill not found: {skill_name}",
                "validation": {
                    "valid": False,
                    "errors": [f"Skill not found: {skill_name}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in skill file for {skill_name}: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Invalid JSON in skill file: {e}",
                "validation": {
                    "valid": False,
                    "errors": [f"Invalid JSON in skill file: {e}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
        except Exception as e:
            logger.error(f"Unexpected error loading skill {skill_name}: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Unexpected error loading skill: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Unexpected error loading skill: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }

    def _dispatch_stage_skill(
        self,
        skill_name: str,
        stage_name: str,
        stage: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        correction_artifact: str | None,
    ) -> tuple:
        """
        Dispatch skill invocation with error handling and metrics recording.

        Returns (result, error_dict) where error_dict is None on success.
        """
        try:
            result = self.skill_invoker.invoke_skill(
                skill_name=skill_name,
                context={
                    "session_id": session_id,
                    "stage": stage_name,
                    "skill": skill_name,
                },
                workspace=str(session_dir),
                is_reviewer=stage.get("skill") == "requesting-code-review",
                config_overrides=config_overrides,
                correction_artifact=correction_artifact,
            )
            logger.info(
                f"Skill {skill_name} invocation completed with "
                f"success={result.success}"
            )

            # Record skill result in metrics
            self.metrics.record_skill_result(
                skill_name, result.success, result.error
            )
            return result, None
        except RuntimeError as e:
            logger.error(
                f"Runtime error during skill invocation for {skill_name}: {e}"
            )
            self.metrics.record_skill_result(
                skill_name, False, f"Runtime error: {str(e)}"
            )
            return None, {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Runtime error during skill invocation: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Runtime error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
        except TimeoutError as e:
            logger.error(f"Timeout during skill invocation for {skill_name}: {e}")
            self.metrics.record_skill_result(
                skill_name, False, f"Timeout: {str(e)}"
            )
            return None, {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Timeout during skill invocation: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Timeout: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.RETRY,
            }
        except Exception as e:
            logger.error(
                f"Unexpected error during skill invocation for {skill_name}: {e}"
            )
            self.metrics.record_skill_result(
                skill_name, False, f"Unexpected error: {str(e)}"
            )
            return None, {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Unexpected error during skill invocation: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Unexpected error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }

    def _validate_artifact_path(
        self, artifact_name: str, session_dir: Path
    ) -> Path:
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
        return validate_path_safe(session_dir, candidate, allow_absolute=True)

    def _validate_stage_artifacts(
        self,
        stage_name: str,
        session_dir: Path,
        output_artifacts: list[str],
    ) -> tuple:
        """
        Validate stage output artifacts structurally.

        Returns (validation_result, artifact_paths).
        """
        artifact_paths: list[Path] = []
        for artifact in output_artifacts:
            try:
                artifact_paths.append(
                    self._validate_artifact_path(artifact, session_dir)
                )
            except (InvalidInputError, PathTraversalError) as e:
                logger.error(
                    f"Invalid artifact path for stage {stage_name}: {e}"
                )
                return (
                    {
                        "valid": False,
                        "errors": [f"Invalid artifact path {artifact!r}: {str(e)}"],
                        "artifact_results": {},
                    },
                    [],
                )
        try:
            validation_result = validate_structural(artifact_paths)
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
        except Exception as e:
            logger.error(
                f"Unexpected error during validation for stage {stage_name}: {e}"
            )
            return (
                {
                    "valid": False,
                    "errors": [f"Unexpected validation error: {str(e)}"],
                    "artifact_results": {},
                },
                artifact_paths,
            )

    def _evaluate_stage_and_triage(
        self,
        stage_name: str,
        skill_name: str,
        session_dir: Path,
        session_id: str,
        result: Any,
        validation_result: dict[str, Any],
        artifact_paths: list[Path],
        correction_artifact: str | None,
    ) -> dict[str, Any]:
        """
        Dispatch neutral reviewer, make triage decision, and build stage result.

        Returns the final stage execution result dictionary.
        """
        # Dispatch neutral reviewer after structural validation passes
        reviewer_verdict = "PASS"
        confidence = "HIGH"
        review_output = None
        review_artifact_path = None

        if result.success and validation_result["valid"]:
            try:
                review_artifact_path = self._validate_artifact_path(
                    f"review-{stage_name}.md", session_dir
                )
                reviewer_verdict, confidence, review_output = self._dispatch_reviewer(
                    stage_name=stage_name,
                    skill_name=skill_name,
                    session_dir=session_dir,
                    session_id=session_id,
                    artifact_paths=artifact_paths,
                    correction_artifact=correction_artifact,
                )
                if review_artifact_path and review_output:
                    review_artifact_path.write_text(
                        review_output, encoding="utf-8"
                    )
            except Exception as e:
                logger.error(
                    f"Reviewer dispatch failed for stage {stage_name}: {e}"
                )
                reviewer_verdict = "FAIL"
                confidence = "LOW"

        # Make triage decision
        if not result.success:
            triage_decision = TriageDecision.ESCALATE
            error = result.error
        elif not validation_result["valid"]:
            triage_decision = TriageDecision.RETRY
            error = "; ".join(validation_result["errors"])
        elif reviewer_verdict == "FAIL" or confidence == "LOW":
            triage_decision = TriageDecision.RETRY
            error = f"Reviewer verdict: {reviewer_verdict}, confidence: {confidence}"
        else:
            triage_decision = TriageDecision.PROCEED
            error = None

        # Record stage result in metrics
        self.metrics.record_stage_result(
            stage_name, result.success, error, triage_decision.value
        )

        update_status(
            session_dir,
            stage_name,
            "completed" if triage_decision == TriageDecision.PROCEED else "failed",
            f"Triage decision: {triage_decision.value}",
        )

        return {
            "stage": stage_name,
            "skill": skill_name,
            "success": result.success,
            "output": result.output,
            "error": error,
            "validation": validation_result,
            "reviewer_verdict": reviewer_verdict,
            "confidence": confidence,
            "triage_decision": triage_decision,
        }

    def _dispatch_reviewer(
        self,
        stage_name: str,
        skill_name: str,
        session_dir: Path,
        session_id: str,
        artifact_paths: list[Path],
        correction_artifact: str | None = None,
    ) -> tuple:
        """
        Dispatch a neutral reviewer worker to evaluate stage artifacts.

        Returns a tuple of (verdict, confidence, review_output) where verdict is
        'PASS' or 'FAIL' and confidence is 'HIGH', 'MEDIUM', or 'LOW'.
        """
        focused_context = [str(p) for p in artifact_paths if p.exists()]
        if not focused_context:
            return "PASS", "HIGH", "No artifacts to review"

        review_output_artifact = self._validate_artifact_path(
            f"review-{stage_name}.md", session_dir
        )
        if review_output_artifact.exists():
            try:
                existing_review = review_output_artifact.read_text(encoding="utf-8")
            except Exception:
                existing_review = ""
        else:
            existing_review = ""

        reviewer_context = {
            "session_id": session_id,
            "stage": stage_name,
            "skill": skill_name,
            "role": "reviewer",
        }

        result = self.skill_invoker.invoke_skill(
            skill_name="swe-compliance",
            context=reviewer_context,
            workspace=str(session_dir),
            focused_context=focused_context,
            correction_artifact=correction_artifact,
            is_reviewer=True,
        )

        if not result.success:
            return "FAIL", "LOW", result.error

        review_output = result.output or existing_review or "Reviewer approved"

        # Simple heuristic verdict parsing
        review_lower = review_output.lower()
        if any(
            word in review_lower
            for word in ["fail", "rejected", "critical", "error", "invalid"]
        ):
            verdict = "FAIL"
            confidence = "LOW"
        elif any(
            word in review_lower
            for word in ["minor", "caveat", "warning", "suggestion", "medium"]
        ):
            verdict = "PASS"
            confidence = "MEDIUM"
        else:
            verdict = "PASS"
            confidence = "HIGH"

        review_text = f"# Review for {stage_name}\n\nVerdict: {verdict}\nConfidence: {confidence}\n\n{review_output}"
        return verdict, confidence, review_text

    def _skip_stage(
        self, stage: dict[str, Any], session_dir: Path, session_id: str
    ) -> dict[str, Any]:
        """
        Skip a stage (e.g., brainstorming when spec is clear)

        Args:
            stage: Stage configuration from manifest
            session_dir: Session directory
            session_id: Session identifier

        Returns:
            Dictionary with stage skip results
        """
        stage_name = stage["name"]

        update_status(
            session_dir, stage_name, "skipped", "Skipping stage - spec is clear"
        )

        # Create placeholder artifacts
        try:
            output_artifacts = stage.get("output_artifacts", [])
            for artifact in output_artifacts:
                artifact_path = self._validate_artifact_path(artifact, session_dir)
                if artifact_path.name == "design.md":
                    placeholder = f"# Design\n\nSkipping brainstorming - spec is clear.\n\nSession ID: {session_id}\n"
                    create_placeholder_artifact(artifact_path, placeholder)
                    logger.info(f"Created placeholder artifact: {artifact_path}")
        except (OSError, PermissionError, InvalidInputError, PathTraversalError) as e:
            logger.error(f"Error creating placeholder artifacts: {e}")
            return {
                "stage": stage_name,
                "skill": stage["skill"],
                "success": False,
                "output": "Stage skip failed - artifact creation error",
                "error": f"Error creating placeholder artifacts: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Artifact creation error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }

        return {
            "stage": stage_name,
            "skill": stage["skill"],
            "success": True,
            "output": "Stage skipped - spec is clear",
            "error": None,
            "validation": {"valid": True, "errors": [], "artifact_results": {}},
            "triage_decision": TriageDecision.PROCEED,
        }

    def _handle_gate(
        self, gate_id: str, stage_name: str, session_dir: Path
    ) -> dict[str, Any]:
        """
        Handle a gate (human approval or auto-gate)

        Args:
            gate_id: Gate identifier
            stage_name: Stage name for context
            session_dir: Session directory

        Returns:
            Dictionary with gate handling results
        """
        update_status(
            session_dir,
            f"gate_{gate_id}",
            "waiting",
            f"Waiting for gate decision: {gate_id}",
        )

        # Create gate decision file for human input
        error = self._create_gate_decision_file(gate_id, stage_name, session_dir)
        if error is not None:
            return error

        # Re-derive the validated gate decision path so the wait loop reads
        # from the same validated location that was written above.
        gate_decision_file = self._validate_artifact_path(
            f"gate-{gate_id}-decision.md", session_dir
        )

        # Wait for gate decision file to be modified
        try:
            return self._wait_and_parse_gate_decision(
                gate_id, session_dir, gate_decision_file
            )
        except Exception as e:
            logger.error(f"Unexpected error during gate handling: {e}")
            update_status(
                session_dir,
                f"gate_{gate_id}",
                "error",
                f"Unexpected gate handling error: {str(e)}",
            )
            return {
                "gate_id": gate_id,
                "verdict": "block",
                "blocked": True,
                "error": f"Unexpected gate handling error: {str(e)}",
            }

    def _create_gate_decision_file(
        self, gate_id: str, stage_name: str, session_dir: Path
    ) -> dict[str, Any] | None:
        """
        Create the gate decision file for human input.

        Returns an error dict on failure, None on success.
        """
        try:
            gate_decision_file = self._validate_artifact_path(
                f"gate-{gate_id}-decision.md", session_dir
            )
            gate_decision_file.write_text(f"""# Gate Decision: {gate_id}

Stage: {stage_name}

Please review the stage output and provide your decision.

## Options:
- approve: Proceed to next stage
- request_changes: Request changes and retry
- block: Block workflow and escalate to human

## Decision Format:
```
verdict: approve|request_changes|block
notes: [optional notes]
```

Please edit this file with your decision.
""")
            logger.info(f"Created gate decision file: {gate_decision_file}")
            return None
        except (OSError, PermissionError) as e:
            logger.error(f"Error creating gate decision file: {e}")
            update_status(
                session_dir,
                f"gate_{gate_id}",
                "error",
                f"Failed to create gate decision file: {str(e)}",
            )
            return {
                "gate_id": gate_id,
                "verdict": "block",
                "blocked": True,
                "error": f"Failed to create gate decision file: {str(e)}",
            }

    def _wait_and_parse_gate_decision(
        self, gate_id: str, session_dir: Path, gate_decision_file: Path
    ) -> dict[str, Any]:
        """
        Wait for the gate decision file to be modified and parse the decision.

        Returns a gate result dictionary (either a verdict, a read error, or a
        timeout).
        """
        import time

        max_wait_seconds = self.config.get("gate_timeout_seconds", 3600)
        check_interval = self.config.get("gate_check_interval", 5)
        waited_seconds = 0

        while waited_seconds < max_wait_seconds:
            time.sleep(check_interval)
            waited_seconds += check_interval

            # Check if file has been modified (contains decision)
            try:
                content = gate_decision_file.read_text(encoding="utf-8")
            except (OSError, PermissionError) as e:
                logger.error(f"Error reading gate decision file: {e}")
                update_status(
                    session_dir,
                    f"gate_{gate_id}",
                    "error",
                    f"Failed to read gate decision file: {str(e)}",
                )
                return {
                    "gate_id": gate_id,
                    "verdict": "block",
                    "blocked": True,
                    "error": f"Failed to read gate decision file: {str(e)}",
                }

            parsed = self._parse_gate_verdict(content)
            if parsed is not None:
                verdict, notes = parsed
                if verdict in ["approve", "request_changes", "block"]:
                    try:
                        record_gate(gate_id, verdict, session_dir, notes)
                        update_status(
                            session_dir,
                            f"gate_{gate_id}",
                            verdict,
                            f"Gate {verdict}: {gate_id}",
                        )
                        logger.info(
                            f"Gate {gate_id} decision recorded: {verdict}"
                        )
                    except Exception as e:
                        logger.error(f"Error recording gate decision: {e}")
                        update_status(
                            session_dir,
                            f"gate_{gate_id}",
                            "error",
                            f"Failed to record gate decision: {str(e)}",
                        )

                    return {
                        "gate_id": gate_id,
                        "verdict": verdict,
                        "blocked": verdict == "block",
                    }

        # Timeout reached - escalate
        verdict = "block"
        notes = f"Gate decision timeout after {max_wait_seconds} seconds"
        try:
            record_gate(gate_id, verdict, session_dir, notes)
            update_status(
                session_dir,
                f"gate_{gate_id}",
                "timeout",
                f"Gate timeout: {gate_id}",
            )
            logger.warning(
                f"Gate {gate_id} timeout after {max_wait_seconds} seconds"
            )
        except Exception as e:
            logger.error(f"Error recording gate timeout: {e}")
            update_status(
                session_dir,
                f"gate_{gate_id}",
                "error",
                f"Failed to record gate timeout: {str(e)}",
            )

        return {"gate_id": gate_id, "verdict": verdict, "blocked": True}

    def _parse_gate_verdict(
        self, content: str
    ) -> tuple[str, str] | None:
        """
        Parse verdict and notes from gate decision file content.

        Returns (verdict, notes) if a verdict line is found, None otherwise.
        """
        if "verdict:" not in content:
            return None
        verdict = None
        notes = ""
        for line in content.split("\n"):
            if line.startswith("verdict:"):
                verdict = line.split(":", 1)[1].strip()
            elif line.startswith("notes:"):
                notes = line.split(":", 1)[1].strip()
        return verdict, notes


def _print_cli_error(message: str, error_type: str, details: str | None = None) -> None:
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
    except Exception as e:
        logger.error(f"Unexpected error loading configuration: {e}")
        _print_cli_error(
            "Unexpected error loading configuration", type(e).__name__, str(e)
        )


def _create_cli_engine(work_dir: Path, config: Any) -> OrchestrationEngine:
    """Create orchestration engine, exiting on error."""
    try:
        return OrchestrationEngine(work_dir, config.__dict__)
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        print(
            json.dumps(
                {
                    "error": "Unexpected error",
                    "error_type": type(e).__name__,
                    "details": str(e),
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

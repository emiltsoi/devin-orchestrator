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
import random
import re
import shutil
import sys
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metrics import MetricsCollector
    from monitoring import MonitoringSystem

from config_loader import ConfigLoader
from deterministic_tools import (
    WorkflowManifestError,
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
from session_manager import resolve_session
from skill_invoker import SkillInvocationResult, SkillInvoker

# Gate interaction modes
GATE_MODE_INTERACTIVE = "interactive"
GATE_MODE_SIGNAL = "signal"
GATE_MODE_AUTO = "auto"

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

    def __init__(self, work_dir: Path, config: dict[str, Any] | None = None, metrics: "MetricsCollector | None" = None, monitoring: "MonitoringSystem | None" = None):
        """
        Initialize orchestration engine

        Args:
            work_dir: Base work directory for sessions
            config: Optional configuration dictionary
            metrics: Optional metrics collector (defaults to global instance)
            monitoring: Optional monitoring system (defaults to global instance)
        """
        try:
            self.work_dir = work_dir
            self.config = config or {}
            self.skill_invoker = SkillInvoker(demo_mode=self.config.get("demo_mode", False))
            # Use provided instances or fall back to global instances for backward compatibility
            self.metrics = metrics if metrics is not None else get_metrics_collector()
            self.monitoring = monitoring if monitoring is not None else get_monitoring_system()
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
        focused_context: list[str] | None = None,
        output_file: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a complete workflow from manifest

        Args:
            manifest_path: Path to workflow manifest
            session_id: Unique session identifier
            request_content: Initial request content
            skip_brainstorming: Override manifest skip_brainstorming setting
            config_overrides: Optional configuration overrides for skills
            focused_context: Optional list of file paths to inject into each stage
            output_file: Optional path (relative to session) for a final summary report

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

        # Persist manifest name and original inputs in session.json so a later
        # continue_workflow call can resume without requiring the caller to resupply them.
        self._update_session_inputs(
            session_dir,
            manifest["name"],
            request_content,
            focused_context or [],
            output_file,
        )

        # Seed focused context files into the session directory so stage workers
        # can access them without escaping the session sandbox.
        if focused_context:
            self._seed_focused_context(session_dir, focused_context)

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
            manifest,
            session_dir,
            session_id,
            config_overrides,
            results,
            resume=False,
            focused_context=focused_context or [],
        )

        if results["final_status"] == "unknown":
            results["final_status"] = "completed"

        # Write final summary report if requested
        if output_file and results["final_status"] == "completed":
            self._write_output_file(session_dir, output_file, results)

        # Enrich results with artifact paths and a stateless resume ticket
        results["artifact_paths"] = self._list_session_artifacts(session_dir)
        waiting_gate_id = self._find_waiting_gate_id(results) if results["final_status"] == "waiting_for_input" else None
        failing_stage = None
        if results["final_status"] in ("escalated", "blocked"):
            for entry in reversed(results.get("stages", [])):
                if entry.get("triage_decision") in (TriageDecision.ESCALATE, TriageDecision.RETRY) or entry.get("success") is False:
                    failing_stage = entry.get("stage")
                    break
        results["resume"] = self._build_resume(
            session_id,
            results["final_status"],
            failing_stage,
            waiting_gate_id,
            results.get("error"),
            results.get("artifact_paths", []),
        )

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
        correction_artifact: str | None = None,
        feedback: str | None = None,
        focused_context: list[str] | None = None,
        output_file: str | None = None,
    ) -> dict[str, Any]:
        """
        Resume a workflow that paused at a gate or escalated.

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
            correction_artifact: Optional path to a correction/feedback artifact
            feedback: Optional inline feedback text to write as correction artifact
            focused_context: Optional additional focused context for resume
            output_file: Optional path for final summary report

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

        session_id, manifest_path, manifest, error = self._validate_and_load_manifest(
            session_id, manifest_path
        )
        if error is not None:
            return error

        # Load original inputs if caller did not resupply them
        original_request, original_focused_context, original_output_file = self._load_session_inputs(session_dir)
        if focused_context is None:
            focused_context = original_focused_context
        if output_file is None:
            output_file = original_output_file

        # Seed focused context files into the session directory
        if focused_context:
            self._seed_focused_context(session_dir, focused_context)

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

        # If inline feedback is supplied, write it as a correction artifact for the
        # stage that needs to retry.
        effective_correction_artifact = correction_artifact
        if feedback:
            correction_file = self._validate_artifact_path(
                f"correction-resume-{session_id}.md", session_dir
            )
            try:
                correction_file.write_text(feedback, encoding="utf-8")
                effective_correction_artifact = str(correction_file)
            except (OSError, PermissionError) as e:
                logger.error(f"Failed to write feedback correction artifact: {e}")

        # Start/resume metrics tracking
        self.metrics.start_workflow(session_id, manifest["name"])

        results = {
            "session_id": session_id,
            "manifest": manifest["name"],
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
            focused_context=focused_context or [],
            correction_artifact=effective_correction_artifact,
        )

        if results["final_status"] == "unknown":
            results["final_status"] = "completed"

        if output_file and results["final_status"] == "completed":
            self._write_output_file(session_dir, output_file, results)

        # Enrich results with artifact paths and a stateless resume ticket
        results["artifact_paths"] = self._list_session_artifacts(session_dir)
        waiting_gate_id = self._find_waiting_gate_id(results) if results["final_status"] == "waiting_for_input" else None
        failing_stage = None
        if results["final_status"] in ("escalated", "blocked"):
            for entry in reversed(results.get("stages", [])):
                if entry.get("triage_decision") in (TriageDecision.ESCALATE, TriageDecision.RETRY) or entry.get("success") is False:
                    failing_stage = entry.get("stage")
                    break
        results["resume"] = self._build_resume(
            session_id,
            results["final_status"],
            failing_stage,
            waiting_gate_id,
            results.get("error"),
            results.get("artifact_paths", []),
        )

        self._finalize_workflow(session_id, session_dir, results)
        return results

    def _update_session_inputs(
        self,
        session_dir: Path,
        manifest_name: str,
        request_content: str,
        focused_context: list[str],
        output_file: str | None,
    ) -> None:
        """Persist original inputs in session.json for later continuation."""
        session_file = session_dir / "session.json"
        try:
            session_data = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            session_data = {}
        session_data["manifest"] = manifest_name
        session_data["request_content"] = request_content
        session_data["focused_context"] = focused_context
        session_data["output_file"] = output_file
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to record inputs in session.json: {e}")

    def _load_session_inputs(
        self, session_dir: Path
    ) -> tuple[str, list[str], str | None]:
        """Load original inputs from session.json."""
        session_file = session_dir / "session.json"
        try:
            session_data = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read session.json: {e}")
            return "", [], None
        return (
            session_data.get("request_content", ""),
            session_data.get("focused_context", []),
            session_data.get("output_file", None),
        )

    def _seed_focused_context(self, session_dir: Path, focused_context: list[str]) -> list[str]:
        """Copy focused context files into the session directory and return their paths."""
        if not focused_context:
            return []
        seeded: list[str] = []
        for raw_file in focused_context:
            raw = raw_file.strip()
            if not raw:
                continue
            try:
                source = validate_path_safe(
                    Path(self.work_dir), Path(raw), allow_absolute=True
                )
                if not source.is_file():
                    logger.warning(f"Focused context file not found: {source}")
                    continue
                # Keep relative structure under session dir for clarity
                dest = validate_path_safe(
                    session_dir, session_dir / source.name, allow_absolute=True
                )
                shutil.copy2(source, dest)
                seeded.append(str(dest))
                logger.info(f"Seeded workflow focused context: {source} -> {dest}")
            except (InvalidInputError, PathTraversalError, OSError, ValueError) as e:
                logger.warning(f"Failed to seed focused context {raw}: {e}")
        return seeded

    def _write_output_file(
        self, session_dir: Path, output_file: str, results: dict[str, Any]
    ) -> None:
        """Write a structured summary report to the requested output file."""
        try:
            out_path = validate_path_safe(
                session_dir, session_dir / output_file, allow_absolute=True
            )
            summary = {
                "session_id": results.get("session_id"),
                "manifest": results.get("manifest"),
                "final_status": results.get("final_status"),
                "stages": [
                    {
                        "stage": s.get("stage"),
                        "skill": s.get("skill"),
                        "success": s.get("success"),
                        "triage_decision": s.get("triage_decision"),
                        "error": s.get("error"),
                    }
                    for s in results.get("stages", [])
                ],
            }
            out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        except (InvalidInputError, PathTraversalError, OSError) as e:
            logger.warning(f"Failed to write output_file {output_file}: {e}")

    def _build_resume(
        self,
        session_id: str,
        final_status: str,
        stage_name: str | None,
        gate_id: str | None,
        error: str | None,
        artifact_paths: list[str],
    ) -> dict[str, Any] | None:
        """Build a stateless resume ticket for the calling agent."""
        if final_status == "completed":
            return None

        resume: dict[str, Any] = {
            "tool": "mcp0_continue_workflow",
            "arguments": {
                "session_id": session_id,
            },
        }

        if final_status == "waiting_for_input" and gate_id:
            resume["tool"] = "mcp0_gate_decision"
            resume["arguments"] = {
                "session_id": session_id,
                "gate_id": gate_id,
                "verdict": "approve|request_changes|block",
                "notes": "",
            }
            resume["then"] = {
                "tool": "mcp0_continue_workflow",
                "arguments": {"session_id": session_id},
            }
        elif final_status in ("escalated", "blocked"):
            resume["arguments"]["feedback"] = error or "<agent fills this with correction/feedback>"
            if stage_name:
                resume["arguments"]["stage"] = stage_name
            if artifact_paths:
                resume["arguments"]["correction_artifact"] = artifact_paths[-1]

        return resume

    def _list_session_artifacts(self, session_dir: Path) -> list[str]:
        """List durable artifacts in the session directory, excluding temp files."""
        if not session_dir.exists():
            return []
        artifacts: list[str] = []
        for f in sorted(session_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("devin_prompt_"):
                artifacts.append(str(f))
        return artifacts

    def _find_waiting_gate_id(self, session_data: dict[str, Any]) -> str | None:
        """Find the most recent gate that is still waiting for input."""
        for entry in reversed(session_data.get("stages", [])):
            stage_name = entry.get("stage", "")
            if stage_name.startswith("gate_") and entry.get("status") == "waiting":
                return stage_name.replace("gate_", "", 1)
        return None

    def _validate_and_load_manifest(
        self, session_id: str, manifest_path: Path
    ) -> tuple[str, Path, dict[str, Any] | None, dict[str, Any] | None]:
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
            # Validate required structure so a malformed manifest (missing
            # name/stages or per-stage skill/name) raises WorkflowManifestError
            # instead of an uncaught KeyError downstream.
            self._validate_manifest_structure(manifest, manifest_path)
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
        self, session_id: str, request_content: str, manifest: dict[str, Any]
    ) -> tuple[Path, dict[str, Any] | None]:
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
        except (ValueError, InvalidInputError, PathTraversalError) as e:
            logger.error(f"Input error initializing session: {e}")
            return None, {
                "session_id": session_id,
                "manifest": manifest.get("name", "unknown"),
                "stages": [],
                "final_status": "failed",
                "error": f"Input error initializing session: {str(e)}",
                "error_type": type(e).__name__,
            }

    def _run_workflow_stages(
        self,
        manifest: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        results: dict[str, Any],
        resume: bool = False,
        focused_context: list[str] | None = None,
        correction_artifact: str | None = None,
    ) -> None:
        """
        Execute all stages in the manifest, updating results in place.

        Args:
            manifest: Workflow manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills
            results: Results dictionary to update in place
            resume: If True, skip stages already marked completed in session.json
            focused_context: Optional file paths to inject into each stage
            correction_artifact: Optional correction artifact for retry
        """
        for stage in manifest["stages"]:
            try:
                stage_result = self._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id,
                    config_overrides=config_overrides,
                    resume=resume,
                    focused_context=focused_context,
                    correction_artifact=correction_artifact,
                )
                results["stages"].append(stage_result)
            except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                logger.error(
                    f"Error executing stage "
                    f"{stage.get('name', 'unknown')}: {e}"
                )
                results["stages"].append(
                    {
                        "stage": stage.get("name", "unknown"),
                        "skill": stage.get("skill", "unknown"),
                        "success": False,
                        "output": None,
                        "error": f"Error during stage execution: {str(e)}",
                        "validation": {
                            "valid": False,
                            "errors": [f"Error: {str(e)}"],
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
                    manifest=manifest,
                    stage_result=stage_result,
                )
                if gate_result.get("requires_input"):
                    results["final_status"] = "waiting_for_input"
                    update_status(
                        session_dir,
                        f"gate_{stage['gate']}",
                        "waiting",
                        gate_result.get("notes", f"Gate {stage['gate']} waiting for agent decision"),
                    )
                    break
                if gate_result.get("verdict") == "request_changes":
                    update_status(
                        session_dir,
                        stage["name"],
                        "request_changes",
                        f"Gate {stage['gate']} requested changes",
                    )
                    # Re-run the current stage on the next continue/loop
                    should_break = self._retry_stage_execution(
                        stage,
                        manifest,
                        session_dir,
                        session_id,
                        config_overrides,
                        {
                            "stage": stage["name"],
                            "skill": stage.get("skill", "unknown"),
                            "success": False,
                            "output": None,
                            "error": gate_result.get(
                                "notes", f"Gate {stage['gate']} requested changes"
                            ),
                            "validation": {"valid": False, "errors": [], "artifact_results": {}},
                            "triage_decision": TriageDecision.RETRY,
                        },
                        results,
                    )
                    if should_break:
                        break
                    continue
                if gate_result["blocked"]:
                    results["final_status"] = "blocked"
                    update_status(
                        session_dir,
                        f"gate_{stage['gate']}",
                        "block",
                        gate_result.get("notes", f"Gate {stage['gate']} blocked"),
                    )
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

        Args:
            stage: Stage configuration from manifest
            manifest: Full manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills
            stage_result: Previous stage execution result
            results: Results dictionary to update in place

        Returns:
            True if the outer stage loop should break (retries exhausted)
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

            # Exponential backoff with jitter to avoid thundering herd
            # Base backoff: 2^retry_count seconds, plus random jitter up to 50%
            base_backoff = 2**retry_count
            jitter = random.uniform(0, 0.5 * base_backoff)
            backoff_seconds = base_backoff + jitter
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
        """
        Resolve max retry count for a stage from its configuration.

        Falls back to the default of 3 and clamps to a sane range.
        Invalid values are logged and treated as the default.

        Args:
            stage: Stage configuration from manifest

        Returns:
            Maximum number of retries for this stage
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

    def _execute_stage(
        self,
        stage: dict[str, Any],
        manifest: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None = None,
        correction_artifact: str | None = None,
        resume: bool = False,
        focused_context: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a single stage

        Args:
            stage: Stage configuration from manifest
            manifest: Full manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills
            correction_artifact: Optional path to correction artifact for retry loops
            resume: If True, skip stages already marked completed in session.json
            focused_context: Optional file paths to inject into the stage worker

        Returns:
            Dictionary with stage execution results
        """
        stage_name = stage["name"]
        skill_name = stage["skill"]

        # When resuming, check the session log before re-running a stage that has
        # already completed. Statuses like "request_changes" cause a re-run.
        if resume:
            try:
                session_data = json.loads(
                    (session_dir / "session.json").read_text(encoding="utf-8")
                )
                latest_status = None
                for entry in reversed(session_data.get("stages", [])):
                    if entry.get("stage") == stage_name:
                        latest_status = entry.get("status")
                        break
                if latest_status == "completed":
                    return {
                        "stage": stage_name,
                        "skill": skill_name,
                        "success": True,
                        "output": "Stage already completed (resumed)",
                        "error": None,
                        "validation": {
                            "valid": True,
                            "errors": [],
                            "artifact_results": {},
                        },
                        "triage_decision": TriageDecision.PROCEED,
                    }
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to read session.json for resume check: {e}")

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
                    focused_context,
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

        Args:
            pause_file: Path to the pause file
            stage_name: Name of the stage
            session_dir: Session directory
        """
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

    def _extract_user_input(self, content: str) -> str | None:
        """
        Extract user input from pause file content using structured parsing.

        Args:
            content: The pause file content

        Returns:
            Extracted user input, or None if no valid input found
        """
        import re

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
        except (InvalidInputError, ValueError) as e:
            logger.error(f"Validation error loading skill {skill_name}: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Validation error loading skill: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Validation error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
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
        except (RuntimeError, PathTraversalError) as e:
            logger.error(f"Error loading skill {skill_name}: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Error loading skill: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Error loading skill: {str(e)}"],
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
        focused_context: list[str] | None = None,
    ) -> tuple[SkillInvocationResult | None, dict[str, Any] | None]:
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
                focused_context=focused_context,
                timeout=self.config.get("dispatch_timeout_seconds"),
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
        except (InvalidInputError, ValueError) as e:
            logger.error(
                f"Validation error during skill invocation for {skill_name}: {e}"
            )
            self.metrics.record_skill_result(
                skill_name, False, f"Validation error: {str(e)}"
            )
            return None, {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Validation error during skill invocation: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Validation error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
        except OSError as e:
            logger.error(
                f"File system error during skill invocation for {skill_name}: {e}"
            )
            self.metrics.record_skill_result(
                skill_name, False, f"File system error: {str(e)}"
            )
            return None, {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"File system error during skill invocation: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"File system error: {str(e)}"],
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
        except (RuntimeError, PathTraversalError) as e:
            logger.error(
                f"Error during skill invocation for {skill_name}: {e}"
            )
            self.metrics.record_skill_result(
                skill_name, False, f"Error: {str(e)}"
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
    ) -> tuple[dict[str, Any], list[Path]]:
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
        except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
            logger.error(
                f"Error during validation for stage {stage_name}: {e}"
            )
            return (
                {
                    "valid": False,
                    "errors": [f"Validation error: {str(e)}"],
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
            except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
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

        Args:
            stage_name: Name of the stage being reviewed
            skill_name: Name of the skill that was invoked
            session_dir: Session directory
            session_id: Session identifier
            artifact_paths: List of artifact paths to review
            correction_artifact: Optional path to correction artifact

        Returns:
            Tuple of (verdict, confidence, review_output) where verdict is
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
            except (OSError, RuntimeError):
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

        # Parse the explicit overall assessment produced by swe-compliance.
        # The review narrative uses headings like "Overall Quality Assessment:
        # EXCELLENT/GOOD/ACCEPTABLE/POOR/BLOCKED" and lists "Critical Issues Found".
        review_lower = review_output.lower()

        assessment_match = re.search(
            r"overall quality assessment[:\s]+([a-z]+)", review_lower
        )
        critical_count = 0
        critical_match = re.search(
            r"critical issues? found[:\s]*(\d+)", review_lower
        )
        if critical_match:
            critical_count = int(critical_match.group(1))

        if assessment_match:
            assessment = assessment_match.group(1).strip().rstrip(".")
            if assessment in {"excellent", "good", "acceptable"}:
                verdict = "PASS"
                confidence = "HIGH" if assessment in {"excellent", "good"} else "MEDIUM"
            elif assessment in {"poor", "blocked", "fail"}:
                verdict = "FAIL"
                confidence = "LOW"
            else:
                verdict = "PASS"
                confidence = "MEDIUM"
        elif critical_count > 0 or any(
            word in review_lower
            for word in ["rejected", "block", "cannot proceed", "must fix"]
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
        self,
        gate_id: str,
        stage_name: str,
        session_dir: Path,
        manifest: dict[str, Any] | None = None,
        stage_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Handle a gate (human approval or auto-gate).

        Supports three interaction modes via ``config["gate_mode"]``:
        - ``interactive``: block and wait for a decision file edit (legacy CLI behaviour).
        - ``signal``: create the decision file and immediately return a signal
          to the calling agent without waiting.
        - ``auto``: evaluate bypass conditions and either auto-approve or signal
          the agent when human judgment is required.

        Args:
            gate_id: Gate identifier
            stage_name: Stage name for context
            session_dir: Session directory
            manifest: Workflow manifest containing gate definitions
            stage_result: Result of the stage that produced this gate

        Returns:
            Dictionary with gate handling results
        """
        update_status(
            session_dir,
            f"gate_{gate_id}",
            "waiting",
            f"Waiting for gate decision: {gate_id}",
        )

        # Create gate decision file for human/agent input
        error = self._create_gate_decision_file(gate_id, stage_name, session_dir)
        if error is not None:
            return error

        gate_decision_file = self._validate_artifact_path(
            f"gate-{gate_id}-decision.md", session_dir
        )

        gate_mode = self.config.get("gate_mode", GATE_MODE_INTERACTIVE)

        # Legacy interactive mode: block until the decision file is edited.
        if gate_mode == GATE_MODE_INTERACTIVE:
            try:
                return self._wait_and_parse_gate_decision(
                    gate_id, session_dir, gate_decision_file
                )
            except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                logger.error(f"Error during gate handling: {e}")
                update_status(
                    session_dir,
                    f"gate_{gate_id}",
                    "error",
                    f"Gate handling error: {str(e)}",
                )
                return {
                    "gate_id": gate_id,
                    "verdict": "block",
                    "blocked": True,
                    "error": f"Gate handling error: {str(e)}",
                }

        # Non-interactive modes: signal/auto. First, honour any pre-existing
        # decision that an agent may have already written.
        parsed = self._read_gate_decision(gate_decision_file)
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
                    logger.info(f"Gate {gate_id} decision recorded: {verdict}")
                except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                    logger.error(f"Error recording gate decision: {e}")
                    update_status(
                        session_dir,
                        f"gate_{gate_id}",
                        "error",
                        f"Failed to record gate decision: {str(e)}",
                    )
                    return {
                        "gate_id": gate_id,
                        "verdict": "block",
                        "blocked": True,
                        "error": f"Failed to record gate decision: {str(e)}",
                    }
                return {
                    "gate_id": gate_id,
                    "verdict": verdict,
                    "blocked": verdict == "block",
                    "notes": notes,
                }

        # ``signal`` mode always returns a request for input.
        if gate_mode == GATE_MODE_SIGNAL:
            return self._build_gate_signal(
                gate_id, stage_name, session_dir, gate_decision_file
            )

        # ``auto`` mode: decide whether to bypass or escalate.
        bypass = self._evaluate_gate_bypass_conditions(
            gate_id, stage_name, session_dir, gate_decision_file, manifest, stage_result
        )
        verdict = bypass["verdict"]
        conditions = bypass["conditions"]
        notes = "; ".join(
            c["reason"] for c in conditions if c["triggered"]
        ) or "No escalation triggers detected"

        if verdict == "approve":
            try:
                record_gate(gate_id, "approve", session_dir, notes)
                update_status(
                    session_dir,
                    f"gate_{gate_id}",
                    "approve",
                    f"Auto-approved gate {gate_id}: {notes}",
                )
                logger.info(f"Gate {gate_id} auto-approved")
            except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                logger.error(f"Error recording auto gate approval: {e}")
                return {
                    "gate_id": gate_id,
                    "verdict": "block",
                    "blocked": True,
                    "error": f"Failed to record gate approval: {str(e)}",
                }
            return {
                "gate_id": gate_id,
                "verdict": "approve",
                "blocked": False,
                "auto_approved": True,
                "conditions": conditions,
            }

        # request_changes or block: signal the calling agent.
        signal = self._build_gate_signal(
            gate_id, stage_name, session_dir, gate_decision_file, verdict, notes, conditions
        )
        return signal

    def _read_gate_decision(self, gate_decision_file: Path) -> tuple[str, str] | None:
        """Read a gate decision file once and return the parsed verdict if present."""
        try:
            content = gate_decision_file.read_text(encoding="utf-8")
        except (OSError, PermissionError):
            return None
        return self._parse_gate_verdict(content)

    def _build_gate_signal(
        self,
        gate_id: str,
        stage_name: str,
        session_dir: Path,
        gate_decision_file: Path,
        verdict: str = "block",
        notes: str = "",
        conditions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a non-blocking gate result for the calling agent."""
        instruction = (
            f"Gate '{gate_id}' for stage '{stage_name}' requires a decision. "
            f"Write a verdict to {gate_decision_file} using:\n\n"
            f"verdict: approve|request_changes|block\n"
            f"notes: [optional notes]\n\n"
            f"Then call continue_workflow with session_id {session_dir.name} to resume."
        )
        return {
            "gate_id": gate_id,
            "verdict": verdict,
            "blocked": False,
            "requires_input": True,
            "decision_file": str(gate_decision_file),
            "session_id": session_dir.name,
            "stage_name": stage_name,
            "notes": notes,
            "instruction": instruction,
            "conditions": conditions or [],
        }

    def _get_gate_config(
        self, gate_id: str, manifest: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Return gate configuration from the manifest, or an empty dict."""
        if not manifest:
            return {}
        for gate in manifest.get("gates", []):
            if gate.get("id") == gate_id:
                return gate
        return {}

    def _evaluate_gate_bypass_conditions(
        self,
        gate_id: str,
        _stage_name: str,
        _session_dir: Path,
        _gate_decision_file: Path,
        manifest: dict[str, Any] | None,
        stage_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Evaluate whether a gate can be automatically approved or must escalate.

        Returns a dict with:
            verdict: "approve" | "request_changes" | "block"
            conditions: list of condition dicts with name, triggered, verdict, reason
        """
        stage_result = stage_result or {}
        gate_config = self._get_gate_config(gate_id, manifest)
        output = (stage_result.get("output") or "").lower()

        # demo_mode is a simulation override: it short-circuits all other
        # bypass/escalation checks so automated tests and dry-runs do not
        # block on gates.
        if self.config.get("demo_mode"):
            return {
                "verdict": "approve",
                "conditions": [
                    {
                        "name": "demo_mode",
                        "triggered": True,
                        "verdict": "approve",
                        "reason": "demo_mode is enabled; auto-approving for simulation",
                    }
                ],
            }

        conditions: list[dict[str, Any]] = [
            {
                "name": "mandatory_gate",
                "triggered": bool(gate_config.get("mandatory")),
                "verdict": "block",
                "reason": "gate is marked mandatory and requires an explicit agent decision",
            },
            {
                "name": "stage_failure",
                "triggered": stage_result.get("success") is False,
                "verdict": "block",
                "reason": "preceding stage did not succeed",
            },
            {
                "name": "reviewer_rejected",
                "triggered": (
                    stage_result.get("reviewer_verdict") == "FAIL"
                    or stage_result.get("confidence") == "LOW"
                ),
                "verdict": "request_changes",
                "reason": "reviewer rejected the stage output or reported low confidence",
            },
            {
                "name": "critical_security_findings",
                "triggered": any(
                    keyword in output
                    for keyword in ["critical", "security", "unsafe", "block", "danger"]
                ),
                "verdict": "block",
                "reason": "stage output contains critical or security-related keywords",
            },
            {
                "name": "missing_or_empty_output",
                "triggered": not output.strip(),
                "verdict": "request_changes",
                "reason": "stage output is empty or missing",
            },
            {
                "name": "warnings_or_medium_confidence",
                "triggered": (
                    stage_result.get("confidence") == "MEDIUM"
                    or any(
                        keyword in output
                        for keyword in ["warning", "minor", "caveat", "suggestion"]
                    )
                ),
                "verdict": "request_changes",
                "reason": "stage output contains warnings or medium-confidence concerns",
            },
        ]

        # Determine the most severe verdict from triggered conditions.
        severity = {"approve": 0, "request_changes": 1, "block": 2}
        final_verdict = "approve"
        for condition in conditions:
            if condition["triggered"]:
                cond_verdict = condition["verdict"]
                if severity.get(cond_verdict, 0) > severity.get(final_verdict, 0):
                    final_verdict = cond_verdict

        # Config-driven bypass: auto-approve non-security gates when the
        # preceding stage succeeded and reported HIGH confidence.
        has_block = any(
            c["triggered"] and c["verdict"] == "block" for c in conditions
        )
        bypass_config = self.config.get("gate_bypass_conditions") or {}
        if (
            not has_block
            and bypass_config.get("confidence_high_non_security")
            and stage_result.get("confidence") == "HIGH"
            and stage_result.get("success") is not False
        ):
            final_verdict = "approve"
            conditions.append(
                {
                    "name": "confidence_high_non_security",
                    "triggered": True,
                    "verdict": "approve",
                    "reason": "stage succeeded with HIGH confidence and gate is non-security; config bypass auto-approves",
                }
            )

        return {"verdict": final_verdict, "conditions": conditions}

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
            if gate_decision_file.exists():
                return None
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
                    except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
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
        except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
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

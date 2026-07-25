#!/usr/bin/env python3
"""
Stateless Orchestrator - High-level stateless interface for orchestrator operations

Provides a simple, stateless interface for running workflows and skills without
requiring callers to manage session IDs, prompt files, or internal paths.
"""

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from config_loader import ConfigLoader
from deterministic_tools import WorkflowManifestError
from orchestration_engine import OrchestrationEngine
from prompt_builder import write_request_prompt
from security_utils import (
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_skill_name,
    validate_workflow_name,
)
from session_manager import create_session
from skill_invoker import SkillInvoker

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Serialize non-standard JSON types (Enum, Path) for workflow results."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class StatelessOrchestrator:
    """
    Stateless orchestrator for high-level workflow and skill execution.

    This class provides a simple interface that hides session management,
    prompt building, and internal path details from callers.
    """

    # Intent mappings based on use-cases.yaml
    INTENT_MAPPING = {
        "implement": {"workflow": "superpower", "skill": "subagent-driven-development"},
        "review": {"workflow": "code_review", "skill": "code-review"},
        "investigate": {"workflow": "rca", "skill": "systematic-debugging"},
        "plan": {"workflow": None, "skill": "writing-plans"},
    }

    def __init__(
        self,
        workspace: str | None = None,
        demo_mode: bool = False,
        timeout: int | None = None,
        gate_mode: str | None = None,
    ):
        """
        Initialize the stateless orchestrator.

        Args:
            workspace: Optional workspace path for config loading
            demo_mode: If True, skip real Devin dispatches and simulate outputs
            timeout: Optional per-dispatch timeout in seconds (defaults to config)
            gate_mode: Optional gate interaction mode (interactive|signal|auto);
                       defaults to the value in config.yaml
        """
        self.config = ConfigLoader.load(workspace=workspace)
        self.workspace = workspace
        self.demo_mode = demo_mode
        self.timeout = timeout
        self.gate_mode = gate_mode or getattr(self.config, "gate_mode", "auto")
        self._load_use_cases()

    def _load_use_cases(self) -> None:
        """Load use-cases.yaml to map intents to workflows/skills."""
        use_cases_file = self.config.workflows_dir / "use-cases.yaml"
        self.use_cases = {}

        if use_cases_file.exists():
            try:
                with open(use_cases_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for uc in data.get("use_cases", []):
                    uc_id = uc.get("id")
                    if uc_id:
                        self.use_cases[uc_id] = {
                            "workflow": uc.get("workflow"),
                            "session_id_format": uc.get("session_id_format"),
                        }
                logger.info(f"Loaded {len(self.use_cases)} use cases from {use_cases_file}")
            except (FileNotFoundError, yaml.YAMLError, ValueError, KeyError) as e:
                logger.warning(f"Failed to load use-cases.yaml: {e}")

    def _seed_focused_context(
        self, session_dir: Path, focused_context: list[str]
    ) -> list[str]:
        """
        Copy focused context files from the project workspace into the session
        directory and return their absolute paths inside the session.
        """
        if not self.workspace or not focused_context:
            return []

        workspace_path = Path(self.workspace).resolve()
        seeded: list[str] = []
        for raw_file in focused_context:
            raw = raw_file.strip()
            if not raw:
                continue
            try:
                source = validate_path_safe(
                    workspace_path, Path(raw), allow_absolute=True
                )
                if not source.is_file():
                    logger.warning(f"Focused context file not found: {source}")
                    continue
                relative = source.relative_to(workspace_path)
                dest = validate_path_safe(
                    session_dir, session_dir / relative, allow_absolute=True
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                seeded.append(str(dest))
                logger.info(f"Seeded focused context: {source} -> {dest}")
            except (InvalidInputError, PathTraversalError, OSError, ValueError) as e:
                logger.warning(f"Failed to seed focused context {raw}: {e}")
        return seeded

    def _resolve_plan_artifact(self, plan_artifact: str) -> Path | None:
        """Resolve a plan artifact path against the workspace or global root."""
        raw = plan_artifact.strip()
        if not raw:
            return None
        base = Path(self.workspace).resolve() if self.workspace else self.config.global_root
        try:
            source = validate_path_safe(base, Path(raw), allow_absolute=True)
            return source
        except (InvalidInputError, PathTraversalError, ValueError) as e:
            logger.warning(f"Plan artifact path {raw} is not under {base}: {e}")
            return None

    def _list_session_artifacts(self, session_dir: Path) -> list[str]:
        """List durable artifacts in the session directory, excluding temp files."""
        if not session_dir.exists():
            return []
        artifacts: list[str] = []
        for f in sorted(session_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("devin_prompt_"):
                artifacts.append(str(f))
        return artifacts

    def _seed_review_files(self, session_dir: Path, request: str) -> None:
        """
        Copy files listed in a review request (FILES_MODIFIED line) from the
        workspace into the session directory so subagents inspect HEAD content.
        """
        if not self.workspace:
            return

        match = re.search(r"FILES_MODIFIED:\s*(.+?)(?:\n|$)", request)
        if not match:
            return

        workspace_path = Path(self.workspace).resolve()
        for raw_file in match.group(1).split(","):
            relative = raw_file.strip()
            if not relative:
                continue
            try:
                source = validate_path_safe(
                    workspace_path, workspace_path / relative, allow_absolute=True
                )
                if not source.is_file():
                    continue
                dest = validate_path_safe(
                    session_dir, session_dir / source.name, allow_absolute=True
                )
                shutil.copy2(source, dest)
                logger.info(f"Seeded review file: {dest}")
            except (InvalidInputError, PathTraversalError, OSError) as e:
                logger.warning(f"Failed to seed {raw_file}: {e}")

    def execute(
        self,
        request: str,
        intent: str = "auto",
        focused_context: list[str] | None = None,
        output_file: str | None = None,
        ready_callback: Any | None = None,
        plan_artifact: str | None = None,
        skip_brainstorming: bool | None = None,
    ) -> dict[str, Any]:
        """
        Execute a request with automatic or explicit intent routing.

        Args:
            request: The user request to execute
            intent: The intent to use ("auto" for automatic routing, or one of
                   "implement", "review", "investigate", "plan")
            focused_context: Optional file paths to focus the worker
            output_file: Optional path for a final summary report

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, resume
        """
        if intent == "auto":
            # Simplified auto-routing: use keyword matching
            intent = StatelessOrchestrator._detect_intent(request)

        # Route to the appropriate method
        if intent == "implement":
            return self.implement(
                request,
                focused_context=focused_context,
                output_file=output_file,
                ready_callback=ready_callback,
                plan_artifact=plan_artifact,
                skip_brainstorming=skip_brainstorming,
            )
        elif intent == "review":
            return self.review(request, focused_context=focused_context, ready_callback=ready_callback)
        elif intent == "investigate":
            return self.investigate(request, focused_context=focused_context, ready_callback=ready_callback)
        elif intent == "plan":
            return self.plan(request, focused_context=focused_context, output_file=output_file, ready_callback=ready_callback)
        else:
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Unknown intent: {intent}",
                "artifact_paths": [],
                "resume": None,
            }

    @staticmethod
    def _detect_intent(request: str) -> str:
        """
        Detect intent from request using weighted keyword matching with word boundaries.

        This is a simplified fallback for auto-routing. A full implementation
        would use the using-devin-orchestrator skill for more sophisticated routing.

        The algorithm uses weighted keyword scoring for the four main intents:
        - implement: default fallback for implementation/coding tasks
        - review: code review, audit, verification tasks
        - investigate: debugging, RCA, incident investigation
        - plan: planning, design, architecture tasks

        Keywords are matched with word boundaries to avoid false positives.
        In case of ties, priorities are: review > investigate > plan > implement.

        Args:
            request: The user request

        Returns:
            Detected intent ("implement", "review", "investigate", or "plan")

        Examples:
            >>> StatelessOrchestrator._detect_intent("Review the authentication code")
            'review'
            >>> StatelessOrchestrator._detect_intent("Debug the login failure")
            'investigate'
            >>> StatelessOrchestrator._detect_intent("Plan the migration strategy")
            'plan'
            >>> StatelessOrchestrator._detect_intent("Add a new API endpoint")
            'implement'
        """
        request_lower = request.lower()

        # Keywords for each intent with word boundary matching
        # Higher-weight keywords are listed first for clarity
        review_keywords = [
            r"\breview\b", r"\baudit\b", r"\bcheck\b", r"\bverify\b",
            r"\bpr\b", r"\bpull request\b", r"\bcode review\b"
        ]
        investigate_keywords = [
            r"\bdebug\b", r"\binvestigate\b", r"\brca\b", r"\broot cause\b",
            r"\bincident\b", r"\berror\b", r"\bfailure\b", r"\bbug\b", r"\bfix\b"
        ]
        plan_keywords = [
            r"\bplan\b", r"\bdesign\b", r"\barchitecture\b", r"\bspec\b",
            r"\bproposal\b", r"\bdraft\b", r"\boutline\b"
        ]

        # Score each intent based on keyword matches
        scores = {
            "review": 0,
            "investigate": 0,
            "plan": 0,
        }

        # Score review intent
        for pattern in review_keywords:
            if re.search(pattern, request_lower):
                scores["review"] += 1

        # Score investigate intent
        for pattern in investigate_keywords:
            if re.search(pattern, request_lower):
                scores["investigate"] += 1

        # Score plan intent
        for pattern in plan_keywords:
            if re.search(pattern, request_lower):
                scores["plan"] += 1

        # Return intent with highest score, default to implement
        max_score = max(scores.values())
        if max_score == 0:
            return "implement"

        # Get intents with max score (handle ties)
        max_intents = [intent for intent, score in scores.items() if score == max_score]

        # If tie, prioritize review > investigate > plan
        if "review" in max_intents:
            return "review"
        if "investigate" in max_intents:
            return "investigate"
        if "plan" in max_intents:
            return "plan"

        return "implement"

    def implement(
        self,
        request: str,
        focused_context: list[str] | None = None,
        output_file: str | None = None,
        ready_callback: Any | None = None,
        plan_artifact: str | None = None,
        skip_brainstorming: bool | None = None,
    ) -> dict[str, Any]:
        """
        Execute an implementation request using the superpower workflow.

        Args:
            request: The implementation request
            focused_context: Optional file paths to focus each stage
            output_file: Optional path for final summary report
            plan_artifact: Optional path to a pre-existing plan file
            skip_brainstorming: If True, skip the brainstorming stage

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, resume
        """
        return self.run_workflow(
            "superpower",
            request,
            focused_context=focused_context,
            output_file=output_file,
            ready_callback=ready_callback,
            plan_artifact=plan_artifact,
            skip_brainstorming=skip_brainstorming,
        )

    def review(
        self,
        request: str,
        focused_context: list[str] | None = None,
        ready_callback: Any | None = None,
    ) -> dict[str, Any]:
        """
        Execute a review request using the code_review workflow.

        Args:
            request: The review request
            focused_context: Optional file paths to focus review stages

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, resume
        """
        return self.run_workflow("code_review", request, focused_context=focused_context, ready_callback=ready_callback)

    def investigate(
        self,
        request: str,
        focused_context: list[str] | None = None,
        ready_callback: Any | None = None,
    ) -> dict[str, Any]:
        """
        Execute an investigation request using the rca workflow.

        Args:
            request: The investigation request
            focused_context: Optional file paths to focus investigation stages

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, resume
        """
        return self.run_workflow("rca", request, focused_context=focused_context, ready_callback=ready_callback)

    def plan(
        self,
        request: str,
        focused_context: list[str] | None = None,
        output_file: str | None = None,
        ready_callback: Any | None = None,
    ) -> dict[str, Any]:
        """
        Execute a planning request using the writing-plans skill.

        Args:
            request: The planning request
            focused_context: Optional file paths to focus the planner
            output_file: Optional path for the plan report

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, output_file
        """
        return self.run_skill("writing-plans", request, focused_context=focused_context, output_file=output_file, ready_callback=ready_callback)

    def run_workflow(
        self,
        workflow_name: str,
        request: str,
        focused_context: list[str] | None = None,
        output_file: str | None = None,
        ready_callback: Any | None = None,
        plan_artifact: str | None = None,
        skip_brainstorming: bool | None = None,
    ) -> dict[str, Any]:
        """
        Run a specific workflow with a request.

        Args:
            workflow_name: Name of the workflow to run
            request: The user request
            focused_context: Optional list of file paths to inject into each stage
            output_file: Optional path (relative to session) for final summary report
            plan_artifact: Optional path to a pre-existing plan file (e.g., design.md)
            skip_brainstorming: If True, skip the brainstorming stage and use the
                plan_artifact or an existing design.md

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, resume
        """
        try:
            # Validate workflow name to prevent path traversal / manifest
            # injection from session directories. Even though the MCP layer
            # validates this too, run_workflow is a public method that can be
            # called directly, so we enforce containment here as well.
            workflow_name = validate_workflow_name(workflow_name)

            # Determine session format from use-cases
            session_format = "SESSION-NNN"  # Default format
            for _uc_id, uc_data in self.use_cases.items():
                if uc_data.get("workflow") == workflow_name:
                    session_format = uc_data.get("session_id_format", "SESSION-NNN")
                    break

            # Create session
            session_id, session_dir = create_session(self.config.session_work_dir, session_format)

            # Seed focused context files into the session directory
            if focused_context:
                self._seed_focused_context(session_dir, focused_context)

            # Write prompt file
            write_request_prompt(session_dir, request)

            # Seed session with the modified files under review so subagents
            # evaluate the HEAD version instead of stale base copies.
            self._seed_review_files(session_dir, request)

            # If a plan artifact is supplied, copy it into the session as design.md
            # and force the brainstorming stage to be skipped.
            if plan_artifact:
                try:
                    plan_path = self._resolve_plan_artifact(plan_artifact)
                    if plan_path and plan_path.is_file():
                        design_path = session_dir / "design.md"
                        design_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(plan_path, design_path)
                        skip_brainstorming = True
                        logger.info(f"Seeded plan artifact: {plan_path} -> {design_path}")
                except (InvalidInputError, PathTraversalError, OSError, ValueError) as e:
                    logger.warning(f"Failed to seed plan artifact {plan_artifact}: {e}")

            # Let the caller return as soon as the session is established.
            if ready_callback:
                ready_callback(session_id, session_dir)

            # Load workflow manifest. Resolve the manifest path against
            # workflows_dir and validate it stays safely under workflows_dir
            # so traversal-style names like "../work/SESSION-001/evil" cannot
            # escape to other directories. allow_absolute=True is required
            # because workflows_dir is itself absolute; containment is still
            # enforced via the relative_to check inside validate_path_safe.
            # This mirrors the pattern in McpServer._tool_get_workflow.
            manifest_path = validate_path_safe(
                self.config.workflows_dir,
                self.config.workflows_dir / f"{workflow_name}.manifest.yaml",
                allow_absolute=True,
            )
            if not manifest_path.exists():
                return {
                    "session_id": session_id,
                    "workspace": str(session_dir),
                    "success": False,
                    "output": None,
                    "error": f"Workflow manifest not found: {manifest_path}",
                }

            # Execute workflow
            dispatch_timeout = self.timeout or self.config.dispatch_timeout_seconds
            engine = OrchestrationEngine(
                work_dir=self.config.session_work_dir,
                config={
                    "demo_mode": self.demo_mode,
                    "dispatch_timeout_seconds": dispatch_timeout,
                    "gate_mode": self.gate_mode,
                    "workflows_dir": str(self.config.workflows_dir),
                },
            )
            results = engine.execute_workflow(
                manifest_path=manifest_path,
                session_id=session_id,
                request_content=request,
                focused_context=focused_context,
                output_file=output_file,
                skip_brainstorming=skip_brainstorming,
            )

            # Flatten engine results into a stateless response
            result = dict(results)
            result["session_id"] = session_id
            result["workspace"] = str(session_dir)
            result["success"] = results.get("final_status") == "completed"
            result["error"] = results.get("error") if results.get("final_status") != "completed" else None
            # The full engine result (including stages) is serialized into output.
            # Remove the raw stages list from the top-level dict so the MCP layer
            # can json.dumps the response without hitting TriageDecision enum objects.
            result.pop("stages", None)
            result["output"] = json.dumps(results, indent=2, default=_json_default)
            if "artifact_paths" not in result:
                result["artifact_paths"] = self._list_session_artifacts(session_dir)
            return result

        except (InvalidInputError, ValueError) as e:
            logger.error(f"Validation error running workflow {workflow_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Validation error: {str(e)}",
            }
        except OSError as e:
            logger.error(f"File system error running workflow {workflow_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"File system error: {str(e)}",
            }
        except PathTraversalError as e:
            logger.error(f"Path traversal error running workflow {workflow_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Path traversal error: {str(e)}",
            }
        except WorkflowManifestError as e:
            logger.error(f"Invalid workflow manifest {workflow_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Invalid workflow manifest: {str(e)}",
            }

    def continue_workflow(
        self,
        session_id: str,
        gate_verdict: str | None = None,
        gate_notes: str | None = None,
        gate_id: str | None = None,
        correction_artifact: str | None = None,
        feedback: str | None = None,
        focused_context: list[str] | None = None,
        output_file: str | None = None,
        ready_callback: Any | None = None,
    ) -> dict[str, Any]:
        """
        Resume a workflow that is paused at a gate or escalated.

        Args:
            session_id: Existing session identifier
            gate_verdict: Optional verdict to write before resuming
            gate_notes: Optional notes for the gate decision
            gate_id: Optional explicit gate id
            correction_artifact: Optional correction artifact path
            feedback: Optional inline feedback text
            focused_context: Optional additional focused context
            output_file: Optional path for final summary report

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, resume
        """
        session_dir = self.config.session_work_dir / session_id

        has_resume_input = bool(
            gate_verdict or gate_notes or gate_id or correction_artifact or feedback
        )

        try:
            session_path = session_dir / "session.json"
            session_data: dict[str, Any] = {}
            if session_path.exists():
                session_data = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read session state for {session_id}: {e}")
            session_data = {}

        status = session_data.get("status") or session_data.get("final_status") or "unknown"
        artifact_paths = self._list_session_artifacts(session_dir)

        if not has_resume_input and status != "completed":
            # Nothing new to act on. Return the resume ticket immediately so a
            # stateless agent does not block on the same failing stage.
            resume = self._build_resume_from_session(
                session_id, session_data, artifact_paths
            )
            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": False,
                "output": None,
                "error": f"Session {session_id} is {status}. No new feedback/correction/verdict provided; not re-running.",
                "artifact_paths": artifact_paths,
                "resume": resume,
                "done": False,
                "next_step": resume.get("tool") if resume else None,
            }

        # Notify the caller that the session is established so it can return
        # while the engine runs in the background.
        if ready_callback:
            ready_callback(session_id, session_dir)

        try:
            engine = OrchestrationEngine(
                work_dir=self.config.session_work_dir,
                config={
                    "demo_mode": self.demo_mode,
                    "dispatch_timeout_seconds": self.timeout or self.config.dispatch_timeout_seconds,
                    "gate_mode": self.gate_mode,
                    "workflows_dir": str(self.config.workflows_dir),
                },
            )
            results = engine.continue_workflow(
                session_id=session_id,
                gate_verdict=gate_verdict,
                gate_notes=gate_notes,
                gate_id=gate_id,
                correction_artifact=correction_artifact,
                feedback=feedback,
                focused_context=focused_context,
                output_file=output_file,
            )
            result = dict(results)
            result["session_id"] = session_id
            result["workspace"] = str(session_dir)
            result["success"] = results.get("final_status") == "completed"
            result["error"] = results.get("error") if results.get("final_status") != "completed" else None
            # The full engine result (including stages) is serialized into output.
            # Remove the raw stages list from the top-level dict so the MCP layer
            # can json.dumps the response without hitting TriageDecision enum objects.
            result.pop("stages", None)
            result["output"] = json.dumps(results, indent=2, default=_json_default)
            if "artifact_paths" not in result:
                result["artifact_paths"] = artifact_paths
            result["done"] = results.get("final_status") == "completed"
            result["next_step"] = self._next_step_from_results(results)
            return result
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            logger.error(f"Failed to continue workflow {session_id}: {e}")
            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": False,
                "output": None,
                "error": f"Failed to continue workflow: {str(e)}",
                "done": False,
                "next_step": None,
            }

    def _build_resume_from_session(
        self,
        session_id: str,
        session_data: dict[str, Any],
        artifact_paths: list[str],
    ) -> dict[str, Any]:
        """Build a lightweight resume ticket directly from a session.json snapshot."""
        status = session_data.get("status") or session_data.get("final_status") or "unknown"
        stages = session_data.get("stages", [])
        current_stage = None
        if stages:
            current_stage = stages[-1].get("stage")

        waiting_gate = None
        if status == "waiting_for_input" and stages:
            for entry in reversed(stages):
                stage = entry.get("stage", "")
                if stage.startswith("gate_"):
                    waiting_gate = stage
                    current_stage = stage
                    break

        last_artifact = artifact_paths[-1] if artifact_paths else None

        if status == "waiting_for_input" and waiting_gate:
            return {
                "tool": "mcp0_gate_decision",
                "arguments": {
                    "session_id": session_id,
                    "gate_id": waiting_gate.replace("gate_", "", 1),
                    "verdict": "approve|request_changes|block",
                    "notes": "",
                },
                "then": {
                    "tool": "mcp0_continue_workflow",
                    "arguments": {"session_id": session_id},
                },
            }

        resume: dict[str, Any] = {
            "tool": "mcp0_continue_workflow",
            "arguments": {"session_id": session_id},
        }
        if status in ("escalated", "blocked", "retrying") and current_stage:
            resume["arguments"]["feedback"] = (
                f"<Provide correction/feedback for the '{current_stage}' stage>"
            )
        if last_artifact:
            resume["arguments"]["correction_artifact"] = last_artifact
        return resume

    def _next_step_from_results(self, results: dict[str, Any]) -> str | dict[str, Any] | None:
        """Return a concise next action from engine results."""
        if results.get("final_status") == "completed":
            return None
        resume = results.get("resume")
        if resume:
            return resume.get("tool")
        return "mcp0_continue_workflow"

    def get_session_status(self, session_id: str) -> dict[str, Any]:
        """Return a concise status summary for a session."""
        session_dir = self.config.session_work_dir / session_id
        try:
            session_path = session_dir / "session.json"
            session_data = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "session_id": session_id,
                "exists": False,
                "status": "unknown",
            }

        stages = session_data.get("stages", [])
        last_stage = stages[-1] if stages else {}
        return {
            "session_id": session_id,
            "exists": True,
            "workspace": str(session_dir),
            "status": session_data.get("status") or session_data.get("final_status") or "unknown",
            "manifest": session_data.get("manifest"),
            "current_stage": last_stage.get("stage"),
            "stage_status": last_stage.get("status"),
            "artifact_paths": self._list_session_artifacts(session_dir),
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions in the work directory with their current status."""
        sessions: list[dict[str, Any]] = []
        work_dir = self.config.session_work_dir
        if not work_dir.exists():
            return sessions

        for path in sorted(work_dir.iterdir()):
            if not path.is_dir():
                continue
            if not (path / "session.json").exists():
                continue
            status = self.get_session_status(path.name)
            sessions.append(status)

        return sessions

    def cancel_workflow(self, session_id: str) -> dict[str, Any]:
        """Mark a session as cancelled, signal any running Devin subprocess to stop, and return status."""
        session_dir = self.config.session_work_dir / session_id
        session_path = session_dir / "session.json"
        try:
            if not session_path.exists():
                return {
                    "session_id": session_id,
                    "success": False,
                    "error": f"Session {session_id} not found",
                }
            session_data = json.loads(session_path.read_text(encoding="utf-8"))
            existing_status = session_data.get("final_status") or session_data.get("status")
            if existing_status == "completed":
                return {
                    "session_id": session_id,
                    "success": False,
                    "error": f"Session {session_id} is already completed",
                }

            session_data["status"] = "cancelled"
            session_data["final_status"] = "cancelled"
            session_path.write_text(json.dumps(session_data, indent=2), encoding="utf-8")

            # Signal any active Popen dispatch to stop polling and terminate.
            cancel_token = session_dir / ".cancel"
            try:
                cancel_token.write_text("", encoding="utf-8")
            except OSError as e:
                logger.warning(f"Failed to write cancel token for {session_id}: {e}")

            # Best-effort kill of the recorded PIDs (devin subprocess and the
            # background workflow dispatcher). Verify process identity before
            # killing to avoid terminating an unrelated process that has reused
            # a recorded PID.
            any_failed = False
            any_killed = False
            for pid_name in ("pid.txt", "workflow-pid.txt"):
                pid_file = session_dir / pid_name
                if not pid_file.exists():
                    continue
                try:
                    pid, _, _ = self._read_pid_file(pid_file)
                    if pid is None:
                        continue
                    terminated = self._kill_process(pid)
                    if terminated:
                        any_killed = True
                    else:
                        any_failed = True
                except (OSError, ValueError) as e:
                    logger.warning(f"Failed to read/terminate {pid_name} for {session_id}: {e}")

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": True,
                "status": "cancelled",
                "process_terminated": not any_failed,
            }
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to cancel session {session_id}: {e}")
            return {
                "session_id": session_id,
                "success": False,
                "error": f"Failed to cancel session: {e}",
            }

    def _read_pid_file(
        self, pid_file: Path
    ) -> tuple[int | None, float | None, str | None]:
        """Read a PID file.

        Supports legacy files containing a plain PID integer and JSON files
        written by the orchestrator that include a creation timestamp.
        """
        try:
            text = pid_file.read_text(encoding="utf-8").strip()
        except OSError:
            return (None, None, None)
        if not text:
            return (None, None, None)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                pid = int(data["pid"])
                create_time = (
                    float(data["create_time"]) if "create_time" in data else None
                )
                return (pid, create_time, None)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
        try:
            return (int(text), None, None)
        except (ValueError, TypeError):
            return (None, None, text)

    def _get_process_commandline(
        self, pid: int
    ) -> tuple[list[str] | None, str | None]:
        """Return argv list and command-line string for a process, or (None,None) if gone."""
        if pid <= 0:
            return (None, None)
        if os.name == "nt":
            # PowerShell's CIM provider is available on modern Windows and
            # returns the full command line. WMIC is deprecated and often absent;
            # tasklist only returns the image name, which is not enough to verify
            # that the PID still belongs to our dispatcher.
            for cmd, is_cmdline in (
                (
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f"(Get-CimInstance -ClassName Win32_Process -Filter 'ProcessId={pid}' -Property CommandLine | Select-Object -ExpandProperty CommandLine).Trim()",
                    ],
                    True,
                ),
                (
                    [
                        "wmic",
                        "process",
                        "where",
                        f"ProcessId={pid}",
                        "get",
                        "CommandLine",
                        "/value",
                    ],
                    True,
                ),
                # Last resort: confirm the process exists, but we cannot safely
                # identify it.  Caller will treat (None, None) as "gone".
                (["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], False),
            ):
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        errors="replace",
                        timeout=3,
                        check=False,
                    )
                    output = result.stdout.strip()
                    if not output:
                        continue
                    if cmd[1] == "-NoProfile":  # PowerShell
                        if output:
                            return (output.split(), output)
                        continue
                    if cmd[0] == "wmic":
                        for line in output.splitlines():
                            if line.startswith("CommandLine="):
                                val = line[len("CommandLine="):].strip()
                                if val:
                                    return (val.split(), val)
                        continue
                    # tasklist: only proves existence.
                    parts = output.split(",")
                    if len(parts) >= 1:
                        return (None, None)
                except (OSError, subprocess.TimeoutExpired):
                    continue
        else:
            try:
                proc_dir = Path(f"/proc/{pid}")
                if not proc_dir.exists():
                    return (None, None)
                cmdline_text = (proc_dir / "cmdline").read_text(
                    encoding="utf-8", errors="replace"
                )
                parts = cmdline_text.split("\x00")
                if parts and parts[-1] == "":
                    parts = parts[:-1]
                if parts:
                    return (parts, " ".join(parts))
            except (OSError, ValueError):
                pass
        return (None, None)

    def _verify_process_identity(self, pid: int) -> tuple[bool, bool]:
        """Return (exists, belongs_to_orchestrator) for the given PID."""
        if pid <= 0 or pid == os.getpid():
            return (False, False)
        argv, cmdstr = self._get_process_commandline(pid)
        if argv is None:
            return (False, False)
        markers = (
            "devin",
            "dispatch_workflow",
            "dispatch_devin",
            "devin-orchestrator",
            "mcp_server.py",
        )
        check = cmdstr or " ".join(argv)
        return (True, any(marker in check for marker in markers))

    def _kill_process(self, pid: int) -> bool:
        """Best-effort cross-platform kill of a process by PID."""
        exists, ours = self._verify_process_identity(pid)
        if not exists:
            # Already gone; treat as success.
            return True
        if not ours:
            logger.warning(
                f"PID {pid} does not appear to be an orchestrator process; skipping kill"
            )
            return False
        try:
            if os.name == "nt":
                # Windows: taskkill /F /T forcibly terminates the process tree.
                result = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    check=False,
                    timeout=10,
                )
                return result.returncode == 0
            # Unix-like: SIGTERM with grace period, then SIGKILL.
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            # SIGKILL is not defined on Windows; fall back to SIGTERM if needed.
            sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
            os.kill(pid, sigkill)
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"taskkill timed out for PID {pid}")
            return False
        except (OSError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to kill process {pid}: {e}")
            return False

    def run_skill(
        self,
        skill_name: str,
        request: str,
        focused_context: list[str] | None = None,
        output_file: str | None = None,
        ready_callback: Any | None = None,
    ) -> dict[str, Any]:
        """
        Run a specific skill with a request.

        Args:
            skill_name: Name of the skill to run
            request: The user request
            focused_context: Optional list of file paths to copy into the session
            output_file: Optional path (relative to session) where the worker report is written

        Returns:
            Dictionary with session_id, workspace, success, output, error, artifact_paths, output_file
        """
        try:
            # Validate skill name to prevent path traversal. Even though the MCP
            # layer and SkillInvoker validate this too, run_skill is a public
            # method that can be called directly, so we enforce containment here
            # as well for defense in depth.
            skill_name = validate_skill_name(skill_name)

            # Create session with default format
            session_format = "SKILL-NNN"
            session_id, session_dir = create_session(self.config.session_work_dir, session_format)

            # Let the caller return as soon as the session is established.
            if ready_callback:
                ready_callback(session_id, session_dir)

            # Seed focused context files into the session directory so the worker
            # can access them without escaping the session sandbox.
            seeded_context = self._seed_focused_context(session_dir, focused_context or [])

            # Write request prompt file
            write_request_prompt(session_dir, request)

            # Record the start of this skill session so get_session_status can
            # report progress while the skill runs.
            try:
                (session_dir / "session.json").write_text(
                    json.dumps(
                        {
                            "session_id": session_id,
                            "workspace": str(session_dir),
                            "status": "in_progress",
                            "final_status": "in_progress",
                            "manifest": skill_name,
                            "request_content": request,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as e:
                logger.warning(f"Failed to seed session.json for skill {skill_name}: {e}")

            # Invoke skill. Pass the request in context so SkillInvoker builds
            # the full skill prompt (name, iron law, checklist, narrative).
            # Do NOT override with custom_prompt=request; that strips the skill
            # definition and produced broad, shallow passes.
            dispatch_timeout = self.timeout or self.config.dispatch_timeout_seconds
            invoker = SkillInvoker(demo_mode=self.demo_mode)
            context = {
                "session_id": session_id,
                "request": request,
            }

            result = invoker.invoke_skill(
                skill_name=skill_name,
                context=context,
                workspace=str(session_dir),
                focused_context=seeded_context,
                timeout=dispatch_timeout,
            )

            # Write output report if requested
            written_output_file: str | None = None
            if output_file:
                try:
                    out_path = validate_path_safe(session_dir, session_dir / output_file, allow_absolute=True)
                    out_path.write_text(result.output or "", encoding="utf-8")
                    written_output_file = str(out_path)
                except (InvalidInputError, PathTraversalError, OSError) as e:
                    logger.warning(f"Failed to write output_file {output_file}: {e}")

            artifact_paths = self._list_session_artifacts(session_dir)

            # Persist final skill result for get_session_status polling.
            try:
                session_file = session_dir / "session.json"
                session_data: dict[str, Any] = {}
                if session_file.exists():
                    session_data = json.loads(session_file.read_text(encoding="utf-8"))
                session_data.update(
                    {
                        "session_id": session_id,
                        "workspace": str(session_dir),
                        "status": "completed" if result.success else "failed",
                        "final_status": "completed" if result.success else "failed",
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                        "output_file": written_output_file,
                        "artifact_paths": artifact_paths,
                        "done": True,
                        "next_step": None,
                    }
                )
                session_file.write_text(json.dumps(session_data, indent=2, default=str), encoding="utf-8")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to update session.json for skill {skill_name}: {e}")

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "output_file": written_output_file,
                "artifact_paths": artifact_paths,
            }

        except (InvalidInputError, ValueError) as e:
            logger.error(f"Validation error running skill {skill_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Validation error: {str(e)}",
            }
        except OSError as e:
            logger.error(f"File system error running skill {skill_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"File system error: {str(e)}",
            }
        except PathTraversalError as e:
            logger.error(f"Path traversal error running skill {skill_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Path traversal error: {str(e)}",
            }

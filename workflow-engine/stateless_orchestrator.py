#!/usr/bin/env python3
"""
Stateless Orchestrator - High-level stateless interface for orchestrator operations

Provides a simple, stateless interface for running workflows and skills without
requiring callers to manage session IDs, prompt files, or internal paths.
"""

import json
import logging
import re
import shutil
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

    def execute(self, request: str, intent: str = "auto") -> dict[str, Any]:
        """
        Execute a request with automatic or explicit intent routing.

        Args:
            request: The user request to execute
            intent: The intent to use ("auto" for automatic routing, or one of
                   "implement", "review", "investigate", "plan")

        Returns:
            Dictionary with session_id, workspace, success, output, error
        """
        if intent == "auto":
            # Simplified auto-routing: use keyword matching
            intent = StatelessOrchestrator._detect_intent(request)

        # Route to the appropriate method
        if intent == "implement":
            return self.implement(request)
        elif intent == "review":
            return self.review(request)
        elif intent == "investigate":
            return self.investigate(request)
        elif intent == "plan":
            return self.plan(request)
        else:
            return {
                "session_id": None,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Unknown intent: {intent}",
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

    def implement(self, request: str) -> dict[str, Any]:
        """
        Execute an implementation request using the superpower workflow.

        Args:
            request: The implementation request

        Returns:
            Dictionary with session_id, workspace, success, output, error
        """
        return self.run_workflow("superpower", request)

    def review(self, request: str) -> dict[str, Any]:
        """
        Execute a review request using the code_review workflow.

        Args:
            request: The review request

        Returns:
            Dictionary with session_id, workspace, success, output, error
        """
        return self.run_workflow("code_review", request)

    def investigate(self, request: str) -> dict[str, Any]:
        """
        Execute an investigation request using the rca workflow.

        Args:
            request: The investigation request

        Returns:
            Dictionary with session_id, workspace, success, output, error
        """
        return self.run_workflow("rca", request)

    def plan(self, request: str) -> dict[str, Any]:
        """
        Execute a planning request using the writing-plans skill.

        Args:
            request: The planning request

        Returns:
            Dictionary with session_id, workspace, success, output, error
        """
        return self.run_skill("writing-plans", request)

    def run_workflow(self, workflow_name: str, request: str) -> dict[str, Any]:
        """
        Run a specific workflow with a request.

        Args:
            workflow_name: Name of the workflow to run
            request: The user request

        Returns:
            Dictionary with session_id, workspace, success, output, error
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

            # Write prompt file
            write_request_prompt(session_dir, request)

            # Seed session with the modified files under review so subagents
            # evaluate the HEAD version instead of stale base copies.
            self._seed_review_files(session_dir, request)

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
            )

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": results.get("final_status") == "completed",
                "output": json.dumps(results, indent=2, default=_json_default),
                "error": results.get("error") if results.get("final_status") != "completed" else None,
            }

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
    ) -> dict[str, Any]:
        """
        Resume a workflow that is paused at a gate.

        Args:
            session_id: Existing session identifier
            gate_verdict: Optional verdict to write before resuming
            gate_notes: Optional notes for the gate decision
            gate_id: Optional explicit gate id

        Returns:
            Dictionary with session_id, workspace, success, output, error
        """
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
            )
            session_dir = self.config.session_work_dir / session_id
            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": results.get("final_status") == "completed",
                "output": json.dumps(results, indent=2, default=_json_default),
                "error": results.get("error") if results.get("final_status") != "completed" else None,
            }
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            logger.error(f"Failed to continue workflow {session_id}: {e}")
            return {
                "session_id": session_id,
                "workspace": None,
                "success": False,
                "output": None,
                "error": f"Failed to continue workflow: {str(e)}",
            }

    def run_skill(self, skill_name: str, request: str) -> dict[str, Any]:
        """
        Run a specific skill with a request.

        Args:
            skill_name: Name of the skill to run
            request: The user request

        Returns:
            Dictionary with session_id, workspace, success, output, error
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

            # Write prompt file
            write_request_prompt(session_dir, request)

            # Invoke skill
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
                custom_prompt=request,
                timeout=dispatch_timeout,
            )

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "success": result.success,
                "output": result.output,
                "error": result.error,
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

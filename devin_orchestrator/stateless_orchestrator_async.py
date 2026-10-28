#!/usr/bin/env python3
# mypy: disable-error-code="attr-defined"
"""Asynchronous workflow and skill dispatch for the StatelessOrchestrator."""

from __future__ import annotations

import json
import logging
import re
import threading
import traceback
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from devin_orchestrator.deterministic_tools import session_init
from devin_orchestrator.prompt_builder import write_request_prompt
from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_session_id,
    validate_skill_name,
    validate_workflow_name,
)
from devin_orchestrator.session_manager import create_session, resolve_session
from devin_orchestrator.skill_invoker import SkillInvoker
from devin_orchestrator.stateless_orchestrator import (
    _clear_session_event,
    _get_session_event,
    _register_thread,
    _set_session_event,
    _tracked_target,
)

logger = logging.getLogger(__name__)


class StatelessAsyncMixin:
    """Mixin providing background async workflow/skill dispatch."""

    @staticmethod
    def _detect_intent(request: str) -> str:
        """
        Detect intent from request using weighted keyword matching with word boundaries.

        This is a simplified fallback for auto-routing when the caller does not
        specify a use case explicitly.

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
            r"\breview\b",
            r"\baudit\b",
            r"\bcheck\b",
            r"\bverify\b",
            r"\bpr\b",
            r"\bpull request\b",
            r"\bcode review\b",
        ]
        investigate_keywords = [
            r"\bdebug\b",
            r"\binvestigate\b",
            r"\brca\b",
            r"\broot cause\b",
            r"\bincident\b",
            r"\berror\b",
            r"\bfailure\b",
            r"\bbug\b",
            r"\bfix\b",
        ]
        plan_keywords = [
            r"\bplan\b",
            r"\bdesign\b",
            r"\barchitecture\b",
            r"\bspec\b",
            r"\bproposal\b",
            r"\bdraft\b",
            r"\boutline\b",
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

    def _prepare_workflow(
        self, workflow_name: str, request: str
    ) -> tuple[str, Path, Path] | dict[str, Any]:
        """
        Prepare a workflow session and manifest.

        Returns (session_id, session_dir, manifest_path) on success, or an error
        dict on failure.
        """
        workflow_name = validate_workflow_name(workflow_name)
        session_format = self._session_format_for_workflow(workflow_name)
        session_id, session_dir = create_session(
            self.config.session_work_dir, session_format
        )

        # Scaffold session.json with the request and required top-level keys.
        session_init(session_id, self.config.session_work_dir, request)
        write_request_prompt(session_dir, request)
        self._seed_review_files(session_dir, request)

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
        return session_id, session_dir, manifest_path

    def _is_session_cancelled(self, session_dir: Path) -> bool:
        """Check session.json for a cancelling/cancelled status."""
        session_file = session_dir / "session.json"
        try:
            if session_file.exists():
                data = json.loads(session_file.read_text(encoding="utf-8"))
                return data.get("status") in ("cancelling", "cancelled")
        except (OSError, json.JSONDecodeError):
            pass
        return False

    def _check_cancelled_before_start(self, session_id: str, session_dir: Path) -> bool:
        """Return True if the session was cancelled before it began work."""
        event = _get_session_event(session_id)
        if event is not None and event.is_set():
            return True
        return self._is_session_cancelled(session_dir)

    def _finish_if_cancelled(
        self, session_id: str, session_dir: Path, cancelled_result: dict[str, Any]
    ) -> bool:
        """Write cancelled result + status when the session was cancelled."""
        if not self._check_cancelled_before_start(session_id, session_dir):
            return False
        self._write_result_file(session_dir, cancelled_result)
        self._update_session_status(session_dir, "cancelled")
        return True

    def _run_workflow_thread(
        self,
        session_id: str,
        session_dir: Path,
        request: str,
        manifest_path: Path,
    ) -> None:
        """Background thread body for execute_workflow."""
        try:
            if self._finish_if_cancelled(
                session_id,
                session_dir,
                {"session_id": session_id, "final_status": "cancelled", "stages": []},
            ):
                return
            engine = self._make_engine()
            results = engine.execute_workflow(
                manifest_path=manifest_path,
                session_id=session_id,
                request_content=request,
            )
            self._write_result_file(session_dir, results)
        except Exception as e:
            logger.error(
                f"Background workflow {session_id} failed: {e}\n{traceback.format_exc()}"
            )
            self._write_result_file(
                session_dir,
                {
                    "session_id": session_id,
                    "final_status": "failed",
                    "error": f"Background dispatch failed: {str(e)}",
                    "stages": [],
                },
            )
        finally:
            _clear_session_event(session_id)

    def run_workflow_async(self, workflow_name: str, request: str) -> dict[str, Any]:
        """
        Start a workflow in a background thread and return the session_id.

        The caller can poll ``get_workflow_status`` or use the MCP
        ``query_workflow_status`` tool until ``result.json`` is written.
        """
        try:
            prepared = self._prepare_workflow(workflow_name, request)
            if isinstance(prepared, dict):
                return prepared
            session_id, session_dir, manifest_path = prepared
            _set_session_event(session_id)

            self._update_session_status(session_dir, "running")
            thread = threading.Thread(
                target=_tracked_target,
                args=(
                    self._run_workflow_thread,
                    (session_id, session_dir, request, manifest_path),
                ),
                daemon=True,
            )
            _register_thread(thread)
            thread.start()

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "status": "started",
            }
        except (InvalidInputError, ValueError, OSError, PathTraversalError) as e:
            logger.error(f"Failed to start workflow {workflow_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "status": "failed",
                "error": str(e),
            }

    def implement_async(self, request: str) -> dict[str, Any]:
        """Dispatch a single coder-role Devin run in the background.

        The gated pipeline was removed; implement is now a focused staff run
        equivalent to ``dispatch_devin --role coder`` — one worker, one prompt.
        """
        try:
            session_id, session_dir = create_session(
                self.config.session_work_dir, "IMPLEMENT-NNN"
            )
            _set_session_event(session_id)
            session_init(session_id, self.config.session_work_dir, request)
            self._update_session_status(session_dir, "running")
            thread = threading.Thread(
                target=_tracked_target,
                args=(self._run_implement_thread, (session_id, session_dir, request)),
                daemon=True,
            )
            _register_thread(thread)
            thread.start()
            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "status": "started",
            }
        except (InvalidInputError, ValueError, OSError, PathTraversalError) as e:
            logger.error(f"Failed to start implement dispatch: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "status": "failed",
                "error": str(e),
            }

    def _run_implement_thread(
        self, session_id: str, session_dir: Path, request: str
    ) -> None:
        """Background thread: one coder-role dispatch, no pipeline."""
        try:
            if self._finish_if_cancelled(
                session_id,
                session_dir,
                {
                    "session_id": session_id,
                    "success": False,
                    "error": "Session cancelled",
                },
            ):
                return
            if self.demo_mode:
                result = SimpleNamespace(
                    success=True, output="Simulated output (demo mode)", error=None
                )
            else:
                from devin_orchestrator.devin_cli_adapter import DevinCliAdapter
                from devin_orchestrator.dispatch_devin import build_prompt
                from devin_orchestrator.model_resolver import resolve_model

                prompt_file = write_request_prompt(session_dir, request, role="coder")
                prompt = build_prompt(
                    self.config.global_root / "roles" / "coder.md", prompt_file
                )
                result = DevinCliAdapter(
                    devin_cli_path=self.config.devin_cli_path,
                    workspace=str(session_dir),
                    model=resolve_model("coder", None, self.config),
                    permission_mode=self.config.default_permission_mode,
                ).invoke(
                    prompt,
                    timeout=self.timeout or self.config.dispatch_timeout_seconds,
                )
            self._write_result_file(
                session_dir,
                {
                    "session_id": session_id,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                },
            )
            self._update_session_status(
                session_dir, "completed" if result.success else "failed"
            )
        except Exception as e:
            logger.error(
                f"Implement dispatch {session_id} failed: {e}\n{traceback.format_exc()}"
            )
            self._write_result_file(
                session_dir,
                {
                    "session_id": session_id,
                    "success": False,
                    "output": None,
                    "error": f"Dispatch failed: {e}",
                },
            )
            self._update_session_status(session_dir, "failed")
        finally:
            _clear_session_event(session_id)

    def review_async(self, request: str) -> dict[str, Any]:
        """Start the code_review workflow in the background."""
        return self.run_workflow_async("code_review", request)

    def investigate_async(self, request: str) -> dict[str, Any]:
        """Start the rca workflow in the background."""
        return self.run_workflow_async("rca", request)

    def _continue_workflow_thread(
        self,
        session_id: str,
        session_dir: Path,
        gate_verdict: str | None,
        gate_notes: str | None,
        gate_id: str | None,
    ) -> None:
        """Background thread body for continue_workflow."""
        try:
            if self._finish_if_cancelled(
                session_id,
                session_dir,
                {"session_id": session_id, "final_status": "cancelled", "stages": []},
            ):
                return
            engine = self._make_engine()
            results = engine.continue_workflow(
                session_id=session_id,
                gate_verdict=gate_verdict,
                gate_notes=gate_notes,
                gate_id=gate_id,
            )
            self._write_result_file(session_dir, results)
        except Exception as e:
            logger.error(
                f"Background continue {session_id} failed: {e}\n{traceback.format_exc()}"
            )
            self._write_result_file(
                session_dir,
                {
                    "session_id": session_id,
                    "final_status": "failed",
                    "error": f"Background continue failed: {str(e)}",
                    "stages": [],
                },
            )
        finally:
            _clear_session_event(session_id)

    def continue_workflow_async(
        self,
        session_id: str,
        gate_verdict: str | None = None,
        gate_notes: str | None = None,
        gate_id: str | None = None,
    ) -> dict[str, Any]:
        """Resume a workflow in a background thread and return immediately."""

        try:
            session_id = validate_session_id(session_id)
            session_dir = resolve_session(self.config.session_work_dir, session_id)
            _set_session_event(session_id)
            self._update_session_status(session_dir, "running")
            thread = threading.Thread(
                target=_tracked_target,
                args=(
                    self._continue_workflow_thread,
                    (session_id, session_dir, gate_verdict, gate_notes, gate_id),
                ),
                daemon=True,
            )
            _register_thread(thread)
            thread.start()

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "status": "started",
            }
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            logger.error(f"Failed to continue workflow {session_id}: {e}")
            return {
                "session_id": session_id,
                "workspace": None,
                "status": "failed",
                "error": f"Failed to continue workflow: {str(e)}",
            }

    def _run_skill_thread(
        self,
        session_id: str,
        session_dir: Path,
        skill_name: str,
        request: str,
    ) -> None:
        """Background thread body for run_skill."""
        try:
            if self._finish_if_cancelled(
                session_id,
                session_dir,
                {
                    "session_id": session_id,
                    "success": False,
                    "error": "Session cancelled",
                },
            ):
                return
            dispatch_timeout = self.timeout or self.config.dispatch_timeout_seconds
            invoker = SkillInvoker(demo_mode=self.demo_mode)
            context = {"session_id": session_id, "request": request}
            result = invoker.invoke_skill(
                skill_name=skill_name,
                context=context,
                workspace=str(session_dir),
                timeout=dispatch_timeout,
            )
            self._write_result_file(
                session_dir,
                {
                    "session_id": session_id,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                },
            )
        except Exception as e:
            logger.error(
                f"Background skill {session_id} failed: {e}\n{traceback.format_exc()}"
            )
            self._write_result_file(
                session_dir,
                {
                    "session_id": session_id,
                    "success": False,
                    "output": None,
                    "error": f"Background dispatch failed: {str(e)}",
                },
            )
        finally:
            _clear_session_event(session_id)

    def run_skill_async(self, skill_name: str, request: str) -> dict[str, Any]:
        """Start a skill invocation in a background thread and return session_id."""
        try:
            skill_name = validate_skill_name(skill_name)
            session_format = "SKILL-NNN"
            session_id, session_dir = create_session(
                self.config.session_work_dir, session_format
            )
            _set_session_event(session_id)

            # Scaffold session.json with the request and required top-level keys.
            session_init(session_id, self.config.session_work_dir, request)
            self._update_session_status(session_dir, "running")
            thread = threading.Thread(
                target=_tracked_target,
                args=(
                    self._run_skill_thread,
                    (session_id, session_dir, skill_name, request),
                ),
                daemon=True,
            )
            _register_thread(thread)
            thread.start()

            return {
                "session_id": session_id,
                "workspace": str(session_dir),
                "status": "started",
            }
        except (InvalidInputError, ValueError) as e:
            logger.error(f"Validation error starting skill {skill_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "status": "failed",
                "error": f"Validation error: {str(e)}",
            }
        except OSError as e:
            logger.error(f"File system error starting skill {skill_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "status": "failed",
                "error": f"File system error: {str(e)}",
            }
        except PathTraversalError as e:
            logger.error(f"Path traversal error starting skill {skill_name}: {e}")
            return {
                "session_id": None,
                "workspace": None,
                "status": "failed",
                "error": f"Path traversal error: {str(e)}",
            }

    def plan_async(self, request: str) -> dict[str, Any]:
        """Start the writing-plans skill in the background."""
        return self.run_skill_async("writing-plans", request)

    def execute_async(self, request: str, intent: str = "auto") -> dict[str, Any]:
        """Route the request and start the matching workflow/skill in background."""
        if intent == "auto":
            intent = self._detect_intent(request)

        if intent == "implement":
            return self.implement_async(request)
        elif intent == "review":
            return self.review_async(request)
        elif intent == "investigate":
            return self.investigate_async(request)
        elif intent == "plan":
            return self.plan_async(request)
        else:
            return {
                "session_id": None,
                "workspace": None,
                "status": "failed",
                "error": f"Unknown intent: {intent}",
            }

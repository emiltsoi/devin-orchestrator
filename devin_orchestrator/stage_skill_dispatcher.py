#!/usr/bin/env python3
"""
Stage Skill Dispatcher

Loads skill definitions and dispatches stage skill invocations via the skill
invoker. This separates skill-loading/prompt-building concerns from stage
execution orchestration.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from devin_orchestrator.security_utils import InvalidInputError, PathTraversalError
from devin_orchestrator.triage_evaluator import TriageDecision

if TYPE_CHECKING:
    from pathlib import Path

    from devin_orchestrator.orchestration_engine import OrchestrationEngine
    from devin_orchestrator.skill_invoker import SkillInvocationResult

logger = logging.getLogger(__name__)


class StageSkillDispatcher:
    """Load and dispatch stage skills."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def load_stage_skill(
        self, skill_name: str, stage_name: str
    ) -> dict[str, Any] | None:
        """
        Load a skill definition from the configured skills directory.

        Returns an error dict on failure, None on success.
        """
        try:
            skills_dir = self._engine.config.get("skills_dir")
            self._engine.load_skill(skills_dir, skill_name)
            logger.info(f"Loaded skill {skill_name} from {skills_dir}")
            return None
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

    def dispatch_stage_skill(
        self,
        skill_name: str,
        stage_name: str,
        stage: dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        correction_artifact: str | None,
    ) -> tuple[SkillInvocationResult | None, dict[str, Any] | None]:
        """
        Dispatch skill invocation with error handling and metrics recording.

        Returns (result, error_dict) where error_dict is None on success.
        """
        try:
            result = self._engine.skill_invoker.invoke_skill(
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
                timeout=self._engine.config.get("dispatch_timeout_seconds"),
            )
            logger.info(
                f"Skill {skill_name} invocation completed with "
                f"success={result.success}"
            )

            # Record skill result in metrics
            self._engine.metrics.record_skill_result(
                skill_name, result.success, result.error
            )
            return result, None
        except (InvalidInputError, ValueError) as e:
            logger.error(
                f"Validation error during skill invocation for {skill_name}: {e}"
            )
            self._engine.metrics.record_skill_result(
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
        except TimeoutError as e:
            logger.error(f"Timeout during skill invocation for {skill_name}: {e}")
            self._engine.metrics.record_skill_result(
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
        except OSError as e:
            logger.error(
                f"File system error during skill invocation for {skill_name}: {e}"
            )
            self._engine.metrics.record_skill_result(
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
        except (RuntimeError, PathTraversalError) as e:
            logger.error(
                f"Error during skill invocation for {skill_name}: {e}"
            )
            self._engine.metrics.record_skill_result(
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
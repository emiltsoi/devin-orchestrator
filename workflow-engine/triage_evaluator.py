#!/usr/bin/env python3
"""
Triage Evaluator

Makes stage-level triage decisions and dispatches neutral reviewers to
evaluate stage artifacts. This separates reviewer/triage logic from stage
execution orchestration.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import TYPE_CHECKING, Any

from guardrails import Guardrails
from security_utils import InvalidInputError, PathTraversalError

if TYPE_CHECKING:
    from pathlib import Path

    from orchestration_engine import OrchestrationEngine

logger = logging.getLogger(__name__)


class TriageDecision(Enum):
    """Triage decision for stage execution"""

    PROCEED = "proceed"
    RETRY = "retry"
    ESCALATE = "escalate"


class TriageEvaluator:
    """Evaluate stage results and dispatch reviewers."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def evaluate_stage_and_triage(
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
                review_artifact_path = self._engine.artifact_validator.validate_artifact_path(
                    f"review-{stage_name}.md", session_dir
                )
                reviewer_verdict, confidence, review_output = self.dispatch_reviewer(
                    stage_name=stage_name,
                    skill_name=skill_name,
                    session_dir=session_dir,
                    session_id=session_id,
                    artifact_paths=artifact_paths,
                    correction_artifact=correction_artifact,
                )
                if review_artifact_path and review_output:
                    review_artifact_path.write_text(review_output, encoding="utf-8")
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
        self._engine.metrics.record_stage_result(
            stage_name, result.success, error, triage_decision.value
        )

        self._engine.update_status(
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

    @staticmethod
    def _parse_explicit_verdict(text: str) -> tuple[str | None, str]:
        """
        Parse explicit verdict and confidence fields from structured reviewer output.

        Recognises both line-based forms (``Verdict: PASS``) and parenthetical
        forms (``Verdict: PASS (confidence: MEDIUM)``), as well as JSON objects.

        Returns:
            Tuple of (verdict, confidence). verdict is None if no explicit
            verdict field is found.
        """
        # Prefer a structured JSON object if the reviewer emitted one.
        json_verdict = TriageEvaluator._parse_json_verdict(text)
        if json_verdict is not None:
            return json_verdict

        verdict: str | None = None
        confidence = "HIGH"

        verdict_match = re.search(
            r"^verdict:\s*([^\s\n\(\)]+)", text, re.IGNORECASE | re.MULTILINE
        )
        if verdict_match:
            value = verdict_match.group(1).strip().lower().rstrip(".")
            if value in {"pass", "proceed", "approve", "approved"}:
                verdict = "PASS"
            elif value in {"fail", "block", "blocked", "reject", "rejected"}:
                verdict = "FAIL"

        confidence_match = re.search(
            r"confidence:\s*([^\s\n\(\)]+)", text, re.IGNORECASE
        )
        if confidence_match:
            value = confidence_match.group(1).strip().lower().rstrip(".")
            if value in {"medium", "med"}:
                confidence = "MEDIUM"
            elif value in {"low"}:
                confidence = "LOW"
            elif value in {"high"}:
                confidence = "HIGH"

        return verdict, confidence

    @staticmethod
    def _parse_json_verdict(text: str) -> tuple[str | None, str] | None:
        """
        Extract a structured verdict from JSON embedded in reviewer output.

        Expected keys (case-insensitive):
        - verdict: "PASS" | "FAIL" | "PROCEED" | "BLOCK" | "APPROVE" etc.
        - confidence: "HIGH" | "MEDIUM" | "LOW"

        Returns:
            Tuple of (verdict, confidence) if found, otherwise None.
        """
        # Find the first well-formed JSON object in the text.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        raw_verdict = None
        for key in ("verdict", "decision", "status"):
            if key in data:
                raw_verdict = data[key]
                break

        if raw_verdict is None:
            return None

        verdict_value = str(raw_verdict).strip().lower()
        if verdict_value in {"pass", "proceed", "approve", "approved"}:
            verdict = "PASS"
        elif verdict_value in {"fail", "block", "blocked", "reject", "rejected"}:
            verdict = "FAIL"
        else:
            return None

        raw_confidence = data.get("confidence", "high")
        confidence_value = str(raw_confidence).strip().lower()
        if confidence_value in {"medium", "med"}:
            confidence = "MEDIUM"
        elif confidence_value in {"low"}:
            confidence = "LOW"
        else:
            confidence = "HIGH"

        return verdict, confidence

    def _verify_reviewer_fail_with_guardrails(
        self, artifact_paths: list[Path]
    ) -> tuple[bool, list[str]]:
        """
        Independently verify a reviewer FAIL verdict using Guardrails.

        Guardrails can meaningfully verify Python artifacts (syntax, leaf-module
        coupling). For non-Python artifacts it can only confirm existence, which
        is not enough to override a reviewer FAIL. Therefore, an override is only
        attempted when at least one Python artifact is present and all Python
        artifacts pass verification.

        Returns:
            Tuple of (all_verified, notes).
        """
        if not artifact_paths:
            return False, ["No artifacts provided for verification"]

        python_artifacts = [p for p in artifact_paths if p.suffix == ".py"]
        if not python_artifacts:
            return False, [
                "No Python artifacts to verify; cannot override reviewer FAIL verdict"
            ]

        notes: list[str] = []
        all_verified = True
        for p in python_artifacts:
            if not p.exists():
                all_verified = False
                notes.append(f"{p.name}: file does not exist")
                continue
            result = Guardrails.verify_compliance_block("BLOCK", file_path=p)
            notes.extend(result.get("notes", []))
            if not result.get("verified"):
                all_verified = False
        return all_verified, notes

    def dispatch_reviewer(
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

        review_output_artifact = self._engine.artifact_validator.validate_artifact_path(
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

        result = self._engine.skill_invoker.invoke_skill(
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

        explicit_verdict, explicit_confidence = self._parse_explicit_verdict(
            review_output
        )
        if explicit_verdict is not None:
            verdict = explicit_verdict
            confidence = explicit_confidence
        else:
            logger.warning(
                f"No explicit verdict field in reviewer output for stage {stage_name}; "
                "falling back to regex/keyword parsing"
            )
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

        if verdict == "FAIL":
            verified, guardrails_notes = self._verify_reviewer_fail_with_guardrails(
                artifact_paths
            )
            if verified:
                verdict = "PASS"
                confidence = "MEDIUM"
                review_output = (
                    review_output.rstrip()
                    + "\n\n[Guardrails override: reviewer FAIL overridden because "
                    "artifacts verified]\n"
                    + "\n".join(guardrails_notes)
                )
            else:
                review_output = (
                    review_output.rstrip()
                    + "\n\n[Guardrails: verification failed]\n"
                    + "\n".join(guardrails_notes)
                )

        review_text = (
            f"# Review for {stage_name}\n\nVerdict: {verdict}\n"
            f"Confidence: {confidence}\n\n{review_output}"
        )
        return verdict, confidence, review_text

    def skip_stage(
        self, stage: dict[str, Any], session_dir: Path, session_id: str
    ) -> dict[str, Any]:
        """
        Skip a stage (e.g., brainstorming when spec is clear).

        Args:
            stage: Stage configuration from manifest
            session_dir: Session directory
            session_id: Session identifier

        Returns:
            Dictionary with stage skip results
        """
        stage_name = stage["name"]

        self._engine.update_status(
            session_dir, stage_name, "skipped", "Skipping stage - spec is clear"
        )

        # Create placeholder artifacts
        try:
            output_artifacts = stage.get("output_artifacts", [])
            for artifact in output_artifacts:
                artifact_path = self._engine.artifact_validator.validate_artifact_path(
                    artifact, session_dir
                )
                if artifact_path.name == "design.md":
                    placeholder = (
                        f"# Design\n\nSkipping brainstorming - spec is clear.\n\n"
                        f"Session ID: {session_id}\n"
                    )
                    self._engine.create_placeholder_artifact(artifact_path, placeholder)
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

#!/usr/bin/env python3
"""
Workflow Stage Executor

Executes individual workflow stages, handles retries, artifact validation,
and triage decisions. OrchestrationEngine delegates stage execution to this
class and remains responsible for gates and interactive pause handling.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from devin_orchestrator.artifact_validator import ArtifactValidator
from devin_orchestrator.models import Manifest, Stage
from devin_orchestrator.otel_tracing import trace_span
from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
)
from devin_orchestrator.stage_skill_dispatcher import StageSkillDispatcher
from devin_orchestrator.state_store import JsonlStateStore
from devin_orchestrator.triage_evaluator import TriageDecision, TriageEvaluator

if TYPE_CHECKING:
    from pathlib import Path

    from devin_orchestrator.orchestration_engine import OrchestrationEngine
    from devin_orchestrator.skill_invoker import SkillInvocationResult
    from devin_orchestrator.state_store import StateStore

logger = logging.getLogger(__name__)


class WorkflowStageExecutor:
    """
    Executes workflow stages on behalf of OrchestrationEngine.

    Stage execution now delegates to focused collaborators: ArtifactValidator,
    StageSkillDispatcher, TriageEvaluator, and (via the engine) GateController.
    """

    def __init__(
        self,
        engine: OrchestrationEngine,
        *,
        artifact_validator: ArtifactValidator | None = None,
        triage_evaluator: TriageEvaluator | None = None,
        stage_skill_dispatcher: StageSkillDispatcher | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        self._engine = engine
        self._artifact_validator = artifact_validator or ArtifactValidator(engine)
        self._triage_evaluator = triage_evaluator or TriageEvaluator(engine)
        self._stage_skill_dispatcher = stage_skill_dispatcher or StageSkillDispatcher(engine)
        self._state_store = state_store or JsonlStateStore()

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the parent engine."""
        return getattr(self._engine, name)

    def _refresh_results(self, results: dict[str, Any]) -> None:
        """Sync the in-memory results dict from the durable state store."""
        results["stages"] = [
            self._normalize_stage_result(s) for s in self._state_store.list_stages()
        ]
        results["final_status"] = self._state_store.get_status()

    def _normalize_stage_result(self, stage_result: dict[str, Any]) -> dict[str, Any]:
        """Convert triage_decision strings back to TriageDecision enum values."""
        triage = stage_result.get("triage_decision")
        if isinstance(triage, str):
            with suppress(ValueError):
                stage_result["triage_decision"] = TriageDecision(triage)
        return stage_result

    def _persist_stage(
        self, stage_name: str, stage_result: dict[str, Any], status: str = "completed"
    ) -> None:
        """Persist a stage result, tagging it with a status for resume logic."""
        stage_result["status"] = status
        self._state_store.save_stage(stage_name, stage_result)

    def _is_session_cancelled(self, session_dir: Path) -> bool:
        """Check whether the session has been marked for cancellation."""
        session_file = session_dir / "session.json"
        try:
            if session_file.exists():
                data = json.loads(session_file.read_text(encoding="utf-8"))
                return data.get("status") in ("cancelling", "cancelled")
        except (OSError, json.JSONDecodeError):
            pass
        return False

    def _run_workflow_stages(
        self,
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        results: dict[str, Any],
        resume: bool = False,
    ) -> None:
        """
        Execute all stages in the manifest, updating results in place.

        Args:
            manifest: Workflow manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills
            results: Results dictionary to update in place
            resume: If True, _execute_stage uses the state store for completed stages
        """
        manifest = Manifest.ensure(manifest)
        self._state_store.init(session_id, session_dir)

        for stage in manifest.stages:
            if self._process_stage(
                stage,
                manifest,
                session_dir,
                session_id,
                config_overrides,
                results,
                resume,
            ):
                break

        self._refresh_results(results)
        # Leave final_status for the OrchestrationEngine unless the workflow
        # paused or ended inside a stage (escalated, cancelled, waiting, blocked).
        if results["final_status"] not in {
            "escalated",
            "cancelled",
            "waiting_for_input",
            "blocked",
            "failed",
        }:
            results["final_status"] = "unknown"

    def _process_stage(
        self,
        stage: Stage,
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        results: dict[str, Any],
        resume: bool,
    ) -> bool:
        """Execute a single stage and return True if the outer stage loop should stop."""
        stage = Stage.ensure(stage)
        manifest = Manifest.ensure(manifest)
        stage_name = stage.name
        self._state_store.init(session_id, session_dir)

        with trace_span(
            "_process_stage",
            {
                "session_id": session_id,
                "stage_name": stage_name,
                "skill_name": stage.skill,
            },
        ):
            if self._is_session_cancelled(session_dir):
                self._state_store.set_status("cancelled", "Session cancelled")
                self._engine.update_status(
                    session_dir,
                    stage_name,
                    "cancelled",
                    "Session cancelled",
                )
                self._refresh_results(results)
                return True

            try:
                stage_result = self._engine._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id,
                    config_overrides=config_overrides,
                    resume=resume,
                )
            except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                logger.error(f"Error executing stage {stage_name}: {e}")
                stage_result = {
                    "stage": stage_name,
                    "skill": stage.skill,
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
                self._persist_stage(stage_name, stage_result, "escalated")
                self._state_store.set_status("escalated", f"Unexpected error: {e}")
                self._engine.update_status(
                    session_dir,
                    stage_name,
                    "error",
                    f"Unexpected error: {str(e)}",
                )
                self._refresh_results(results)
                return True

            triage = stage_result["triage_decision"]
            if triage == TriageDecision.ESCALATE:
                self._persist_stage(stage_name, stage_result, "escalated")
                self._state_store.set_status("escalated", "Workflow escalated to human")
                self._engine.update_status(
                    session_dir,
                    stage_name,
                    "escalated",
                    "Workflow escalated to human",
                )
                self._refresh_results(results)
                return True

            if triage == TriageDecision.RETRY:
                should_break, stage_result = self._retry_stage_execution(
                    stage,
                    manifest,
                    session_dir,
                    session_id,
                    config_overrides,
                    stage_result,
                )
                self._persist_stage(
                    stage_name, stage_result, "escalated" if should_break else "completed"
                )
                if should_break:
                    self._state_store.set_status("escalated", "Retry exhausted")
                self._refresh_results(results)
                if should_break:
                    return True

            if stage.gate and stage.gate != "none":
                return self._process_stage_gate(
                    stage,
                    stage_result,
                    manifest,
                    session_dir,
                    session_id,
                    config_overrides,
                    results,
                )

            self._persist_stage(stage_name, stage_result, "completed")
            self._refresh_results(results)
            return False

    def _process_stage_gate(
        self,
        stage: Stage,
        stage_result: dict[str, Any],
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        results: dict[str, Any],
    ) -> bool:
        """Handle the gate after a stage, including request-changes retries."""
        stage = Stage.ensure(stage)
        manifest = Manifest.ensure(manifest)
        gate_id = stage.gate
        stage_name = stage.name
        self._state_store.init(session_id, session_dir)
        max_gate_request_changes = self._resolve_max_gate_request_changes(stage)
        gate_request_changes_count = 0

        with trace_span(
            "_process_stage_gate",
            {
                "session_id": session_id,
                "stage_name": stage_name,
                "gate_id": gate_id or "",
            },
        ):
            while True:
                gate_result = self._handle_gate(
                    gate_id=gate_id,
                    stage_name=stage_name,
                    session_dir=session_dir,
                    manifest=manifest,
                    stage_result=stage_result,
                )
                if gate_result.get("requires_input"):
                    self._persist_stage(stage_name, stage_result, "completed")
                    self._state_store.set_status(
                        "waiting_for_input",
                        gate_result.get("notes", f"Gate {gate_id} waiting for agent decision"),
                    )
                    self._engine.update_status(
                        session_dir,
                        f"gate_{gate_id}",
                        "waiting",
                        gate_result.get("notes", f"Gate {gate_id} waiting for agent decision"),
                    )
                    self._refresh_results(results)
                    return True

                if gate_result.get("blocked"):
                    self._persist_stage(stage_name, stage_result, "completed")
                    self._state_store.set_status(
                        "blocked",
                        gate_result.get("notes", f"Gate {gate_id} blocked"),
                    )
                    self._engine.update_status(
                        session_dir,
                        f"gate_{gate_id}",
                        "block",
                        gate_result.get("notes", f"Gate {gate_id} blocked"),
                    )
                    self._refresh_results(results)
                    return True

                if gate_result.get("verdict") == "request_changes":
                    gate_request_changes_count += 1
                    if gate_request_changes_count > max_gate_request_changes:
                        error_msg = (
                            f"Gate {gate_id} requested changes "
                            f"{gate_request_changes_count - 1} times for stage "
                            f"{stage_name}; escalating to avoid infinite loop"
                        )
                        logger.warning(error_msg)
                        self._persist_stage(stage_name, stage_result, "escalated")
                        self._state_store.set_status("escalated", error_msg)
                        self._engine.update_status(
                            session_dir,
                            stage_name,
                            "escalated",
                            error_msg,
                        )
                        self._refresh_results(results)
                        return True

                    self._engine.update_status(
                        session_dir,
                        stage_name,
                        "request_changes",
                        f"Gate {gate_id} requested changes",
                    )

                    should_break, stage_result = self._retry_stage_execution(
                        stage,
                        manifest,
                        session_dir,
                        session_id,
                        config_overrides,
                        {
                            "stage": stage_name,
                            "skill": stage.skill,
                            "success": False,
                            "output": None,
                            "error": gate_result.get(
                                "notes", f"Gate {gate_id} requested changes"
                            ),
                            "validation": {"valid": False, "errors": [], "artifact_results": {}},
                            "triage_decision": TriageDecision.RETRY,
                        },
                    )
                    if should_break:
                        self._persist_stage(stage_name, stage_result, "escalated")
                        self._state_store.set_status("escalated", "Retry exhausted")
                        self._refresh_results(results)
                        return True

                    self._persist_stage(stage_name, stage_result, "completed")
                    continue

                break

            self._persist_stage(stage_name, stage_result, "completed")
            self._refresh_results(results)
            return False

    def _retry_stage_execution(
        self,
        stage: Stage,
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        stage_result: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """
        Retry a failed stage with exponential backoff and correction artifacts.

        Args:
            stage: Stage configuration from manifest
            manifest: Full manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills
            stage_result: Previous stage execution result

        Returns:
            Tuple of (break_loop, final_stage_result). ``break_loop`` is True if
            the outer stage loop should stop (retries exhausted).
            ``final_stage_result`` is the last stage execution result produced
            by the retry loop so callers can re-evaluate gates with fresh data.
        """
        stage = Stage.ensure(stage)
        manifest = Manifest.ensure(manifest)
        max_retries = self._resolve_max_retries(stage)
        retry_count = 0
        last_error = stage_result["error"]

        while retry_count < max_retries:
            retry_count += 1
            self._engine.update_status(
                session_dir,
                stage.name,
                "retrying",
                f"Retry {retry_count}/{max_retries}: {last_error}",
            )

            # Exponential backoff: 2^retry_count seconds.  Jitter was removed
            # so retry timing is deterministic and unit-testable.
            backoff_seconds = 2**retry_count
            time.sleep(backoff_seconds)

            # Re-dispatch with correction artifact
            try:
                correction_artifact = self._validate_artifact_path(
                    f"correction-{stage.name}-attempt{retry_count}.md",
                    session_dir,
                )
                correction_artifact.write_text(
                    f"# Correction for {stage.name}\n\n"
                    f"Error: {last_error}\n\n"
                    "Please fix the issue and re-run the stage."
                )
                logger.info(
                    f"Created correction artifact: {correction_artifact}"
                )
            except (OSError, PermissionError, InvalidInputError, PathTraversalError) as e:
                logger.error(f"Error creating correction artifact: {e}")
                self._engine.update_status(
                    session_dir,
                    stage.name,
                    "error",
                    f"Failed to create correction artifact: {str(e)}",
                )
                break

            stage_result = self._engine._execute_stage(
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
            self._engine.update_status(
                session_dir,
                stage.name,
                "escalated",
                f"Max retries ({max_retries}) exceeded: {last_error}",
            )
            # Log retry exhaustion
            logger.warning(
                f"Retry attempts exhausted for stage {stage.name} "
                f"after {max_retries} attempts: {last_error}"
            )
            return True, stage_result

        return False, stage_result
    def _resolve_max_gate_request_changes(self, stage: Stage) -> int:
        """
        Resolve the maximum number of gate request_changes cycles for a stage.

        This cap prevents an infinite loop when a gate keeps returning
        ``request_changes`` and the stage keeps succeeding without resolving
        the underlying concern. It defaults to ``max_gate_request_changes``
        from the stage config, then falls back to ``max_retries``, and finally
        to a hardcoded default of 3.

        Args:
            stage: Stage configuration from manifest

        Returns:
            Maximum number of gate request_changes cycles
        """
        stage = Stage.ensure(stage)
        default_max = 3
        stage_name = stage.name

        raw_max = stage.max_gate_request_changes
        if raw_max is None:
            raw_max = stage.max_retries
        if raw_max is None:
            return default_max

        try:
            max_gate_request_changes = int(raw_max)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid max_gate_request_changes value for stage {stage_name}: "
                f"{raw_max!r}; using default {default_max}"
            )
            return default_max
        if max_gate_request_changes < 0:
            logger.warning(
                f"max_gate_request_changes cannot be negative for stage {stage_name}; "
                f"using {default_max}"
            )
            return default_max
        if max_gate_request_changes > 10:
            logger.warning(
                f"max_gate_request_changes too large for stage {stage_name}; clamping to 10"
            )
            return 10
        return max_gate_request_changes

    def _resolve_max_retries(self, stage: Stage) -> int:
        """
        Resolve max retry count for a stage from its configuration.

        Falls back to the default of 3 and clamps to a sane range.
        Invalid values are logged and treated as the default.

        Args:
            stage: Stage configuration from manifest

        Returns:
            Maximum number of retries for this stage
        """
        stage = Stage.ensure(stage)
        default_max = 3
        stage_name = stage.name
        raw_max = stage.max_retries
        if raw_max is None:
            return default_max
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
    def _execute_stage(
        self,
        stage: Stage,
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None = None,
        correction_artifact: str | None = None,
        resume: bool = False,
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

        Returns:
            Dictionary with stage execution results
        """
        stage = Stage.ensure(stage)
        manifest = Manifest.ensure(manifest)
        stage_name = stage.name
        skill_name = stage.skill

        # When resuming, check the state store before re-running a stage that has
        # already completed. Statuses like "request_changes" cause a re-run.
        self._state_store.init(session_id, session_dir)
        if resume:
            previous = self._state_store.load_stage(stage_name)
            if previous and previous.get("status") == "completed":
                return self._normalize_stage_result(previous)

        self._engine.update_status(
            session_dir, stage_name, "in_progress", f"Starting stage: {stage_name}"
        )

        # Check if stage should be skipped
        if manifest.skip_brainstorming and stage_name == "brainstorming":
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
                stage.skill == "requesting-code-review",
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
                stage_name, session_dir, stage.output_artifacts
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
    def _load_stage_skill(
        self, skill_name: str, stage_name: str
    ) -> dict[str, Any] | None:
        """Delegate to StageSkillDispatcher."""
        return self._stage_skill_dispatcher.load_stage_skill(
            skill_name, stage_name
        )

    def _dispatch_stage_skill(
        self,
        skill_name: str,
        stage_name: str,
        stage: Stage,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None,
        correction_artifact: str | None,
    ) -> tuple[SkillInvocationResult | None, dict[str, Any] | None]:
        """Delegate to StageSkillDispatcher."""
        stage = Stage.ensure(stage)
        return self._stage_skill_dispatcher.dispatch_stage_skill(
            skill_name,
            stage_name,
            stage,
            session_dir,
            session_id,
            config_overrides,
            correction_artifact,
        )
    def _validate_artifact_path(
        self, artifact_name: str, session_dir: Path
    ) -> Path:
        """Delegate to ArtifactValidator."""
        return self._artifact_validator.validate_artifact_path(
            artifact_name, session_dir
        )

    def _validate_stage_artifacts(
        self,
        stage_name: str,
        session_dir: Path,
        output_artifacts: list[str],
    ) -> tuple[dict[str, Any], list[Path]]:
        """Delegate to ArtifactValidator."""
        return self._artifact_validator.validate_stage_artifacts(
            stage_name, session_dir, output_artifacts
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
        """Delegate to TriageEvaluator."""
        return self._triage_evaluator.evaluate_stage_and_triage(
            stage_name,
            skill_name,
            session_dir,
            session_id,
            result,
            validation_result,
            artifact_paths,
            correction_artifact,
        )

    def _skip_stage(
        self, stage: Stage, session_dir: Path, session_id: str
    ) -> dict[str, Any]:
        """Delegate to TriageEvaluator."""
        stage = Stage.ensure(stage)
        return self._triage_evaluator.skip_stage(stage, session_dir, session_id)

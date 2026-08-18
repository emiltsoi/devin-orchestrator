#!/usr/bin/env python3
# mypy: disable-error-code="attr-defined"
"""Stage gate and request-changes limit logic for WorkflowStageExecutor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from devin_orchestrator.models import Manifest, Stage
from devin_orchestrator.otel_tracing import trace_span
from devin_orchestrator.triage_evaluator import TriageDecision

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class WorkflowStageGateMixin:
    """Mixin containing gate processing helpers for workflow stage execution."""

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
                        gate_result.get(
                            "notes", f"Gate {gate_id} waiting for agent decision"
                        ),
                    )
                    self._engine.update_status(
                        session_dir,
                        f"gate_{gate_id}",
                        "waiting",
                        gate_result.get(
                            "notes", f"Gate {gate_id} waiting for agent decision"
                        ),
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
                            "validation": {
                                "valid": False,
                                "errors": [],
                                "artifact_results": {},
                            },
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

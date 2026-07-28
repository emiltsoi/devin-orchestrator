#!/usr/bin/env python3
"""
Gate Controller

Handles workflow gates: human/agent approval, decision files, wait/parse logic,
and auto-gate bypass evaluation. This separates gate concerns from stage
execution orchestration.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from deterministic_tools import record_gate, wait_for_file_change
from security_utils import InvalidInputError, PathTraversalError

if TYPE_CHECKING:
    from pathlib import Path

    from orchestration_engine import OrchestrationEngine

logger = logging.getLogger(__name__)

# Gate interaction modes
GATE_MODE_INTERACTIVE = "interactive"
GATE_MODE_SIGNAL = "signal"
GATE_MODE_AUTO = "auto"


class GateController:
    """Evaluate gates and manage gate decision files."""

    def __init__(self, engine: OrchestrationEngine) -> None:
        self._engine = engine

    def handle_gate(
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
        self._engine.update_status(
            session_dir,
            f"gate_{gate_id}",
            "waiting",
            f"Waiting for gate decision: {gate_id}",
        )

        # Create gate decision file for human/agent input
        error = self.create_gate_decision_file(gate_id, stage_name, session_dir)
        if error is not None:
            return error

        gate_decision_file = self._engine.artifact_validator.validate_artifact_path(
            f"gate-{gate_id}-decision.md", session_dir
        )

        gate_mode = self._engine.config.get("gate_mode", GATE_MODE_INTERACTIVE)

        # Legacy interactive mode: block until the decision file is edited.
        if gate_mode == GATE_MODE_INTERACTIVE:
            try:
                return self.wait_and_parse_gate_decision(
                    gate_id, session_dir, gate_decision_file
                )
            except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                logger.error(f"Error during gate handling: {e}")
                self._engine.update_status(
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
        parsed = self.read_gate_decision(gate_decision_file)
        if parsed is not None:
            verdict, notes = parsed
            if verdict in ["approve", "request_changes", "block"]:
                try:
                    record_gate(gate_id, verdict, session_dir, notes)
                    self._engine.update_status(
                        session_dir,
                        f"gate_{gate_id}",
                        verdict,
                        f"Gate {verdict}: {gate_id}",
                    )
                    logger.info(f"Gate {gate_id} decision recorded: {verdict}")
                except (OSError, RuntimeError, InvalidInputError, PathTraversalError) as e:
                    logger.error(f"Error recording gate decision: {e}")
                    self._engine.update_status(
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
            return self.build_gate_signal(
                gate_id, stage_name, session_dir, gate_decision_file
            )

        # ``auto`` mode: decide whether to bypass or escalate.
        bypass = self.evaluate_gate_bypass_conditions(
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
                self._engine.update_status(
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
        signal = self.build_gate_signal(
            gate_id, stage_name, session_dir, gate_decision_file, verdict, notes, conditions
        )
        return signal

    def read_gate_decision(
        self, gate_decision_file: Path
    ) -> tuple[str, str] | None:
        """Read a gate decision file once and return the parsed verdict if present."""
        try:
            content = gate_decision_file.read_text(encoding="utf-8")
        except (OSError, PermissionError):
            return None
        return self.parse_gate_verdict(content)

    def build_gate_signal(
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

    def get_gate_config(
        self, gate_id: str, manifest: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Return gate configuration from the manifest, or an empty dict."""
        if not manifest:
            return {}
        for gate in manifest.get("gates", []):
            if gate.get("id") == gate_id:
                return gate
        return {}

    def evaluate_gate_bypass_conditions(
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
        gate_config = self.get_gate_config(gate_id, manifest)
        output = (stage_result.get("output") or "").lower()

        # demo_mode is a simulation override: it short-circuits all other
        # bypass/escalation checks so automated tests and dry-runs do not
        # block on gates.
        if self._engine.config.get("demo_mode"):
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
                "name": "reviewer_medium_confidence",
                "triggered": stage_result.get("confidence") == "MEDIUM",
                "verdict": "request_changes",
                "reason": "reviewer reported medium confidence; retry recommended",
            },
            {
                "name": "missing_or_empty_output",
                "triggered": not output.strip(),
                "verdict": "request_changes",
                "reason": "stage output is empty or missing",
            },
            {
                "name": "unstructured_output_fallback",
                "triggered": (
                    stage_result.get("reviewer_verdict") is None
                    and stage_result.get("confidence") is None
                    and any(
                        keyword in output
                        for keyword in ["rejected", "cannot proceed", "must fix"]
                    )
                ),
                "verdict": "request_changes",
                "reason": "unstructured stage output contains rejection keywords; falling back to request_changes",
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
        bypass_config = self._engine.config.get("gate_bypass_conditions") or {}
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

    def create_gate_decision_file(
        self, gate_id: str, stage_name: str, session_dir: Path
    ) -> dict[str, Any] | None:
        """
        Create the gate decision file for human input.

        Returns an error dict on failure, None on success.
        """
        try:
            gate_decision_file = self._engine.artifact_validator.validate_artifact_path(
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
            self._engine.update_status(
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

    def wait_and_parse_gate_decision(
        self, gate_id: str, session_dir: Path, gate_decision_file: Path
    ) -> dict[str, Any]:
        """
        Wait for the gate decision file to be modified and parse the decision.

        Uses filesystem events instead of polling and returns a gate result
        dictionary (either a verdict, a read error, or a timeout).
        """
        max_wait_seconds = self._engine.config.get("gate_timeout_seconds", 3600)
        deadline = time.time() + max_wait_seconds

        def _process_content(content: str) -> dict[str, Any] | None:
            """Parse and record a verdict if one is present."""
            parsed = self.parse_gate_verdict(content)
            if parsed is not None:
                verdict, notes = parsed
                if verdict in ["approve", "request_changes", "block"]:
                    try:
                        record_gate(gate_id, verdict, session_dir, notes)
                        self._engine.update_status(
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
                        self._engine.update_status(
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
            return None

        # Check if the file already contains a verdict before waiting for events.
        try:
            initial_content = gate_decision_file.read_text(encoding="utf-8")
        except (OSError, PermissionError) as e:
            logger.error(f"Error reading gate decision file: {e}")
            self._engine.update_status(
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

        initial_result = _process_content(initial_content)
        if initial_result is not None:
            return initial_result

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            # Block until the decision file changes or the timeout expires.
            if not wait_for_file_change(gate_decision_file, timeout=remaining):
                # Timeout elapsed with no further edits.
                break

            # Check if file has been modified (contains decision)
            try:
                content = gate_decision_file.read_text(encoding="utf-8")
            except (OSError, PermissionError) as e:
                logger.error(f"Error reading gate decision file: {e}")
                self._engine.update_status(
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

            result = _process_content(content)
            if result is not None:
                return result

        # Timeout reached - escalate
        verdict = "block"
        notes = f"Gate decision timeout after {max_wait_seconds} seconds"
        try:
            record_gate(gate_id, verdict, session_dir, notes)
            self._engine.update_status(
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
            self._engine.update_status(
                session_dir,
                f"gate_{gate_id}",
                "error",
                f"Failed to record gate timeout: {str(e)}",
            )

        return {"gate_id": gate_id, "verdict": verdict, "blocked": True}

    def parse_gate_verdict(
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
            stripped = line.strip()
            if stripped.startswith("verdict:"):
                verdict = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("notes:"):
                notes = stripped.split(":", 1)[1].strip()
        if verdict is None:
            return None
        return verdict, notes

"""
Unit tests for WorkflowStageExecutor stage/gate/retry state machine.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from devin_orchestrator.triage_evaluator import TriageDecision
from devin_orchestrator.workflow_stage_executor import WorkflowStageExecutor


class TestWorkflowStageExecutor(unittest.TestCase):
    """Cover the extracted stage/gate/retry methods."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.session_dir = self.temp_dir / "session"
        self.session_dir.mkdir()
        self.session_id = "TEST-001"

        self.engine = MagicMock()
        self.wse = WorkflowStageExecutor(
            self.engine,
            artifact_validator=MagicMock(),
            triage_evaluator=MagicMock(),
            stage_skill_dispatcher=MagicMock(),
        )

        self.base_stage = {
            "step": 0,
            "name": "test-stage",
            "skill": "brainstorming",
            "description": "A test stage",
            "output_artifacts": ["result.md"],
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _proceed_result(self):
        return {
            "stage": "test-stage",
            "skill": "brainstorming",
            "success": True,
            "output": "ok",
            "error": None,
            "validation": {"valid": True, "errors": [], "artifact_results": {}},
            "triage_decision": TriageDecision.PROCEED,
        }

    def _make_results(self):
        return {"session_id": self.session_id, "stages": [], "final_status": "unknown"}

    def test_process_stage_proceed_no_gate(self):
        self.engine._execute_stage.return_value = self._proceed_result()
        results = self._make_results()

        stop = self.wse._process_stage(
            self.base_stage,
            {"stages": [self.base_stage]},
            self.session_dir,
            self.session_id,
            None,
            results,
            False,
        )

        self.assertFalse(stop)
        self.assertEqual(len(results["stages"]), 1)
        self.assertEqual(results["final_status"], "unknown")

    def test_process_stage_escalate(self):
        self.engine._execute_stage.return_value = {
            **self._proceed_result(),
            "triage_decision": TriageDecision.ESCALATE,
        }
        results = self._make_results()

        stop = self.wse._process_stage(
            self.base_stage,
            {"stages": [self.base_stage]},
            self.session_dir,
            self.session_id,
            None,
            results,
            False,
        )

        self.assertTrue(stop)
        self.assertEqual(results["final_status"], "escalated")

    @patch.object(WorkflowStageExecutor, "_retry_stage_execution")
    def test_process_stage_retry_then_proceed(self, mock_retry):
        retry_result = self._proceed_result()
        mock_retry.return_value = (False, retry_result)

        self.engine._execute_stage.return_value = {
            **self._proceed_result(),
            "triage_decision": TriageDecision.RETRY,
        }
        results = self._make_results()

        stop = self.wse._process_stage(
            self.base_stage,
            {"stages": [self.base_stage]},
            self.session_dir,
            self.session_id,
            None,
            results,
            False,
        )

        self.assertFalse(stop)
        self.assertEqual(results["stages"][-1], retry_result)
        mock_retry.assert_called_once()

    @patch.object(WorkflowStageExecutor, "_process_stage_gate")
    def test_process_stage_calls_gate_handler(self, mock_gate):
        self.engine._execute_stage.return_value = self._proceed_result()
        stage = {**self.base_stage, "gate": "g1_approve"}
        mock_gate.return_value = False
        results = self._make_results()

        stop = self.wse._process_stage(
            stage,
            {"stages": [stage], "gates": [{"id": "g1_approve", "type": "human"}]},
            self.session_dir,
            self.session_id,
            None,
            results,
            False,
        )

        self.assertFalse(stop)
        mock_gate.assert_called_once()

    def test_process_stage_gate_approve(self):
        self.engine._execute_stage.return_value = self._proceed_result()
        self.engine._handle_gate.return_value = {
            "gate_id": "g1_approve",
            "verdict": "approve",
            "blocked": False,
        }
        stage = {**self.base_stage, "gate": "g1_approve"}
        results = self._make_results()
        results["stages"] = [self._proceed_result()]

        stop = self.wse._process_stage_gate(
            stage,
            self._proceed_result(),
            {"stages": [stage], "gates": [{"id": "g1_approve", "type": "human"}]},
            self.session_dir,
            self.session_id,
            None,
            results,
        )

        self.assertFalse(stop)
        self.assertEqual(results["final_status"], "unknown")
        self.engine._handle_gate.assert_called_once()

    def test_process_stage_gate_block(self):
        self.engine._execute_stage.return_value = self._proceed_result()
        self.engine._handle_gate.return_value = {
            "gate_id": "g1_approve",
            "verdict": "block",
            "blocked": True,
        }
        stage = {**self.base_stage, "gate": "g1_approve"}
        results = self._make_results()
        results["stages"] = [self._proceed_result()]

        stop = self.wse._process_stage_gate(
            stage,
            self._proceed_result(),
            {"stages": [stage], "gates": [{"id": "g1_approve", "type": "human"}]},
            self.session_dir,
            self.session_id,
            None,
            results,
        )

        self.assertTrue(stop)
        self.assertEqual(results["final_status"], "blocked")

    @patch.object(WorkflowStageExecutor, "_retry_stage_execution")
    def test_process_stage_gate_request_changes_then_approve(self, mock_retry):
        self.engine._handle_gate.side_effect = [
            {"verdict": "request_changes", "notes": "fix it"},
            {"verdict": "approve", "blocked": False},
        ]
        mock_retry.return_value = (False, self._proceed_result())

        stage = {**self.base_stage, "gate": "g1_approve"}
        results = self._make_results()
        results["stages"] = [self._proceed_result()]

        stop = self.wse._process_stage_gate(
            stage,
            self._proceed_result(),
            {"stages": [stage], "gates": [{"id": "g1_approve", "type": "human"}]},
            self.session_dir,
            self.session_id,
            None,
            results,
        )

        self.assertFalse(stop)
        self.assertEqual(self.engine._handle_gate.call_count, 2)
        mock_retry.assert_called_once()

    @patch.object(WorkflowStageExecutor, "_retry_stage_execution")
    def test_process_stage_gate_request_changes_exceeds_max(self, mock_retry):
        self.engine._handle_gate.return_value = {"verdict": "request_changes", "notes": "fix it"}
        mock_retry.return_value = (False, self._proceed_result())

        stage = {**self.base_stage, "gate": "g1_approve", "max_gate_request_changes": 1}
        results = self._make_results()
        results["stages"] = [self._proceed_result()]

        stop = self.wse._process_stage_gate(
            stage,
            self._proceed_result(),
            {"stages": [stage], "gates": [{"id": "g1_approve", "type": "human"}]},
            self.session_dir,
            self.session_id,
            None,
            results,
        )

        self.assertTrue(stop)
        self.assertEqual(results["final_status"], "escalated")
        self.assertEqual(mock_retry.call_count, 1)

    @patch.object(WorkflowStageExecutor, "_retry_stage_execution")
    def test_process_stage_gate_retry_exhausted(self, mock_retry):
        self.engine._handle_gate.return_value = {"verdict": "request_changes", "notes": "fix it"}
        mock_retry.return_value = (True, {})  # retry exhausted

        stage = {**self.base_stage, "gate": "g1_approve"}
        results = self._make_results()
        results["stages"] = [self._proceed_result()]

        stop = self.wse._process_stage_gate(
            stage,
            self._proceed_result(),
            {"stages": [stage], "gates": [{"id": "g1_approve", "type": "human"}]},
            self.session_dir,
            self.session_id,
            None,
            results,
        )

        self.assertTrue(stop)
        self.assertEqual(results["final_status"], "escalated")

    def test_process_stage_cancellation_stops_loop(self):
        session_file = self.session_dir / "session.json"
        session_file.write_text(json.dumps({"status": "cancelling"}), encoding="utf-8")

        results = self._make_results()
        stop = self.wse._process_stage(
            self.base_stage,
            {"stages": [self.base_stage]},
            self.session_dir,
            self.session_id,
            None,
            results,
            False,
        )

        self.assertTrue(stop)
        self.assertEqual(results["final_status"], "cancelled")

    def test_run_workflow_stages_iterates_and_stops(self):
        self.engine._execute_stage.return_value = self._proceed_result()
        self.engine._handle_gate.return_value = {"verdict": "approve", "blocked": False}

        stage1 = {**self.base_stage, "name": "stage-1"}
        stage2 = {**self.base_stage, "name": "stage-2"}
        results = self._make_results()

        self.wse._run_workflow_stages(
            {"stages": [stage1, stage2]},
            self.session_dir,
            self.session_id,
            None,
            results,
            False,
        )

        self.assertEqual(len(results["stages"]), 2)
        self.assertEqual(results["final_status"], "unknown")


if __name__ == "__main__":
    unittest.main()

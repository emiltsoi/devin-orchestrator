"""
Unit tests for GateController.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from devin_orchestrator.gate_controller import (
    GATE_MODE_AUTO,
    GATE_MODE_INTERACTIVE,
    GATE_MODE_SIGNAL,
    GateController,
)


class TestGateController(unittest.TestCase):
    """Focused tests for GateController"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.session_dir = Path(self.temp_dir) / "session-abc"
        self.session_dir.mkdir()

        self.engine = MagicMock()
        self.engine.config = {}
        self.engine.artifact_validator = MagicMock()
        self.controller = GateController(self.engine)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _decision_path(self, gate_id="g1"):
        return self.session_dir / f"gate-{gate_id}-decision.md"

    # ---------- parse_gate_verdict ----------

    def test_parse_gate_verdict_approve(self):
        """Verdict and notes are parsed from standard decision content."""
        content = "verdict: approve\nnotes: looks good\n"
        parsed = self.controller.parse_gate_verdict(content)
        self.assertEqual(parsed, ("approve", "looks good"))

    def test_parse_gate_verdict_request_changes(self):
        content = "verdict: request_changes\nnotes: fix typo\n"
        parsed = self.controller.parse_gate_verdict(content)
        self.assertEqual(parsed, ("request_changes", "fix typo"))

    def test_parse_gate_verdict_missing(self):
        """Content without a verdict line returns None."""
        self.assertIsNone(self.controller.parse_gate_verdict("some notes"))

    # ---------- get_gate_config ----------

    def test_get_gate_config_found(self):
        manifest = {
            "gates": [{"id": "g1", "name": "g1", "type": "auto", "mandatory": True}]
        }
        cfg = self.controller.get_gate_config("g1", manifest)
        self.assertTrue(cfg["mandatory"])

    def test_get_gate_config_missing(self):
        manifest = {"gates": [{"id": "g1", "name": "g1", "type": "auto"}]}
        cfg = self.controller.get_gate_config("g2", manifest)
        self.assertEqual(cfg, {})

    def test_get_gate_config_no_manifest(self):
        self.assertEqual(self.controller.get_gate_config("g1", None), {})

    # ---------- evaluate_gate_bypass_conditions ----------

    def test_bypass_demo_mode(self):
        """demo_mode short-circuits to approve."""
        self.engine.config = {"demo_mode": True}
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1", "stage", self.session_dir, self._decision_path(), None, {}
        )
        self.assertEqual(result["verdict"], "approve")

    def test_bypass_mandatory_gate(self):
        """A mandatory gate blocks by default."""
        manifest = {
            "gates": [{"id": "g1", "name": "g1", "type": "auto", "mandatory": True}]
        }
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            manifest,
            {"success": True},
        )
        self.assertEqual(result["verdict"], "block")

    def test_bypass_stage_failure(self):
        """A failed preceding stage blocks."""
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {"success": False},
        )
        self.assertEqual(result["verdict"], "block")

    def test_bypass_reviewer_rejected(self):
        """A FAIL reviewer verdict requests changes."""
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {"success": True, "reviewer_verdict": "FAIL"},
        )
        self.assertEqual(result["verdict"], "request_changes")

    def test_bypass_medium_confidence(self):
        """Medium confidence reviewer verdict requests changes."""
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {"success": True, "reviewer_verdict": "PASS", "confidence": "MEDIUM"},
        )
        self.assertEqual(result["verdict"], "request_changes")

    def test_bypass_benign_keywords_ignored(self):
        """Benign mentions of critical/security/block words do not block."""
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {
                "success": True,
                "reviewer_verdict": "PASS",
                "confidence": "HIGH",
                "output": "critical security block",
            },
        )
        self.assertEqual(result["verdict"], "approve")

    def test_bypass_empty_output(self):
        """Empty output requests changes."""
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {
                "success": True,
                "reviewer_verdict": "PASS",
                "confidence": "HIGH",
                "output": "",
            },
        )
        self.assertEqual(result["verdict"], "request_changes")

    def test_bypass_unstructured_output_fallback(self):
        """Unstructured output falls back to keyword rejection detection."""
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {"success": True, "output": "rejected: cannot proceed"},
        )
        self.assertEqual(result["verdict"], "request_changes")

    def test_bypass_high_confidence_non_security(self):
        """Config-driven bypass approves HIGH confidence successes."""
        self.engine.config = {
            "gate_bypass_conditions": {"confidence_high_non_security": True}
        }
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            None,
            {"success": True, "confidence": "HIGH"},
        )
        self.assertEqual(result["verdict"], "approve")

    def test_bypass_high_confidence_with_block_condition(self):
        """A mandatory gate block condition overrides the high-confidence bypass."""
        self.engine.config = {
            "gate_bypass_conditions": {"confidence_high_non_security": True}
        }
        manifest = {
            "gates": [{"id": "g1", "name": "g1", "type": "auto", "mandatory": True}]
        }
        result = self.controller.evaluate_gate_bypass_conditions(
            "g1",
            "stage",
            self.session_dir,
            self._decision_path(),
            manifest,
            {"success": True, "reviewer_verdict": "PASS", "confidence": "HIGH"},
        )
        self.assertEqual(result["verdict"], "block")

    # ---------- create_gate_decision_file ----------

    def test_create_gate_decision_file_writes_template(self):
        """A decision file is created with the expected template."""
        self.engine.artifact_validator.validate_artifact_path.return_value = (
            self._decision_path()
        )

        error = self.controller.create_gate_decision_file(
            "g1", "stage", self.session_dir
        )

        self.assertIsNone(error)
        content = self._decision_path().read_text(encoding="utf-8")
        self.assertIn("Gate Decision: g1", content)
        self.assertIn("Stage: stage", content)

    def test_create_gate_decision_file_already_exists(self):
        """An existing decision file is left untouched."""
        path = self._decision_path()
        path.write_text("existing")
        self.engine.artifact_validator.validate_artifact_path.return_value = path

        error = self.controller.create_gate_decision_file(
            "g1", "stage", self.session_dir
        )

        self.assertIsNone(error)
        self.assertEqual(path.read_text(encoding="utf-8"), "existing")

    def test_create_gate_decision_file_os_error(self):
        """An OSError while writing returns a block error dict."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path.write_text.side_effect = OSError("denied")
        self.engine.artifact_validator.validate_artifact_path.return_value = mock_path

        error = self.controller.create_gate_decision_file(
            "g1", "stage", self.session_dir
        )

        self.assertEqual(error["verdict"], "block")
        self.assertTrue(error["blocked"])

    # ---------- handle_gate ----------

    def test_handle_gate_interactive(self):
        """Interactive mode delegates to wait_and_parse_gate_decision."""
        self.engine.config = {"gate_mode": GATE_MODE_INTERACTIVE}
        path = self._decision_path()
        self.engine.artifact_validator.validate_artifact_path.return_value = path

        with patch.object(
            self.controller,
            "wait_and_parse_gate_decision",
            return_value={"gate_id": "g1", "verdict": "approve", "blocked": False},
        ) as mock_wait:
            result = self.controller.handle_gate("g1", "stage", self.session_dir)

        mock_wait.assert_called_once_with("g1", self.session_dir, path)
        self.assertEqual(result["verdict"], "approve")

    def test_handle_gate_signal(self):
        """Signal mode returns a non-blocking request for input."""
        self.engine.config = {"gate_mode": GATE_MODE_SIGNAL}
        path = self._decision_path()
        self.engine.artifact_validator.validate_artifact_path.return_value = path

        result = self.controller.handle_gate("g1", "stage", self.session_dir)

        self.assertFalse(result["blocked"])
        self.assertTrue(result["requires_input"])
        self.assertEqual(result["decision_file"], str(path))

    def test_handle_gate_auto_approve(self):
        """Auto mode with demo config auto-approves."""
        self.engine.config = {"gate_mode": GATE_MODE_AUTO, "demo_mode": True}
        path = self._decision_path()
        self.engine.artifact_validator.validate_artifact_path.return_value = path

        with patch("devin_orchestrator.gate_controller.record_gate") as mock_record:
            result = self.controller.handle_gate("g1", "stage", self.session_dir)

        self.assertEqual(result["verdict"], "approve")
        self.assertTrue(result["auto_approved"])
        mock_record.assert_called_once()

    def test_handle_gate_auto_request_changes(self):
        """Auto mode with a request-changes condition signals the agent."""
        self.engine.config = {"gate_mode": GATE_MODE_AUTO}
        path = self._decision_path()
        self.engine.artifact_validator.validate_artifact_path.return_value = path

        result = self.controller.handle_gate(
            "g1",
            "stage",
            self.session_dir,
            stage_result={"success": True, "output": ""},
        )

        self.assertEqual(result["verdict"], "request_changes")
        self.assertTrue(result["requires_input"])

    def test_handle_gate_prerecorded_decision(self):
        """A pre-existing decision file is honored."""
        path = self._decision_path()
        path.write_text("verdict: block\nnotes: no go\n")
        self.engine.artifact_validator.validate_artifact_path.return_value = path
        self.engine.config = {"gate_mode": GATE_MODE_AUTO}

        with patch("devin_orchestrator.gate_controller.record_gate") as mock_record:
            result = self.controller.handle_gate("g1", "stage", self.session_dir)

        self.assertEqual(result["verdict"], "block")
        self.assertTrue(result["blocked"])
        mock_record.assert_called_once()

    # ---------- wait_and_parse_gate_decision ----------

    @patch(
        "devin_orchestrator.gate_controller.wait_for_file_change", return_value=False
    )
    @patch("devin_orchestrator.gate_controller.record_gate")
    def test_wait_and_parse_gate_decision_approve(self, mock_record, mock_wait):
        """The loop reads a decision file and returns the verdict."""
        path = self._decision_path()
        path.write_text("verdict: approve\nnotes: ok\n")
        self.engine.config = {"gate_timeout_seconds": 10, "gate_check_interval": 1}

        result = self.controller.wait_and_parse_gate_decision(
            "g1", self.session_dir, path
        )

        self.assertEqual(result["verdict"], "approve")
        self.assertFalse(result["blocked"])
        mock_record.assert_called_once_with("g1", "approve", self.session_dir, "ok")

    @patch(
        "devin_orchestrator.gate_controller.wait_for_file_change", return_value=False
    )
    @patch("devin_orchestrator.gate_controller.record_gate")
    def test_wait_and_parse_gate_decision_timeout(self, mock_record, mock_wait):
        """A timeout returns block."""
        path = self._decision_path()
        path.write_text("no verdict here", encoding="utf-8")
        self.engine.config = {"gate_timeout_seconds": 1, "gate_check_interval": 2}

        result = self.controller.wait_and_parse_gate_decision(
            "g1", self.session_dir, path
        )

        self.assertTrue(result["blocked"])
        mock_record.assert_called_once_with(
            "g1", "block", self.session_dir, unittest.mock.ANY
        )

    # ---------- build_gate_signal ----------

    def test_build_gate_signal_contains_required_keys(self):
        path = self._decision_path()
        signal = self.controller.build_gate_signal(
            "g1", "stage", self.session_dir, path
        )

        self.assertEqual(signal["gate_id"], "g1")
        self.assertIn("decision_file", signal)
        self.assertIn("instruction", signal)
        self.assertFalse(signal["blocked"])
        self.assertTrue(signal["requires_input"])


if __name__ == "__main__":
    unittest.main()

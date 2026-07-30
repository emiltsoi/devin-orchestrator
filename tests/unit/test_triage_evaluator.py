"""
Unit tests for TriageEvaluator.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from devin_orchestrator.triage_evaluator import TriageDecision, TriageEvaluator


class TestTriageEvaluator(unittest.TestCase):
    """Focused tests for TriageEvaluator"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.session_dir = Path(self.temp_dir) / "session"
        self.session_dir.mkdir()

        self.engine = MagicMock()
        self.engine.artifact_validator = MagicMock()
        self.engine.metrics = MagicMock()
        self.triage = TriageEvaluator(self.engine)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _result(self, success=True, output="output", error=None):
        return SimpleNamespace(success=success, output=output, error=error)

    # ---------- evaluate_stage_and_triage ----------

    def test_evaluate_stage_and_triage_proceed(self):
        """Successful result + valid validation + PASS reviewer => PROCEED."""
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        result = self._result()
        validation = {"valid": True, "errors": [], "artifact_results": {}}

        with patch.object(
            self.triage, "dispatch_reviewer", return_value=("PASS", "HIGH", "good")
        ):
            stage_result = self.triage.evaluate_stage_and_triage(
                "stage", "skill", self.session_dir, "s1", result, validation, [], None
            )

        self.assertEqual(stage_result["triage_decision"], TriageDecision.PROCEED)
        self.assertIsNone(stage_result["error"])
        self.engine.metrics.record_stage_result.assert_called_once()

    def test_evaluate_stage_and_triage_escalate_on_failure(self):
        """A failed skill result escalates regardless of validation."""
        result = self._result(success=False, error="boom")
        validation = {"valid": True, "errors": [], "artifact_results": {}}

        stage_result = self.triage.evaluate_stage_and_triage(
            "stage", "skill", self.session_dir, "s1", result, validation, [], None
        )

        self.assertEqual(stage_result["triage_decision"], TriageDecision.ESCALATE)
        self.assertEqual(stage_result["error"], "boom")

    def test_evaluate_stage_and_triage_retry_on_validation_error(self):
        """Invalid validation triggers a retry."""
        result = self._result()
        validation = {
            "valid": False,
            "errors": ["bad artifact"],
            "artifact_results": {},
        }

        stage_result = self.triage.evaluate_stage_and_triage(
            "stage", "skill", self.session_dir, "s1", result, validation, [], None
        )

        self.assertEqual(stage_result["triage_decision"], TriageDecision.RETRY)
        self.assertIn("bad artifact", stage_result["error"])

    def test_evaluate_stage_and_triage_retry_on_reviewer_fail(self):
        """A FAIL reviewer verdict triggers retry."""
        validation = {"valid": True, "errors": [], "artifact_results": {}}
        result = self._result()

        with patch.object(
            self.triage, "dispatch_reviewer", return_value=("FAIL", "LOW", "bad")
        ):
            stage_result = self.triage.evaluate_stage_and_triage(
                "stage", "skill", self.session_dir, "s1", result, validation, [], None
            )

        self.assertEqual(stage_result["triage_decision"], TriageDecision.RETRY)
        self.assertEqual(stage_result["reviewer_verdict"], "FAIL")

    def test_evaluate_stage_and_triage_reviewer_dispatch_error(self):
        """An exception during reviewer dispatch is treated as FAIL/LOW."""
        validation = {"valid": True, "errors": [], "artifact_results": {}}
        result = self._result()
        self.engine.artifact_validator.validate_artifact_path.side_effect = OSError(
            "disk full"
        )

        stage_result = self.triage.evaluate_stage_and_triage(
            "stage", "skill", self.session_dir, "s1", result, validation, [], None
        )

        self.assertEqual(stage_result["triage_decision"], TriageDecision.RETRY)
        self.assertEqual(stage_result["reviewer_verdict"], "FAIL")
        self.assertEqual(stage_result["confidence"], "LOW")

    # ---------- dispatch_reviewer ----------

    def test_dispatch_reviewer_no_artifacts(self):
        """No existing artifact paths returns PASS/HIGH."""
        verdict, confidence, output = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", []
        )

        self.assertEqual(verdict, "PASS")
        self.assertEqual(confidence, "HIGH")
        self.assertIn("No artifacts to review", output)
        self.engine.skill_invoker.invoke_skill.assert_not_called()

    def test_dispatch_reviewer_excellent_assessment(self):
        """Explicit 'excellent' assessment yields PASS/HIGH."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="Overall Quality Assessment: EXCELLENT\nCritical Issues Found: 0",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, _ = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "PASS")
        self.assertEqual(confidence, "HIGH")

    def test_dispatch_reviewer_acceptable_assessment(self):
        """'acceptable' assessment yields PASS/MEDIUM."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="Overall Quality Assessment: ACCEPTABLE",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, _ = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "PASS")
        self.assertEqual(confidence, "MEDIUM")

    def test_dispatch_reviewer_poor_assessment(self):
        """'poor' assessment yields FAIL/LOW."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="Overall Quality Assessment: POOR",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, _ = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "FAIL")
        self.assertEqual(confidence, "LOW")

    def test_dispatch_reviewer_critical_issues(self):
        """Critical issues found yields FAIL/LOW."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="Critical Issues Found: 2",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, _ = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "FAIL")
        self.assertEqual(confidence, "LOW")

    def test_dispatch_reviewer_warning_keyword(self):
        """Warning keyword yields PASS/MEDIUM."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="One warning: minor issue",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, _ = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "PASS")
        self.assertEqual(confidence, "MEDIUM")

    def test_dispatch_reviewer_invocation_failure(self):
        """A failed invocation returns FAIL/LOW with the error."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(success=False, output=None, error="invoke failed")
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, output = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "FAIL")
        self.assertEqual(confidence, "LOW")
        self.assertEqual(output, "invoke failed")

    # ---------- skip_stage ----------

    def test_skip_stage_proceed(self):
        """Skipping a stage with a design placeholder returns PROCEED."""
        design_path = self.session_dir / "design.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = design_path
        stage = {
            "name": "brainstorming",
            "skill": "brainstorming",
            "output_artifacts": ["design.md"],
        }

        result = self.triage.skip_stage(stage, self.session_dir, "s1")

        self.assertEqual(result["triage_decision"], TriageDecision.PROCEED)
        self.assertTrue(result["success"])
        self.engine.create_placeholder_artifact.assert_called_once_with(
            design_path, unittest.mock.ANY
        )

    def test_skip_stage_no_artifacts(self):
        """Skipping a stage with no artifacts still succeeds."""
        stage = {
            "name": "brainstorming",
            "skill": "brainstorming",
            "output_artifacts": [],
        }

        result = self.triage.skip_stage(stage, self.session_dir, "s1")

        self.assertEqual(result["triage_decision"], TriageDecision.PROCEED)
        self.assertTrue(result["success"])
        self.engine.create_placeholder_artifact.assert_not_called()

    def test_skip_stage_error(self):
        """An artifact creation error escalates."""
        self.engine.artifact_validator.validate_artifact_path.side_effect = OSError(
            "boom"
        )
        stage = {
            "name": "brainstorming",
            "skill": "brainstorming",
            "output_artifacts": ["design.md"],
        }

        result = self.triage.skip_stage(stage, self.session_dir, "s1")

        self.assertEqual(result["triage_decision"], TriageDecision.ESCALATE)
        self.assertFalse(result["success"])

    def test_parse_explicit_verdict(self):
        """Explicit verdict/confidence fields are parsed case-insensitively."""
        self.assertEqual(
            self.triage._parse_explicit_verdict("verdict: fail\nconfidence: low"),
            ("FAIL", "LOW"),
        )
        self.assertEqual(
            self.triage._parse_explicit_verdict("Verdict: PASS"),
            ("PASS", "HIGH"),
        )
        self.assertEqual(
            self.triage._parse_explicit_verdict("no verdict here"),
            (None, "HIGH"),
        )

    def test_parse_explicit_verdict_with_parenthetical(self):
        """Verdict and confidence can appear in a parenthetical form."""
        self.assertEqual(
            self.triage._parse_explicit_verdict("Verdict: PASS (confidence: MEDIUM)"),
            ("PASS", "MEDIUM"),
        )

    def test_parse_json_verdict(self):
        """A structured JSON verdict is preferred over keyword parsing."""
        output = (
            "Some prose before the verdict.\n\n"
            '{"verdict": "FAIL", "confidence": "LOW", "notes": "bad"}\n'
            "Some prose after."
        )
        self.assertEqual(
            self.triage._parse_explicit_verdict(output),
            ("FAIL", "LOW"),
        )

    def test_dispatch_reviewer_explicit_verdict(self):
        """An explicit verdict field is used before regex/keyword fallback."""
        artifact = self.session_dir / "design.md"
        artifact.write_text("content")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="verdict: PASS\nconfidence: MEDIUM\nLooks good.",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, _ = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [artifact]
        )

        self.assertEqual(verdict, "PASS")
        self.assertEqual(confidence, "MEDIUM")

    def test_dispatch_reviewer_guardrails_overrides_fail(self):
        """A reviewer FAIL on verified Python artifacts is overridden to PASS/MEDIUM."""
        code = self.session_dir / "code.py"
        code.write_text("\n".join(f"# line {i}" for i in range(15)), encoding="utf-8")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="verdict: FAIL\nconfidence: LOW",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, output = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [code]
        )

        self.assertEqual(verdict, "PASS")
        self.assertEqual(confidence, "MEDIUM")
        self.assertIn("Guardrails override", output)

    def test_dispatch_reviewer_guardrails_keeps_real_fail(self):
        """A reviewer FAIL on unverified artifacts is kept as FAIL."""
        tiny = self.session_dir / "tiny.py"
        tiny.write_text("print('hi')\n", encoding="utf-8")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="verdict: FAIL\nconfidence: LOW",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, output = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [tiny]
        )

        self.assertEqual(verdict, "FAIL")
        self.assertEqual(confidence, "LOW")
        self.assertIn("Guardrails: verification failed", output)

    def test_dispatch_reviewer_guardrails_no_override_for_non_python(self):
        """A reviewer FAIL on non-Python artifacts cannot be overridden."""
        design = self.session_dir / "design.md"
        design.write_text("# Design\n\nContent here.", encoding="utf-8")
        review_path = self.session_dir / "review-stage.md"
        self.engine.artifact_validator.validate_artifact_path.return_value = review_path
        mock_result = SimpleNamespace(
            success=True,
            output="verdict: FAIL\nconfidence: LOW",
            error=None,
        )
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        verdict, confidence, output = self.triage.dispatch_reviewer(
            "stage", "skill", self.session_dir, "s1", [design]
        )

        self.assertEqual(verdict, "FAIL")
        self.assertEqual(confidence, "LOW")
        self.assertIn("cannot override reviewer FAIL", output)


if __name__ == "__main__":
    unittest.main()

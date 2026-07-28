"""
Unit tests for StageSkillDispatcher.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from security_utils import InvalidInputError, PathTraversalError
from stage_skill_dispatcher import StageSkillDispatcher
from triage_evaluator import TriageDecision


class TestStageSkillDispatcher(unittest.TestCase):
    """Focused tests for StageSkillDispatcher"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.session_dir = self.temp_dir / "session"
        self.session_dir.mkdir()

        self.engine = MagicMock()
        self.engine.config = {"skills_dir": str(self.temp_dir / "skills")}
        self.engine.skill_invoker = MagicMock()
        self.engine.metrics = MagicMock()
        self.dispatcher = StageSkillDispatcher(self.engine)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ---------- load_stage_skill ----------

    def test_load_stage_skill_success(self):
        """A successful skill load returns None and calls engine.load_skill."""
        error = self.dispatcher.load_stage_skill("brainstorming", "brainstorming")

        self.assertIsNone(error)
        self.engine.load_skill.assert_called_once_with(
            str(self.temp_dir / "skills"), "brainstorming"
        )

    def test_load_stage_skill_invalid_input(self):
        """InvalidInputError from load_skill produces an escalate error dict."""
        self.engine.load_skill.side_effect = InvalidInputError("bad skill")

        error = self.dispatcher.load_stage_skill("bad", "stage")

        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("Validation error", error["error"])

    def test_load_stage_skill_not_found(self):
        """FileNotFoundError produces an escalate error dict."""
        self.engine.load_skill.side_effect = FileNotFoundError("missing")

        error = self.dispatcher.load_stage_skill("missing", "stage")

        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("Skill not found", error["error"])

    def test_load_stage_skill_json_error(self):
        """JSONDecodeError produces an escalate error dict."""
        self.engine.load_skill.side_effect = json.JSONDecodeError("bad json", "", 0)

        error = self.dispatcher.load_stage_skill("bad-json", "stage")

        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("Invalid JSON", error["error"])

    def test_load_stage_skill_runtime_error(self):
        """RuntimeError/PathTraversalError produces an escalate error dict."""
        self.engine.load_skill.side_effect = PathTraversalError("unsafe")

        error = self.dispatcher.load_stage_skill("unsafe", "stage")

        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("Error loading skill", error["error"])

    # ---------- dispatch_stage_skill ----------

    def _stage(self, output_artifacts=None):
        return {
            "name": "stage",
            "skill": "brainstorming",
            "output_artifacts": output_artifacts or [],
        }

    def test_dispatch_stage_skill_success(self):
        """A successful invocation returns the result and records metrics."""
        mock_result = SimpleNamespace(success=True, output="ok", error=None)
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        result, error = self.dispatcher.dispatch_stage_skill(
            "brainstorming", "stage", self._stage(), self.session_dir, "s1", None, None
        )

        self.assertEqual(result, mock_result)
        self.assertIsNone(error)
        self.engine.metrics.record_skill_result.assert_called_once_with(
            "brainstorming", True, None
        )

    def test_dispatch_stage_skill_reviewer_flag(self):
        """Skill 'requesting-code-review' sets is_reviewer=True."""
        stage = {"name": "stage", "skill": "requesting-code-review"}
        mock_result = SimpleNamespace(success=True, output="ok", error=None)
        self.engine.skill_invoker.invoke_skill.return_value = mock_result

        self.dispatcher.dispatch_stage_skill(
            "requesting-code-review", "stage", stage, self.session_dir, "s1", None, None
        )

        call_kwargs = self.engine.skill_invoker.invoke_skill.call_args.kwargs
        self.assertTrue(call_kwargs["is_reviewer"])

    def test_dispatch_stage_skill_validation_error(self):
        """ValidationError during invocation returns escalate dict."""
        self.engine.skill_invoker.invoke_skill.side_effect = ValueError("bad args")

        result, error = self.dispatcher.dispatch_stage_skill(
            "brainstorming", "stage", self._stage(), self.session_dir, "s1", None, None
        )

        self.assertIsNone(result)
        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("Validation error", error["error"])

    def test_dispatch_stage_skill_os_error(self):
        """OSError during invocation returns escalate dict."""
        self.engine.skill_invoker.invoke_skill.side_effect = OSError("disk")

        result, error = self.dispatcher.dispatch_stage_skill(
            "brainstorming", "stage", self._stage(), self.session_dir, "s1", None, None
        )

        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("File system error", error["error"])

    def test_dispatch_stage_skill_timeout(self):
        """TimeoutError during invocation returns retry dict."""
        self.engine.skill_invoker.invoke_skill.side_effect = TimeoutError("slow")

        result, error = self.dispatcher.dispatch_stage_skill(
            "brainstorming", "stage", self._stage(), self.session_dir, "s1", None, None
        )

        self.assertEqual(error["triage_decision"], TriageDecision.RETRY)
        self.assertIn("Timeout", error["error"])

    def test_dispatch_stage_skill_runtime_error(self):
        """RuntimeError/PathTraversalError returns escalate dict."""
        self.engine.skill_invoker.invoke_skill.side_effect = PathTraversalError("unsafe")

        result, error = self.dispatcher.dispatch_stage_skill(
            "brainstorming", "stage", self._stage(), self.session_dir, "s1", None, None
        )

        self.assertEqual(error["triage_decision"], TriageDecision.ESCALATE)
        self.assertIn("Unexpected error", error["error"])


if __name__ == "__main__":
    unittest.main()

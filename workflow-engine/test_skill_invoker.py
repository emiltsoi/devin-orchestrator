"""
Unit Tests for Skill Invoker
Tests follow TDD principles - written to validate existing implementation
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))

from devin_cli_adapter import DevinCliAdapter, InvocationResult
from skill_invoker import SkillInvoker


class TestSkillInvoker(unittest.TestCase):
    """Test cases for SkillInvoker"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.harness_root = self.temp_path / "harness"
        self.harness_root.mkdir()
        self.skills_dir = self.temp_path / "skills"
        self.skills_dir.mkdir()

        # Create skill files
        (self.skills_dir / "brainstorming.yaml").write_text(
            "schema_version: 1\n"
            "name: brainstorming\n"
            "description: Brainstorming skill\n"
            'iron_law: "NO IMPLEMENTATION UNTIL DESIGN APPROVED"\n'
            "triggers: [new_feature]\n"
            "checklist: []\n"
            "terminal_state: writing-plans\n"
            'announcement: "Using the brainstorming skill to refine {topic}"\n'
            "red_flags: []\n"
        )

        (self.skills_dir / "brainstorming.md").write_text(
            "# Brainstorming Skill\n\n"
            "## Overview\n"
            "Brainstorming skill for generating ideas.\n\n"
            "## The Iron Law\n"
            "NO IMPLEMENTATION UNTIL DESIGN APPROVED\n"
        )

        self.devin_cli_path = str(self.temp_path / "devin.exe")
        (self.temp_path / "devin.exe").write_text(
            "# fake devin cli"
        )  # File must exist for SkillInvoker
        self.skill_invoker = SkillInvoker(self.skills_dir, self.devin_cli_path)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_invoke_skill_success(self):
        """Should successfully invoke skill using devin-cli"""
        context = {
            "session_id": "TEST-001",
            "step": "step_1",
            "session_dir": str(self.temp_path / "work" / "TEST-001"),
            "required_artifacts": ["requirement.md"],
        }

        # Mock the adapter to return success
        with patch.object(DevinCliAdapter, "invoke") as mock_invoke:
            mock_invoke.return_value = InvocationResult(
                success=True,
                output="Skill executed successfully",
                error=None,
                exit_code=0,
            )

            result = self.skill_invoker.invoke_skill("brainstorming", context)

            self.assertTrue(result.success)
            self.assertIsNotNone(result.session_id)
            self.assertEqual(result.output, "Skill executed successfully")
            self.assertIsNone(result.error)

    def test_invoke_skill_missing_definition(self):
        """Should fail when skill YAML not found"""
        context = {"session_id": "TEST-002"}

        result = self.skill_invoker.invoke_skill("nonexistent_skill", context)

        self.assertFalse(result.success)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.output)
        self.assertIn("Skill definition not found", result.error)

    def test_invoke_skill_missing_narrative(self):
        """Should fail when skill markdown not found"""
        # Create YAML but not markdown
        (self.skills_dir / "partial_skill.yaml").write_text(
            "schema_version: 1\nname: partial_skill\n"
        )

        context = {"session_id": "TEST-003"}

        result = self.skill_invoker.invoke_skill("partial_skill", context)

        self.assertFalse(result.success)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.output)
        self.assertIn("Skill narrative not found", result.error)

    def test_invoke_skill_no_devin_path(self):
        """Should fail when devin CLI path not configured"""
        skill_invoker_no_path = SkillInvoker(self.skills_dir, "")
        context = {"session_id": "TEST-004"}

        result = skill_invoker_no_path.invoke_skill("brainstorming", context)

        self.assertFalse(result.success)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.output)
        self.assertIn("Devin CLI path not configured", result.error)

    def test_build_skill_prompt(self):
        """Should build correct prompt with context and skill content"""
        from deterministic_tools import load_skill

        skill_data = load_skill(self.skills_dir, "brainstorming")
        skill_def = skill_data["definition"]
        skill_narrative = skill_data["narrative"]

        context = {
            "session_id": "TEST-005",
            "step": "step_1",
            "required_artifacts": ["requirement.md"],
        }

        prompt = self.skill_invoker.build_skill_prompt(
            "brainstorming", skill_def, skill_narrative, context
        )

        self.assertIn("Skill Invocation: brainstorming", prompt)
        self.assertIn("session_id: TEST-005", prompt)
        self.assertIn("step: step_1", prompt)
        self.assertIn("Iron Law:", prompt)
        self.assertIn("NO IMPLEMENTATION UNTIL DESIGN APPROVED", prompt)
        self.assertIn("Skill Narrative", prompt)
        self.assertIn("Brainstorming Skill", prompt)
        self.assertIn("Instructions", prompt)

    def test_invoke_skill_with_model(self):
        """Should use specified model when provided"""
        skill_invoker_with_model = SkillInvoker(
            self.skills_dir, self.devin_cli_path, model="claude-opus-4.6"
        )

        context = {"session_id": "TEST-006"}

        with patch("skill_invoker.DevinCliAdapter") as mock_adapter_class:
            mock_adapter = Mock()
            mock_adapter_class.return_value = mock_adapter
            mock_adapter.invoke.return_value = InvocationResult(
                success=True, output="Success", error=None, exit_code=0
            )

            result = skill_invoker_with_model.invoke_skill("brainstorming", context)

            self.assertTrue(result.success)
            # Verify adapter was initialized with model parameter
            mock_adapter_class.assert_called_once()
            call_args = mock_adapter_class.call_args
            # Check positional and keyword arguments
            if call_args[1]:  # kwargs
                self.assertEqual(call_args[1].get("model"), "claude-opus-4.6")

    def test_invoke_skill_with_permission_mode(self):
        """Should use specified permission mode"""
        skill_invoker_with_mode = SkillInvoker(
            self.skills_dir, self.devin_cli_path, permission_mode="smart"
        )

        context = {"session_id": "TEST-007"}

        with patch("skill_invoker.DevinCliAdapter") as mock_adapter_class:
            mock_adapter = Mock()
            mock_adapter_class.return_value = mock_adapter
            mock_adapter.invoke.return_value = InvocationResult(
                success=True, output="Success", error=None, exit_code=0
            )

            result = skill_invoker_with_mode.invoke_skill("brainstorming", context)

            self.assertTrue(result.success)
            # Verify adapter was initialized with permission mode parameter
            mock_adapter_class.assert_called_once()
            call_args = mock_adapter_class.call_args
            # Check positional and keyword arguments
            if call_args[1]:  # kwargs
                self.assertEqual(call_args[1].get("permission_mode"), "smart")

    def test_invoke_skill_adapter_exception(self):
        """Should handle adapter exceptions gracefully"""
        context = {"session_id": "TEST-008"}

        with patch.object(DevinCliAdapter, "invoke") as mock_invoke:
            mock_invoke.side_effect = Exception("Adapter error")

            result = self.skill_invoker.invoke_skill("brainstorming", context)

            self.assertFalse(result.success)
            self.assertIsNone(result.session_id)
            self.assertIsNone(result.output)
            self.assertIsNotNone(result.error)
            self.assertIn("Adapter error", result.error)

    def test_session_id_generation(self):
        """Should generate session ID for tracking"""
        context = {"session_id": "TEST-009"}

        with patch.object(DevinCliAdapter, "invoke") as mock_invoke:
            mock_invoke.return_value = InvocationResult(
                success=True, output="Success", error="", exit_code=0
            )

            result = self.skill_invoker.invoke_skill("brainstorming", context)

            self.assertIsNotNone(result.session_id)
            self.assertIn("brainstorming", result.session_id)
            self.assertIn("TEST-009", result.session_id)


if __name__ == "__main__":
    unittest.main()

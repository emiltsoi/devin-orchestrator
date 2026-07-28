"""
Unit tests for ArtifactValidator.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from devin_orchestrator.artifact_validator import ArtifactValidator
from devin_orchestrator.security_utils import InvalidInputError, PathTraversalError


class TestArtifactValidator(unittest.TestCase):
    """Focused tests for ArtifactValidator"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.temp_dir) / "work"
        self.work_dir.mkdir()
        self.session_dir = self.work_dir / "session-1"
        self.session_dir.mkdir(parents=True)

        self.engine = MagicMock()
        self.validator = ArtifactValidator(self.engine)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_artifact_path_success(self):
        """A clean artifact name resolves inside the session directory."""
        expected = self.session_dir / "design.md"
        self.engine.validate_path_safe.return_value = expected

        result = self.validator.validate_artifact_path("design.md", self.session_dir)

        self.assertEqual(result, expected)
        self.engine.validate_path_safe.assert_called_once()
        session_arg, candidate_arg, *_ = self.engine.validate_path_safe.call_args.args
        self.assertEqual(session_arg, self.session_dir)
        self.assertEqual(candidate_arg, expected)

    def test_validate_artifact_path_rejects_invalid_name(self):
        """An invalid artifact name propagates InvalidInputError."""
        self.engine.validate_path_safe.side_effect = InvalidInputError("bad name")

        with self.assertRaises(InvalidInputError):
            self.validator.validate_artifact_path("", self.session_dir)

    def test_validate_artifact_path_rejects_path_traversal(self):
        """A traversal attempt propagates PathTraversalError."""
        self.engine.validate_path_safe.side_effect = PathTraversalError(
            "outside session"
        )

        with self.assertRaises(PathTraversalError):
            self.validator.validate_artifact_path("../../etc/passwd", self.session_dir)

    def test_validate_stage_artifacts_empty_list(self):
        """An empty artifact list is structurally valid."""
        self.engine.validate_structural.return_value = {
            "valid": True,
            "errors": [],
            "artifact_results": {},
        }

        validation, paths = self.validator.validate_stage_artifacts(
            "stage", self.session_dir, []
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(paths, [])
        self.engine.validate_structural.assert_called_once_with(
            [], required_artifacts=[]
        )

    def test_validate_stage_artifacts_success(self):
        """Valid artifact names are collected and validated structurally."""
        artifact_a = self.session_dir / "design.md"
        artifact_b = self.session_dir / "code.py"
        self.engine.validate_path_safe.side_effect = [artifact_a, artifact_b]
        self.engine.validate_structural.return_value = {
            "valid": True,
            "errors": [],
            "artifact_results": {"design.md": {"valid": True}},
        }

        validation, paths = self.validator.validate_stage_artifacts(
            "stage", self.session_dir, ["design.md", "code.py"]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(paths, [artifact_a, artifact_b])
        self.engine.validate_structural.assert_called_once_with(
            paths, required_artifacts=["design.md", "code.py"]
        )

    def test_validate_stage_artifacts_invalid_path(self):
        """A bad artifact name returns an invalid validation result."""
        self.engine.validate_path_safe.side_effect = PathTraversalError(
            "outside session"
        )

        validation, paths = self.validator.validate_stage_artifacts(
            "stage", self.session_dir, ["../../etc/passwd"]
        )

        self.assertFalse(validation["valid"])
        self.assertIn("Invalid artifact path", validation["errors"][0])
        self.assertEqual(paths, [])
        self.engine.validate_structural.assert_not_called()

    def test_validate_stage_artifacts_file_not_found(self):
        """FileNotFoundError from structural validation is handled gracefully."""
        artifact = self.session_dir / "missing.md"
        self.engine.validate_path_safe.return_value = artifact
        self.engine.validate_structural.side_effect = FileNotFoundError("missing")

        validation, paths = self.validator.validate_stage_artifacts(
            "stage", self.session_dir, ["missing.md"]
        )

        self.assertFalse(validation["valid"])
        self.assertIn("Artifact not found", validation["errors"][0])
        self.assertEqual(paths, [artifact])

    def test_validate_stage_artifacts_permission_error(self):
        """PermissionError from structural validation is handled gracefully."""
        artifact = self.session_dir / "secret.md"
        self.engine.validate_path_safe.return_value = artifact
        self.engine.validate_structural.side_effect = PermissionError("denied")

        validation, paths = self.validator.validate_stage_artifacts(
            "stage", self.session_dir, ["secret.md"]
        )

        self.assertFalse(validation["valid"])
        self.assertIn("Permission error", validation["errors"][0])
        self.assertEqual(paths, [artifact])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Tests for security_utils.py validation functions
"""

import os

# Add workflow-engine to path
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))

from security_utils import (
    InvalidInputError,
    PathTraversalError,
    sanitize_filename,
    validate_path_safe,
    validate_session_id,
    validate_skill_name,
    validate_workflow_name,
    validate_workspace_path,
)


class TestValidatePathSafe:
    """Tests for validate_path_safe function"""

    def test_valid_relative_path(self):
        """Test that valid relative paths are accepted"""
        base = Path("/tmp/test")
        target = Path("/tmp/test/subdir/file.txt")
        result = validate_path_safe(base, target, allow_absolute=False)
        assert result == target.resolve()

    def test_valid_absolute_path_allowed(self):
        """Test that valid absolute paths are accepted when allowed"""
        base = Path("/tmp/test")
        target = Path("/tmp/test/subdir/file.txt")
        result = validate_path_safe(base, target, allow_absolute=True)
        assert result == target.resolve()

    def test_absolute_path_rejected_when_not_allowed(self):
        """Test that absolute paths are rejected when not allowed"""
        base = Path("/tmp/test")
        target = Path("/etc/passwd")
        with pytest.raises(PathTraversalError):
            validate_path_safe(base, target, allow_absolute=False)

    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected"""
        base = Path("/tmp/test")
        target = Path("/tmp/test/../../../etc/passwd")
        with pytest.raises(PathTraversalError):
            validate_path_safe(base, target, allow_absolute=False)

    def test_empty_path_rejected(self):
        """Test that empty paths are rejected"""
        base = Path("/tmp/test")
        with pytest.raises(InvalidInputError):
            validate_path_safe(base, Path(""), allow_absolute=False)

    def test_null_bytes_rejected(self):
        """Test that paths with null bytes are rejected"""
        base = Path("/tmp/test")
        with pytest.raises(InvalidInputError):
            validate_path_safe(base, Path("test\x00file"), allow_absolute=False)

    def test_symlink_traversal_rejected(self):
        """Test that symlink traversal is rejected"""
        # Skip on Windows due to permission requirements for symlink creation
        import platform
        if platform.system() == "Windows":
            pytest.skip("Symlink test skipped on Windows due to permission requirements")

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "base"
            base.mkdir()

            # Create a symlink pointing outside base
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            symlink = base / "link"
            symlink.symlink_to(outside)

            # Try to access via symlink
            target = base / "link" / "file.txt"
            with pytest.raises(PathTraversalError):
                validate_path_safe(base, target, allow_absolute=False)


class TestValidateSkillName:
    """Tests for validate_skill_name function"""

    def test_valid_skill_name(self):
        """Test that valid skill names are accepted"""
        assert validate_skill_name("my-skill") == "my-skill"
        assert validate_skill_name("my-skill-123") == "my-skill-123"
        assert validate_skill_name("MySkill") == "MySkill"

    def test_empty_skill_name_rejected(self):
        """Test that empty skill names are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("")

    def test_skill_name_with_whitespace_rejected(self):
        """Test that skill names with whitespace are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("my skill")
        with pytest.raises(InvalidInputError):
            validate_skill_name(" my-skill")

    def test_skill_name_with_dots_rejected(self):
        """Test that skill names with leading/trailing dots are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name(".skill")
        with pytest.raises(InvalidInputError):
            validate_skill_name("skill.")

    def test_skill_name_with_path_separators_rejected(self):
        """Test that skill names with path separators are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("my/skill")
        with pytest.raises(InvalidInputError):
            validate_skill_name("my\\skill")

    def test_skill_name_with_traversal_rejected(self):
        """Test that skill names with traversal sequences are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("../skill")
        with pytest.raises(InvalidInputError):
            validate_skill_name("skill..test")

    def test_skill_name_with_control_chars_rejected(self):
        """Test that skill names with control characters are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("skill\x00test")

    def test_skill_name_with_underscores_rejected(self):
        """Test that skill names with underscores are rejected (hyphens only)"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("my_skill")


class TestValidateWorkflowName:
    """Tests for validate_workflow_name function"""

    def test_valid_workflow_name_with_hyphen(self):
        """Test that hyphenated workflow names are accepted"""
        assert validate_workflow_name("superpower") == "superpower"
        assert validate_workflow_name("code-review") == "code-review"

    def test_valid_workflow_name_with_underscore(self):
        """Test that workflow names with underscores are accepted (e.g. code_review)"""
        assert validate_workflow_name("code_review") == "code_review"
        assert validate_workflow_name("my_workflow_123") == "my_workflow_123"

    def test_empty_workflow_name_rejected(self):
        """Test that empty workflow names are rejected"""
        with pytest.raises(InvalidInputError):
            validate_workflow_name("")

    def test_workflow_name_with_whitespace_rejected(self):
        """Test that workflow names with whitespace are rejected"""
        with pytest.raises(InvalidInputError):
            validate_workflow_name("my workflow")
        with pytest.raises(InvalidInputError):
            validate_workflow_name(" my-workflow")

    def test_workflow_name_with_path_separators_rejected(self):
        """Test that workflow names with path separators are rejected"""
        with pytest.raises(InvalidInputError):
            validate_workflow_name("my/workflow")
        with pytest.raises(InvalidInputError):
            validate_workflow_name("my\\workflow")

    def test_workflow_name_with_traversal_rejected(self):
        """Test that workflow names with traversal sequences are rejected"""
        with pytest.raises(InvalidInputError):
            validate_workflow_name("../workflow")
        with pytest.raises(InvalidInputError):
            validate_workflow_name("workflow..test")

    def test_workflow_name_with_control_chars_rejected(self):
        """Test that workflow names with control characters are rejected"""
        with pytest.raises(InvalidInputError):
            validate_workflow_name("workflow\x00test")


class TestValidateSessionId:
    """Tests for validate_session_id function"""

    def test_valid_session_id(self):
        """Test that valid session IDs are accepted"""
        assert validate_session_id("session-123") == "session-123"
        assert validate_session_id("session_123") == "session_123"
        assert validate_session_id("Session123") == "Session123"

    def test_empty_session_id_rejected(self):
        """Test that empty session IDs are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id("")

    def test_session_id_with_whitespace_rejected(self):
        """Test that session IDs with whitespace are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id("session 123")
        with pytest.raises(InvalidInputError):
            validate_session_id(" session-123")

    def test_session_id_with_dots_rejected(self):
        """Test that session IDs with leading/trailing dots are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id(".session")
        with pytest.raises(InvalidInputError):
            validate_session_id("session.")

    def test_session_id_with_path_separators_rejected(self):
        """Test that session IDs with path separators are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id("session/123")
        with pytest.raises(InvalidInputError):
            validate_session_id("session\\123")

    def test_session_id_with_traversal_rejected(self):
        """Test that session IDs with traversal sequences are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id("../session")
        with pytest.raises(InvalidInputError):
            validate_session_id("session..test")

    def test_session_id_with_control_chars_rejected(self):
        """Test that session IDs with control characters are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id("session\x00test")


class TestValidateWorkspacePath:
    """Tests for validate_workspace_path function"""

    def test_valid_workspace_path(self):
        """Test that valid workspace paths are accepted"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            workspace = base / "workspace"
            workspace.mkdir()
            result = validate_workspace_path(str(workspace), base)
            assert result == workspace.resolve()

    def test_workspace_path_traversal_rejected(self):
        """Test that workspace path traversal is rejected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            workspace = base / ".." / "etc"
            with pytest.raises(PathTraversalError):
                validate_workspace_path(str(workspace), base)

    def test_workspace_path_without_base_rejected(self):
        """Test that workspace path without base_allowed_dir is rejected"""
        with pytest.raises(InvalidInputError):
            validate_workspace_path("/tmp/workspace", None)

    def test_workspace_path_with_null_bytes_rejected(self):
        """Test that workspace paths with null bytes are rejected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            with pytest.raises(InvalidInputError):
                validate_workspace_path("work\x00space", base)

    def test_workspace_path_outside_base_rejected(self):
        """Test that workspace paths outside base are rejected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "allowed"
            base.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            with pytest.raises(PathTraversalError):
                validate_workspace_path(str(outside), base)


class TestSanitizeFilename:
    """Tests for sanitize_filename function"""

    def test_valid_filename(self):
        """Test that valid filenames pass through"""
        assert sanitize_filename("test.txt") == "test.txt"
        assert sanitize_filename("my-file-123.pdf") == "my-file-123.pdf"

    def test_filename_with_path_separators_sanitized(self):
        """Test that path separators are removed"""
        assert sanitize_filename("test/file.txt") == "testfile.txt"
        assert sanitize_filename("test\\file.txt") == "testfile.txt"

    def test_filename_with_traversal_sanitized(self):
        """Test that traversal sequences are removed"""
        # Leading dots are now rejected
        with pytest.raises(InvalidInputError):
            sanitize_filename("../test.txt")
        # Multiple consecutive dots are removed (all ".." sequences)
        assert sanitize_filename("test....txt") == "testtxt"

    def test_filename_with_internal_dots_allowed(self):
        """Test that internal dots are allowed"""
        assert sanitize_filename("test.file.txt") == "test.file.txt"

    def test_filename_with_underscores_allowed(self):
        """Test that underscores are allowed in filenames"""
        assert sanitize_filename("my_file.txt") == "my_file.txt"

    def test_filename_with_null_bytes_sanitized(self):
        """Test that null bytes are removed"""
        assert sanitize_filename("test\x00file.txt") == "testfile.txt"

    def test_filename_with_control_chars_sanitized(self):
        """Test that control characters are removed"""
        assert sanitize_filename("test\x01file.txt") == "testfile.txt"

    def test_filename_with_url_encoding_sanitized(self):
        """Test that URL-encoded traversal attempts are caught"""
        # %2e%2e decodes to ".." and should be rejected (leading dots)
        # However, after stripping leading dots, it becomes "test.txt" which is valid
        # So we test that the slashes are properly handled
        assert sanitize_filename("%2e%2e%2ftest.txt") == "test.txt"
        # %2f decodes to "/" and should be removed
        assert sanitize_filename("test%2ffile.txt") == "testfile.txt"
        # %5c decodes to "\" and should be removed
        assert sanitize_filename("test%5cfile.txt") == "testfile.txt"

    def test_filename_with_leading_dots_rejected(self):
        """Test that filenames with leading dots are rejected"""
        with pytest.raises(InvalidInputError):
            sanitize_filename(".hidden")
        with pytest.raises(InvalidInputError):
            sanitize_filename("..test")

    def test_filename_with_trailing_dots_rejected(self):
        """Test that filenames with trailing dots are rejected"""
        with pytest.raises(InvalidInputError):
            sanitize_filename("test.")
        with pytest.raises(InvalidInputError):
            sanitize_filename("test..")

    def test_filename_with_whitespace_stripped(self):
        """Test that leading/trailing whitespace is stripped"""
        assert sanitize_filename("  test.txt  ") == "test.txt"

    def test_filename_with_double_extensions_preserved(self):
        """Test that double extensions are preserved (not a security concern for this use case)"""
        # We don't strip double extensions as they're not a security concern
        # for our use case
        assert sanitize_filename("file.tar.gz") == "file.tar.gz"
        assert sanitize_filename("file.txt.exe") == "file.txt.exe"

    def test_empty_filename_rejected(self):
        """Test that empty filenames are rejected"""
        with pytest.raises(InvalidInputError):
            sanitize_filename("")

    def test_filename_sanitized_to_empty_rejected(self):
        """Test that filenames that sanitize to empty are rejected"""
        with pytest.raises(InvalidInputError):
            sanitize_filename("....")

    def test_filename_length_limited(self):
        """Test that filename length is limited"""
        long_name = "a" * 300
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) == 100

    def test_filename_with_invalid_chars_rejected(self):
        """Test that filenames with invalid characters are rejected"""
        with pytest.raises(InvalidInputError):
            sanitize_filename("test@file.txt")
        with pytest.raises(InvalidInputError):
            sanitize_filename("test#file.txt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

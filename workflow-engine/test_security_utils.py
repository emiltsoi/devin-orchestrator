#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for security_utils.py
"""

import pytest
import tempfile
import os
from pathlib import Path
from workflow_engine.security_utils import (
    validate_path_safe,
    sanitize_filename,
    sanitize_string,
    check_file_permissions,
    check_directory_permissions,
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
    get_secret_from_env,
    redact_sensitive_data,
    PathTraversalError,
    InvalidInputError,
    SecurityError
)


class TestValidatePathSafe:
    """Tests for validate_path_safe function"""
    
    def test_valid_relative_path(self):
        """Test that valid relative paths are accepted"""
        base = Path("/tmp/test")
        target = Path("/tmp/test/subdir/file.txt")
        result = validate_path_safe(base, target)
        assert result == target.resolve()
    
    def test_path_traversal_detected(self):
        """Test that path traversal attacks are detected"""
        base = Path("/tmp/test")
        target = Path("/tmp/test/../etc/passwd")
        with pytest.raises(PathTraversalError):
            validate_path_safe(base, target)
    
    def test_absolute_path_rejected(self):
        """Test that absolute paths are rejected when not allowed"""
        base = Path("/tmp/test")
        target = Path("/etc/passwd")
        with pytest.raises(PathTraversalError):
            validate_path_safe(base, target, allow_absolute=False)
    
    def test_absolute_path_allowed(self):
        """Test that absolute paths are allowed when configured"""
        base = Path("/tmp/test")
        target = Path("/etc/passwd")
        result = validate_path_safe(base, target, allow_absolute=True)
        assert result == target.resolve()
    
    def test_symlink_traversal(self):
        """Test that symlink traversal is detected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "safe"
            base.mkdir()
            
            # Create symlink outside base
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            symlink = base / "link"
            symlink.symlink_to(outside)
            
            target = base / "link" / "file.txt"
            with pytest.raises(PathTraversalError):
                validate_path_safe(base, target)


class TestSanitizeFilename:
    """Tests for sanitize_filename function"""
    
    def test_basic_sanitization(self):
        """Test basic filename sanitization"""
        result = sanitize_filename("test.txt")
        assert result == "test.txt"
    
    def test_path_separator_removal(self):
        """Test that path separators are removed"""
        result = sanitize_filename("test/../file.txt")
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result
    
    def test_null_byte_removal(self):
        """Test that null bytes are removed"""
        result = sanitize_filename("test\x00file.txt")
        assert "\x00" not in result
    
    def test_control_character_removal(self):
        """Test that control characters are removed"""
        result = sanitize_filename("test\x1ffile.txt")
        assert "\x1f" not in result
    
    def test_length_limit(self):
        """Test that filename length is limited"""
        long_name = "a" * 300
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) <= 100
    
    def test_empty_filename_error(self):
        """Test that empty filename raises error"""
        with pytest.raises(InvalidInputError):
            sanitize_filename("")
    
    def test_invalid_after_sanitization(self):
        """Test that filename becoming empty after sanitization raises error"""
        with pytest.raises(InvalidInputError):
            sanitize_filename("..\x00..\x00")


class TestSanitizeString:
    """Tests for sanitize_string function"""
    
    def test_basic_sanitization(self):
        """Test basic string sanitization"""
        result = sanitize_string("test string")
        assert result == "test string"
    
    def test_null_byte_removal(self):
        """Test that null bytes are removed"""
        result = sanitize_string("test\x00string")
        assert "\x00" not in result
    
    def test_length_limit(self):
        """Test that string length is limited"""
        long_string = "a" * 20000
        with pytest.raises(InvalidInputError):
            sanitize_string(long_string, max_length=10000)
    
    def test_non_string_input(self):
        """Test that non-string input raises error"""
        with pytest.raises(InvalidInputError):
            sanitize_string(123)
    
    def test_allowed_chars_validation(self):
        """Test that allowed characters pattern is enforced"""
        result = sanitize_string("abc123", allowed_chars="a-zA-Z0-9")
        assert result == "abc123"
        
        with pytest.raises(InvalidInputError):
            sanitize_string("abc!123", allowed_chars="a-zA-Z0-9")


class TestCheckFilePermissions:
    """Tests for check_file_permissions function"""
    
    def test_file_exists_check(self):
        """Test that non-existent file returns False"""
        result = check_file_permissions(Path("/nonexistent/file.txt"))
        assert result is False
    
    def test_read_permission_check(self):
        """Test read permission check"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test")
            temp_path = Path(f.name)
        
        try:
            result = check_file_permissions(temp_path, required_read=True)
            assert result is True
        finally:
            temp_path.unlink()
    
    def test_write_permission_check(self):
        """Test write permission check"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test")
            temp_path = Path(f.name)
        
        try:
            result = check_file_permissions(temp_path, required_write=True)
            assert result is True
        finally:
            temp_path.unlink()


class TestCheckDirectoryPermissions:
    """Tests for check_directory_permissions function"""
    
    def test_directory_exists_check(self):
        """Test that non-existent directory returns False"""
        result = check_directory_permissions(Path("/nonexistent/dir"))
        assert result is False
    
    def test_file_not_directory(self):
        """Test that file path returns False"""
        with tempfile.NamedTemporaryFile() as f:
            result = check_directory_permissions(Path(f.name))
            assert result is False
    
    def test_directory_permissions(self):
        """Test directory permission check"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = check_directory_permissions(Path(tmpdir))
            assert result is True


class TestValidateSessionId:
    """Tests for validate_session_id function"""
    
    def test_valid_session_id(self):
        """Test that valid session IDs are accepted"""
        result = validate_session_id("SESSION-123")
        assert result == "SESSION-123"
    
    def test_empty_session_id(self):
        """Test that empty session ID raises error"""
        with pytest.raises(InvalidInputError):
            validate_session_id("")
    
    def test_invalid_characters(self):
        """Test that invalid characters are rejected"""
        with pytest.raises(InvalidInputError):
            validate_session_id("SESSION/123")
    
    def test_path_traversal(self):
        """Test that path traversal is prevented"""
        with pytest.raises(InvalidInputError):
            validate_session_id("../etc")


class TestValidateSkillName:
    """Tests for validate_skill_name function"""
    
    def test_valid_skill_name(self):
        """Test that valid skill names are accepted"""
        result = validate_skill_name("brainstorming")
        assert result == "brainstorming"
    
    def test_empty_skill_name(self):
        """Test that empty skill name raises error"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("")
    
    def test_invalid_characters(self):
        """Test that invalid characters are rejected"""
        with pytest.raises(InvalidInputError):
            validate_skill_name("brain_storming")  # underscore not allowed


class TestValidateWorkspacePath:
    """Tests for validate_workspace_path function"""
    
    def test_empty_workspace(self):
        """Test that empty workspace raises error"""
        with pytest.raises(InvalidInputError):
            validate_workspace_path("")
    
    def test_valid_workspace(self):
        """Test that valid workspace is accepted"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_workspace_path(tmpdir)
            assert result == Path(tmpdir).resolve()
    
    def test_workspace_with_base_constraint(self):
        """Test workspace validation with base directory constraint"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "base"
            base.mkdir()
            workspace = base / "workspace"
            workspace.mkdir()
            
            result = validate_workspace_path(str(workspace), base_allowed_dir=base)
            assert result == workspace.resolve()
    
    def test_workspace_outside_base(self):
        """Test that workspace outside base is rejected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "base"
            base.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            
            with pytest.raises(PathTraversalError):
                validate_workspace_path(str(outside), base_allowed_dir=base)


class TestGetSecretFromEnv:
    """Tests for get_secret_from_env function"""
    
    def test_secret_exists(self):
        """Test retrieving existing secret"""
        os.environ["TEST_SECRET"] = "test_value"
        result = get_secret_from_env("TEST_SECRET")
        assert result == "test_value"
        del os.environ["TEST_SECRET"]
    
    def test_secret_not_found_no_default(self):
        """Test that missing secret without default raises error"""
        with pytest.raises(SecurityError):
            get_secret_from_env("NONEXISTENT_SECRET")
    
    def test_secret_not_found_with_default(self):
        """Test that missing secret with default returns default"""
        result = get_secret_from_env("NONEXISTENT_SECRET", default="default_value")
        assert result == "default_value"


class TestRedactSensitiveData:
    """Tests for redact_sensitive_data function"""
    
    def test_basic_redaction(self):
        """Test basic data redaction"""
        data = "My password is secret123"
        patterns = [r"secret\d+"]
        result = redact_sensitive_data(data, patterns)
        assert "secret123" not in result
        assert "[REDACTED]" in result
    
    def test_multiple_patterns(self):
        """Test redaction with multiple patterns"""
        data = "User: john, API key: abc123, Token: xyz789"
        patterns = [r"API key: \w+", r"Token: \w+"]
        result = redact_sensitive_data(data, patterns)
        assert "abc123" not in result
        assert "xyz789" not in result
        assert result.count("[REDACTED]") >= 2
    
    def test_case_insensitive(self):
        """Test case-insensitive redaction"""
        data = "PASSWORD: Secret123"
        patterns = [r"password:\s*\w+"]
        result = redact_sensitive_data(data, patterns)
        assert "Secret123" not in result

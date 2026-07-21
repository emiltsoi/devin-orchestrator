#!/usr/bin/env python3
"""
Unit tests for skill_invoker module validation
"""

# Add workflow-engine to path
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))

from skill_invoker import SkillInvocationResult, SkillInvoker


def test_config_overrides_valid():
    """Test that valid config_overrides are accepted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        # Create a minimal skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        yaml_file = skill_dir / "test-skill.yaml"
        yaml_file.write_text("iron_law: Test skill\nannouncement: Test\n")
        md_file = skill_dir / "test-skill.md"
        md_file.write_text("# Test skill\n")

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        # Valid config overrides
        valid_overrides = {
            "string_key": "value",
            "int_key": 42,
            "float_key": 3.14,
            "bool_key": True,
            "none_key": None,
        }

        result = invoker.invoke_skill(
            skill_name="test-skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
            config_overrides=valid_overrides
        )

        assert result.success is True


def test_config_overrides_invalid_type():
    """Test that non-dict config_overrides are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        # Create a minimal skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        yaml_file = skill_dir / "test-skill.yaml"
        yaml_file.write_text("iron_law: Test skill\nannouncement: Test\n")
        md_file = skill_dir / "test-skill.md"
        md_file.write_text("# Test skill\n")

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        # Invalid config overrides (not a dict)
        result = invoker.invoke_skill(
            skill_name="test-skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
            config_overrides="not_a_dict"
        )

        assert result.success is False
        # The error message now mentions malformed JSON since we try to parse strings as JSON
        assert "Invalid config_overrides" in result.error


def test_config_overrides_json_string():
    """Test that JSON string config_overrides are parsed correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        # Create a minimal skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        yaml_file = skill_dir / "test-skill.yaml"
        yaml_file.write_text("iron_law: Test skill\nannouncement: Test\n")
        md_file = skill_dir / "test-skill.md"
        md_file.write_text("# Test skill\n")

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        # Valid JSON string config overrides
        result = invoker.invoke_skill(
            skill_name="test-skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
            config_overrides='{"key": "value"}'
        )

        assert result.success is True


def test_config_overrides_invalid_key_type():
    """Test that non-string keys in config_overrides are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        # Create a minimal skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        yaml_file = skill_dir / "test-skill.yaml"
        yaml_file.write_text("iron_law: Test skill\nannouncement: Test\n")
        md_file = skill_dir / "test-skill.md"
        md_file.write_text("# Test skill\n")

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        # Invalid config overrides (non-string key)
        invalid_overrides = {123: "value"}

        result = invoker.invoke_skill(
            skill_name="test-skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
            config_overrides=invalid_overrides
        )

        assert result.success is False
        assert "config_overrides key must be string" in result.error


def test_config_overrides_invalid_value_type():
    """Test that invalid value types in config_overrides are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        # Create a minimal skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        yaml_file = skill_dir / "test-skill.yaml"
        yaml_file.write_text("iron_law: Test skill\nannouncement: Test\n")
        md_file = skill_dir / "test-skill.md"
        md_file.write_text("# Test skill\n")

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        # Invalid config overrides (non-basic type value)
        invalid_overrides = {"key": {"nested": "dict"}}

        result = invoker.invoke_skill(
            skill_name="test-skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
            config_overrides=invalid_overrides
        )

        assert result.success is False
        assert "config_overrides value for key 'key' must be basic type" in result.error


def test_config_overrides_list_value():
    """Test that list values in config_overrides are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        # Create a minimal skill
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        yaml_file = skill_dir / "test-skill.yaml"
        yaml_file.write_text("iron_law: Test skill\nannouncement: Test\n")
        md_file = skill_dir / "test-skill.md"
        md_file.write_text("# Test skill\n")

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        # Invalid config overrides (list value)
        invalid_overrides = {"key": ["list", "value"]}

        result = invoker.invoke_skill(
            skill_name="test-skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
            config_overrides=invalid_overrides
        )

        assert result.success is False
        assert "config_overrides value for key 'key' must be basic type" in result.error


def test_invoke_skill_rejects_path_traversal_name():
    """Test that invoke_skill rejects skill names with path traversal sequences."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        result = invoker.invoke_skill(
            skill_name="../../etc/passwd",
            context={"session_id": "test-001"},
            workspace=tmpdir,
        )

        assert result.success is False
        assert "Invalid skill name" in result.error


def test_invoke_skill_rejects_underscore_name():
    """Test that invoke_skill rejects skill names with underscores (skill names are hyphen-only)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills"
        skills_dir.mkdir()

        invoker = SkillInvoker(skills_dir=skills_dir, demo_mode=True)

        result = invoker.invoke_skill(
            skill_name="my_skill",
            context={"session_id": "test-001"},
            workspace=tmpdir,
        )

        assert result.success is False
        assert "Invalid skill name" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

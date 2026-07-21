#!/usr/bin/env python3
"""
Unit tests for deterministic_tools.load_skill frontmatter parsing
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))

from deterministic_tools import load_skill


def test_load_skill_frontmatter_lf():
    """Test that load_skill parses frontmatter with LF line endings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        skill_md = skills_dir / "my-skill.md"
        skill_md.write_text(
            "---\niron_law: Test law\nannouncement: Test\n---\n# Narrative\n",
            encoding="utf-8",
        )

        result = load_skill(skills_dir, "my-skill")

        assert result["format"] == "single"
        assert result["definition"]["iron_law"] == "Test law"
        assert "# Narrative" in result["narrative"]


def test_load_skill_frontmatter_crlf():
    """Test that load_skill parses frontmatter with CRLF (Windows) line endings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        skill_md = skills_dir / "my-skill.md"
        skill_md.write_bytes(
            b"---\r\niron_law: Test law\r\nannouncement: Test\r\n---\r\n# Narrative\r\n",
        )

        result = load_skill(skills_dir, "my-skill")

        assert result["format"] == "single"
        assert result["definition"]["iron_law"] == "Test law"
        assert "# Narrative" in result["narrative"]


def test_load_skill_separate_files_fallback():
    """Test that load_skill falls back to separate yaml+md files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        (skills_dir / "my-skill.yaml").write_text(
            "iron_law: Test law\n", encoding="utf-8"
        )
        (skills_dir / "my-skill.md").write_text("# Narrative\n", encoding="utf-8")

        result = load_skill(skills_dir, "my-skill")

        assert result["format"] == "separate"
        assert result["definition"]["iron_law"] == "Test law"
        assert "# Narrative" in result["narrative"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

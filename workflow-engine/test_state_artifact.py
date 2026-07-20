"""Tests for workflow-engine/state_artifact.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from state_artifact import (
    DEFAULT_STATE,
    REQUIRED_FIELDS,
    init_state,
    load_state,
    save_state,
)


class TestInitState:
    """init_state writes a normalized artifact and returns it."""

    def test_init_creates_file_with_defaults(self, tmp_path):
        path = tmp_path / "STATE.md"
        state = init_state(path, "GSD-001", "execute")
        assert path.exists()
        assert state["milestone"] == "GSD-001"
        assert state["phase"] == "execute"
        assert state["status"] == "in_progress"
        assert state["decisions"] == []
        assert state["blockers"] == []
        assert state["completed_plans"] == []
        assert state["pending_plans"] == []
        assert state["metrics"] == {}

    def test_init_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "STATE.md"
        init_state(path, "M", "P")
        assert path.exists()

    def test_init_writes_yaml_frontmatter(self, tmp_path):
        path = tmp_path / "STATE.md"
        init_state(path, "GSD-001", "execute")
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        # The closing delimiter must be on its own line.
        assert "\n---\n" in text
        # Frontmatter parses back to the expected mapping.
        body = text.split("---\n", 2)[1]
        parsed = yaml.safe_load(body)
        assert parsed["milestone"] == "GSD-001"
        assert parsed["phase"] == "execute"


class TestSaveAndLoad:
    """Round-trip save/load for both Markdown and JSON formats."""

    def test_save_md_round_trip(self, tmp_path):
        path = tmp_path / "STATE.md"
        original = {
            "milestone": "M1",
            "phase": "verify",
            "status": "blocked",
            "decisions": ["pick A"],
            "blockers": ["need info"],
            "completed_plans": ["p1"],
            "pending_plans": ["p2"],
            "metrics": {"lines": 100},
        }
        save_state(path, original)
        loaded = load_state(path)
        for key in REQUIRED_FIELDS:
            assert loaded[key] == original[key]

    def test_save_json_round_trip(self, tmp_path):
        path = tmp_path / "state.json"
        original = {
            "milestone": "M1",
            "phase": "verify",
            "status": "blocked",
            "decisions": ["pick A"],
            "blockers": [],
            "completed_plans": [],
            "pending_plans": ["p2"],
            "metrics": {"lines": 100},
        }
        save_state(path, original)
        loaded = load_state(path)
        for key in REQUIRED_FIELDS:
            assert loaded[key] == original[key]
        # File is valid JSON.
        text = path.read_text(encoding="utf-8")
        assert json.loads(text)["milestone"] == "M1"

    def test_save_fills_missing_required_fields(self, tmp_path):
        path = tmp_path / "STATE.md"
        save_state(path, {"milestone": "M", "phase": "P"})
        loaded = load_state(path)
        for key in REQUIRED_FIELDS:
            assert key in loaded
        assert loaded["status"] == DEFAULT_STATE["status"]
        assert loaded["decisions"] == []

    def test_save_preserves_unknown_fields(self, tmp_path):
        path = tmp_path / "STATE.md"
        save_state(path, {"milestone": "M", "phase": "P", "custom": "x"})
        loaded = load_state(path)
        assert loaded["custom"] == "x"
        # Known fields still present.
        assert loaded["milestone"] == "M"


class TestLoadEdgeCases:
    """load_state error handling and fallbacks."""

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_state(tmp_path / "nope.md")

    def test_load_json_content_in_md_file(self, tmp_path):
        # A .md file whose body is JSON should be accepted as a fallback.
        path = tmp_path / "STATE.md"
        path.write_text(
            json.dumps({"milestone": "M", "phase": "P"}, indent=2),
            encoding="utf-8",
        )
        loaded = load_state(path)
        assert loaded["milestone"] == "M"
        assert loaded["phase"] == "P"
        # Required fields filled in.
        assert loaded["status"] == "in_progress"

    def test_load_invalid_content_raises(self, tmp_path):
        path = tmp_path / "STATE.md"
        path.write_text("just prose, no frontmatter or json", encoding="utf-8")
        with pytest.raises(ValueError):
            load_state(path)

    def test_load_invalid_json_raises(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError):
            load_state(path)

    def test_load_crlf_frontmatter(self, tmp_path):
        # A STATE.md written with CRLF line endings must still parse.
        path = tmp_path / "STATE.md"
        body = "milestone: M\r\nphase: P\r\nstatus: blocked\r\n"
        path.write_bytes(b"---\r\n" + body.encode("utf-8") + b"---\r\n")
        loaded = load_state(path)
        assert loaded["milestone"] == "M"
        assert loaded["phase"] == "P"
        assert loaded["status"] == "blocked"
        # Required fields filled in.
        assert loaded["decisions"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

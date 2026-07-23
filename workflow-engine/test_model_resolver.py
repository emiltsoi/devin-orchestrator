"""Tests for workflow-engine/model_resolver.py."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import GlobalConfig
from model_resolver import resolve_model


@dataclass
class StubConfig:
    """Minimal stand-in matching the _ConfigLike protocol."""

    default_model: str = "swe-1.6"
    model_profile: str = ""
    models: dict[str, str] | None = None
    model_overrides: dict[str, str] | None = None


class TestResolveModelPrecedence:
    """Verify the documented 4-layer precedence."""

    def test_falls_back_to_default_model(self):
        cfg = StubConfig(default_model="swe-1.6")
        assert resolve_model("coder", "execute", cfg) == "swe-1.6"

    def test_default_model_when_agent_and_phase_none(self):
        cfg = StubConfig(default_model="glm-5-2")
        assert resolve_model(None, None, cfg) == "glm-5-2"

    def test_model_profile_wins_over_default(self):
        cfg = StubConfig(default_model="swe-1.6", model_profile="claude-sonnet-4")
        assert resolve_model(None, None, cfg) == "claude-sonnet-4"

    def test_models_phase_wins_over_profile(self):
        cfg = StubConfig(
            default_model="swe-1.6",
            model_profile="claude-sonnet-4",
            models={"verify": "glm-5-2"},
        )
        assert resolve_model(None, "verify", cfg) == "glm-5-2"

    def test_model_overrides_agent_wins_over_phase_and_profile(self):
        cfg = StubConfig(
            default_model="swe-1.6",
            model_profile="claude-sonnet-4",
            models={"execute": "glm-5-2"},
            model_overrides={"coder": "claude-opus-4.6"},
        )
        assert resolve_model("coder", "execute", cfg) == "claude-opus-4.6"

    def test_empty_override_falls_through(self):
        # An empty string in model_overrides[agent] should not win; it should
        # fall through to the next layer.
        cfg = StubConfig(
            default_model="swe-1.6",
            model_profile="claude-sonnet-4",
            model_overrides={"coder": ""},
        )
        assert resolve_model("coder", None, cfg) == "claude-sonnet-4"

    def test_empty_phase_model_falls_through(self):
        cfg = StubConfig(
            default_model="swe-1.6",
            model_profile="claude-sonnet-4",
            models={"execute": ""},
        )
        assert resolve_model(None, "execute", cfg) == "claude-sonnet-4"

    def test_empty_profile_falls_through(self):
        cfg = StubConfig(default_model="swe-1.6", model_profile="")
        assert resolve_model(None, None, cfg) == "swe-1.6"

    def test_unknown_agent_and_phase_fall_through(self):
        cfg = StubConfig(
            default_model="swe-1.6",
            models={"execute": "glm-5-2"},
            model_overrides={"coder": "claude-opus-4.6"},
        )
        # Unknown agent + unknown phase -> profile (empty) -> default
        assert resolve_model("reviewer", "verify", cfg) == "swe-1.6"

    def test_phase_match_with_unknown_agent(self):
        cfg = StubConfig(
            default_model="swe-1.6",
            models={"verify": "glm-5-2"},
            model_overrides={"coder": "claude-opus-4.6"},
        )
        assert resolve_model("reviewer", "verify", cfg) == "glm-5-2"


class TestResolveModelWithGlobalConfig:
    """resolve_model should work with a real GlobalConfig instance."""

    def test_with_empty_global_config(self, tmp_path):
        cfg = GlobalConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="/usr/bin/devin",
            default_model="swe-1.6",
            default_permission_mode="dangerous",
            session_work_dir=tmp_path / "work",
        )
        assert resolve_model("coder", "execute", cfg) == "swe-1.6"

    def test_with_populated_global_config(self, tmp_path):
        cfg = GlobalConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="/usr/bin/devin",
            default_model="swe-1.6",
            default_permission_mode="dangerous",
            session_work_dir=tmp_path / "work",
            model_profile="claude-sonnet-4",
            models={"verify": "glm-5-2"},
            model_overrides={"coder": "claude-opus-4.6"},
        )
        assert resolve_model("coder", "execute", cfg) == "claude-opus-4.6"
        assert resolve_model("reviewer", "verify", cfg) == "glm-5-2"
        assert resolve_model("reviewer", "execute", cfg) == "claude-sonnet-4"
        assert resolve_model("reviewer", "execute", cfg) != "swe-1.6"


class TestResolveModelNoneFields:
    """None maps/dicts on the config should not crash."""

    def test_none_dicts(self):
        cfg = StubConfig(
            default_model="swe-1.6",
            models=None,
            model_overrides=None,
        )
        assert resolve_model("coder", "execute", cfg) == "swe-1.6"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

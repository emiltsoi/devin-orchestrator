"""
Tests for config_loader.py

Covers environment variable expansion, path fallback behavior, permission
mode validation, and GlobalConfig dataclass access.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import (
    ALLOWED_PERMISSION_MODES,
    ConfigLoader,
    GlobalConfig,
)


class TestExpandEnvVars:
    """Tests for ConfigLoader.expand_env_vars"""

    def test_plain_string_returned_unchanged(self):
        assert ConfigLoader.expand_env_vars("plain-value") == "plain-value"

    def test_non_string_returned_unchanged(self):
        # Non-string inputs are passed through untouched.
        assert ConfigLoader.expand_env_vars(123) == 123
        assert ConfigLoader.expand_env_vars(None) is None

    def test_simple_var_expansion(self):
        with patch.dict(os.environ, {"FOO": "bar"}):
            assert ConfigLoader.expand_env_vars("${FOO}") == "bar"

    def test_missing_var_expands_to_empty(self):
        env_without = {k: v for k, v in os.environ.items() if k != "MISSING_VAR_XYZ"}
        with patch.dict(os.environ, env_without, clear=True):
            assert ConfigLoader.expand_env_vars("${MISSING_VAR_XYZ}") == ""

    def test_default_value_when_var_missing(self):
        env_without = {k: v for k, v in os.environ.items() if k != "MISSING_VAR_XYZ"}
        with patch.dict(os.environ, env_without, clear=True):
            assert ConfigLoader.expand_env_vars("${MISSING_VAR_XYZ:-fallback}") == "fallback"

    def test_default_value_ignored_when_var_set(self):
        with patch.dict(os.environ, {"FOO": "real"}):
            assert ConfigLoader.expand_env_vars("${FOO:-fallback}") == "real"

    def test_multiple_vars_in_one_string(self):
        with patch.dict(os.environ, {"A": "1", "B": "2"}):
            assert ConfigLoader.expand_env_vars("${A}/${B}") == "1/2"

    def test_empty_default(self):
        env_without = {k: v for k, v in os.environ.items() if k != "MISSING_VAR_XYZ"}
        with patch.dict(os.environ, env_without, clear=True):
            assert ConfigLoader.expand_env_vars("${MISSING_VAR_XYZ:-}") == ""


class TestLoadConfig:
    """Tests for ConfigLoader.load"""

    def test_load_returns_global_config(self, tmp_path):
        config = ConfigLoader.load(config_path=tmp_path / "missing.yaml")
        assert isinstance(config, GlobalConfig)

    def test_load_missing_file_uses_defaults(self, tmp_path):
        config = ConfigLoader.load(config_path=tmp_path / "missing.yaml")
        # Default model is "swe-1.6" and default permission mode is "dangerous".
        assert config.default_model == "swe-1.6"
        assert config.default_permission_mode == "dangerous"

    def test_load_from_config_file(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "global_root": str(tmp_path / "root"),
                    "skills_dir": str(tmp_path / "skills"),
                    "workflows_dir": str(tmp_path / "workflows"),
                    "workflow_engine_dir": str(tmp_path / "engine"),
                    "devin_cli_path": str(tmp_path / "devin.exe"),
                    "default_model": "custom-model",
                    "default_permission_mode": "smart",
                    "session_work_dir": str(tmp_path / "work"),
                }
            ),
            encoding="utf-8",
        )
        # Create directories so the fallback path logic doesn't kick in.
        for sub in ["root", "skills", "workflows", "engine", "work"]:
            (tmp_path / sub).mkdir()

        config = ConfigLoader.load(config_path=config_path)
        assert config.default_model == "custom-model"
        assert config.default_permission_mode == "smart"
        assert config.global_root == (tmp_path / "root")

    def test_load_expands_env_vars_in_config_values(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "default_model: ${MODEL_VAR:-from-default}\n", encoding="utf-8"
        )
        with patch.dict(os.environ, {"MODEL_VAR": "from-env"}):
            config = ConfigLoader.load(config_path=config_path)
            assert config.default_model == "from-env"

    def test_load_env_var_overrides_config_value(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump({"default_model": "from-config"}), encoding="utf-8"
        )
        with patch.dict(os.environ, {"DEVIN_DEFAULT_MODEL": "from-env-override"}):
            config = ConfigLoader.load(config_path=config_path)
            assert config.default_model == "from-env-override"

    def test_invalid_permission_mode_falls_back_to_dangerous(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump({"default_permission_mode": "bogus-mode"}),
            encoding="utf-8",
        )
        config = ConfigLoader.load(config_path=config_path)
        assert config.default_permission_mode == "dangerous"

    def test_empty_permission_mode_falls_back_to_dangerous(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump({"default_permission_mode": ""}), encoding="utf-8"
        )
        config = ConfigLoader.load(config_path=config_path)
        assert config.default_permission_mode == "dangerous"

    def test_env_permission_mode_override_validated(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump({"default_permission_mode": "smart"}), encoding="utf-8"
        )
        with patch.dict(os.environ, {"DEVIN_DEFAULT_PERMISSION_MODE": "invalid"}):
            config = ConfigLoader.load(config_path=config_path)
            assert config.default_permission_mode == "dangerous"

    def test_allowed_permission_modes_accepted(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        for mode in ALLOWED_PERMISSION_MODES:
            config_path.write_text(
                yaml.safe_dump({"default_permission_mode": mode}), encoding="utf-8"
            )
            config = ConfigLoader.load(config_path=config_path)
            assert config.default_permission_mode == mode

    def test_fallback_to_local_dirs_when_paths_missing(self, tmp_path):
        # When configured directories don't exist, the loader falls back to
        # the local repository layout (skills/, workflows/, workflow-engine/,
        # workflow-engine/work/).
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "skills_dir": str(tmp_path / "no-such-skills"),
                    "workflows_dir": str(tmp_path / "no-such-workflows"),
                    "workflow_engine_dir": str(tmp_path / "no-such-engine"),
                    "session_work_dir": str(tmp_path / "no-such-work"),
                }
            ),
            encoding="utf-8",
        )
        config = ConfigLoader.load(config_path=config_path)
        # All fallback paths should resolve inside the workflow-engine directory.
        assert config.workflow_engine_dir == Path(__file__).parent
        assert config.session_work_dir == Path(__file__).parent / "work"

    def test_default_config_path_fallback_to_repo_config(self, tmp_path, monkeypatch):
        # When DEFAULT_CONFIG_PATH doesn't exist, FALLBACK_CONFIG_PATH is used.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(
            ConfigLoader, "DEFAULT_CONFIG_PATH", fake_home / "config.yaml"
        )
        # Use the real fallback path (repo root config.yaml) so the test exercises
        # the fallback branch and still loads successfully.
        config = ConfigLoader.load()
        assert isinstance(config, GlobalConfig)


class TestGlobalConfig:
    """Tests for the GlobalConfig dataclass"""

    def test_dataclass_fields_present(self):
        fields = {
            "global_root",
            "skills_dir",
            "workflows_dir",
            "workflow_engine_dir",
            "devin_cli_path",
            "default_model",
            "default_permission_mode",
            "session_work_dir",
        }
        assert fields.issubset(set(GlobalConfig.__dataclass_fields__))

    def test_construction_preserves_values(self, tmp_path):
        cfg = GlobalConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="/usr/bin/devin",
            default_model="m1",
            default_permission_mode="auto",
            session_work_dir=tmp_path / "work",
        )
        assert cfg.default_permission_mode == "auto"
        assert cfg.default_model == "m1"
        assert cfg.devin_cli_path == "/usr/bin/devin"


class TestAllowedPermissionModes:
    """Sanity checks on the allowlist constant"""

    def test_allowlist_contains_expected_modes(self):
        assert ALLOWED_PERMISSION_MODES == frozenset({"dangerous", "smart", "auto"})

    def test_allowlist_is_frozen(self):
        assert isinstance(ALLOWED_PERMISSION_MODES, frozenset)

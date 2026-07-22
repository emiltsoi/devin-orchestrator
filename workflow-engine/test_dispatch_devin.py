"""Tests for dispatch_devin.py --agent / --phase / agent_skills wiring.

These tests exercise the ``main()`` entry point of the dispatcher with
monkeypatched config and a stubbed ``DevinCliAdapter`` so the real
``devin.exe`` binary is never invoked. They lock in:

* ``resolve_model`` precedence when ``--agent`` / ``--phase`` are provided.
* Stderr warnings for unknown ``--agent`` / ``--phase`` when the config has
  entries.
* Stderr warnings for missing / unknown ``agent_skills``.
* ``DevinCliAdapter`` is constructed and invoked with the correct ``model``,
  ``enable_skills``, and ``skill_filter`` values.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Make the workflow-engine importable (for config_loader etc.) and the repo
# root importable (for dispatch_devin itself).
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REPO_ROOT))

from config_loader import GlobalConfig  # noqa: E402

import dispatch_devin  # noqa: E402


@dataclass
class _StubConfig:
    """Minimal stand-in matching the config surface used by dispatch_devin."""

    devin_cli_path: str = "/usr/bin/devin"
    default_permission_mode: str = "dangerous"
    default_model: str = "swe-1.6"
    model_profile: str = ""
    models: dict[str, str] | None = None
    model_overrides: dict[str, str] | None = None
    agent_skills: dict[str, list[str]] | None = None
    skills_dir: Path = Path(".")  # noqa: RUF013


class _FakeAdapter:
    """Captures constructor and invoke arguments instead of running devin."""

    instances: list[_FakeAdapter] = []

    def __init__(self, devin_cli_path=None, workspace=None, model=None,
                 permission_mode=None, skills_dir=None, **_kwargs):
        self.devin_cli_path = devin_cli_path
        self.workspace = workspace
        self.model = model
        self.permission_mode = permission_mode
        self.skills_dir = skills_dir
        # Mirror the real adapter's ``.skills`` mapping so the missing-skill
        # warning path in dispatch_devin can introspect it.
        self.skills = {"using-devin-orchestrator": {}, "writing-plans": {}}
        self.invoke_calls: list[dict] = []
        _FakeAdapter.instances.append(self)

    def invoke(self, prompt, timeout=120, focused_context=None,
               correction_artifact=None, enable_skills=True,
               skill_filter=None):
        self.invoke_calls.append(
            {
                "prompt": prompt,
                "timeout": timeout,
                "focused_context": focused_context,
                "enable_skills": enable_skills,
                "skill_filter": skill_filter,
            }
        )
        # Return a simple result-like object.
        return type(
            "_Result",
            (),
            {"success": True, "output": "ok", "error": "", "exit_code": 0},
        )()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def role_and_prompt(tmp_path):
    """Create a minimal role file and prompt file under tmp_path."""
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    role_file = roles_dir / "coder.md"
    role_file.write_text("# Coder Role\n\nYou are a coder.", encoding="utf-8")
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("# Task\n\nDo the thing.", encoding="utf-8")
    return role_file, prompt_file


@pytest.fixture()
def patch_argv(monkeypatch):
    """Helper to set sys.argv for dispatch_devin.parse_args()."""

    def _set(*extra):
        argv = ["dispatch_devin.py"]
        argv.extend(extra)
        monkeypatch.setattr(sys, "argv", argv)

    return _set


@pytest.fixture()
def patch_config(monkeypatch):
    """Patch ConfigLoader.load to return a stub config."""

    def _apply(config: _StubConfig):
        monkeypatch.setattr(
            dispatch_devin.ConfigLoader, "load", staticmethod(lambda *a, **k: config)
        )

    return _apply


@pytest.fixture()
def patch_adapter(monkeypatch):
    """Patch DevinCliAdapter in dispatch_devin with the fake adapter."""
    _FakeAdapter.instances = []
    monkeypatch.setattr(dispatch_devin, "DevinCliAdapter", _FakeAdapter)
    return _FakeAdapter


class TestModelResolutionPrecedence:
    """--model wins; otherwise resolve_model(agent, phase, config) is used."""

    def test_explicit_model_wins(self, tmp_path, role_and_prompt, patch_argv,
                                 patch_config, patch_adapter):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                model_profile="claude-sonnet-4",
                models={"execute": "glm-5-2"},
                model_overrides={"coder": "claude-opus-4.6"},
            )
        )
        patch_argv(
            "--model", "explicit-model",
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "coder",
            "--phase", "execute",
        )
        assert dispatch_devin.main() == 0
        assert patch_adapter.instances[-1].model == "explicit-model"

    def test_agent_override_wins_when_no_model(self, tmp_path, role_and_prompt,
                                               patch_argv, patch_config,
                                               patch_adapter):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                model_profile="claude-sonnet-4",
                models={"execute": "glm-5-2"},
                model_overrides={"coder": "claude-opus-4.6"},
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "coder",
            "--phase", "execute",
        )
        assert dispatch_devin.main() == 0
        # model_overrides["coder"] wins over models["execute"] and profile.
        assert patch_adapter.instances[-1].model == "claude-opus-4.6"

    def test_phase_models_wins_when_agent_unknown(self, tmp_path, role_and_prompt,
                                                  patch_argv, patch_config,
                                                  patch_adapter):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                model_profile="claude-sonnet-4",
                models={"verify": "glm-5-2"},
                model_overrides={"coder": "claude-opus-4.6"},
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "reviewer",
            "--phase", "verify",
        )
        assert dispatch_devin.main() == 0
        # Unknown agent -> models["verify"] wins.
        assert patch_adapter.instances[-1].model == "glm-5-2"

    def test_profile_wins_when_agent_and_phase_unknown(self, tmp_path,
                                                       role_and_prompt,
                                                       patch_argv, patch_config,
                                                       patch_adapter):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                model_profile="claude-sonnet-4",
                models={"verify": "glm-5-2"},
                model_overrides={"coder": "claude-opus-4.6"},
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "reviewer",
            "--phase", "execute",
        )
        assert dispatch_devin.main() == 0
        assert patch_adapter.instances[-1].model == "claude-sonnet-4"


class TestUnknownAgentPhaseWarnings:
    """Stderr warnings are emitted for unknown --agent / --phase when the
    config has entries."""

    def test_unknown_phase_warns(self, tmp_path, role_and_prompt, patch_argv,
                                 patch_config, patch_adapter, capsys):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                models={"verify": "glm-5-2"},
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--phase", "bogus-phase",
        )
        assert dispatch_devin.main() == 0
        err = capsys.readouterr().err
        assert "bogus-phase" in err
        assert "config.models" in err

    def test_unknown_agent_warns(self, tmp_path, role_and_prompt, patch_argv,
                                 patch_config, patch_adapter, capsys):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                model_overrides={"coder": "claude-opus-4.6"},
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "bogus-agent",
        )
        assert dispatch_devin.main() == 0
        err = capsys.readouterr().err
        assert "bogus-agent" in err
        assert "config.model_overrides" in err

    def test_no_warning_when_config_empty(self, tmp_path, role_and_prompt,
                                          patch_argv, patch_config, patch_adapter,
                                          capsys):
        # If models / model_overrides are empty, no typo warning is emitted.
        role_file, prompt_file = role_and_prompt
        patch_config(_StubConfig(default_model="swe-1.6"))
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "anyone",
            "--phase", "anything",
        )
        assert dispatch_devin.main() == 0
        err = capsys.readouterr().err
        assert "config.models" not in err
        assert "config.model_overrides" not in err


class TestAgentSkillsWiring:
    """agent_skills maps agent names to skill_filter lists and enables skills."""

    def test_skills_enabled_and_filter_passed(self, tmp_path, role_and_prompt,
                                              patch_argv, patch_config,
                                              patch_adapter, capsys):
        role_file, prompt_file = role_and_prompt
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                agent_skills={
                    "coder": ["using-devin-orchestrator", "writing-plans"],
                },
                skills_dir=skills_dir,
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "coder",
        )
        assert dispatch_devin.main() == 0
        adapter = patch_adapter.instances[-1]
        # skills_dir is forwarded to the adapter constructor as a string.
        assert adapter.skills_dir == str(skills_dir)
        invoke = adapter.invoke_calls[-1]
        assert invoke["enable_skills"] is True
        assert invoke["skill_filter"] == ["using-devin-orchestrator", "writing-plans"]

    def test_missing_agent_skill_warns(self, tmp_path, role_and_prompt, patch_argv,
                                       patch_config, patch_adapter, capsys):
        role_file, prompt_file = role_and_prompt
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                agent_skills={
                    "coder": ["using-devin-orchestrator", "ghost-skill"],
                },
                skills_dir=skills_dir,
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "coder",
        )
        assert dispatch_devin.main() == 0
        err = capsys.readouterr().err
        assert "ghost-skill" in err
        assert "missing skills" in err
        # The filter is still passed through unchanged.
        invoke = patch_adapter.instances[-1].invoke_calls[-1]
        assert invoke["skill_filter"] == ["using-devin-orchestrator", "ghost-skill"]

    def test_unknown_agent_skills_warns(self, tmp_path, role_and_prompt, patch_argv,
                                        patch_config, patch_adapter, capsys):
        # agent has no entry in agent_skills map -> warning, no skills injected.
        role_file, prompt_file = role_and_prompt
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                agent_skills={"coder": ["writing-plans"]},
                skills_dir=skills_dir,
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--agent", "reviewer",
        )
        assert dispatch_devin.main() == 0
        err = capsys.readouterr().err
        assert "reviewer" in err
        assert "config.agent_skills" in err
        invoke = patch_adapter.instances[-1].invoke_calls[-1]
        assert invoke["enable_skills"] is False
        assert invoke["skill_filter"] is None

    def test_no_agent_no_skills(self, tmp_path, role_and_prompt, patch_argv,
                                patch_config, patch_adapter, capsys):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                default_model="swe-1.6",
                agent_skills={"coder": ["writing-plans"]},
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
        )
        assert dispatch_devin.main() == 0
        err = capsys.readouterr().err
        assert "config.agent_skills" not in err
        invoke = patch_adapter.instances[-1].invoke_calls[-1]
        assert invoke["enable_skills"] is False
        assert invoke["skill_filter"] is None


class TestAdapterConstructorAndInvoke:
    """DevinCliAdapter is constructed with the resolved model and the
    configured permission mode, and invoke receives the merged prompt."""

    def test_constructor_and_invoke_args(self, tmp_path, role_and_prompt,
                                         patch_argv, patch_config, patch_adapter):
        role_file, prompt_file = role_and_prompt
        patch_config(
            _StubConfig(
                devin_cli_path="/path/to/devin",
                default_permission_mode="smart",
                default_model="swe-1.6",
                model_profile="claude-sonnet-4",
            )
        )
        patch_argv(
            "--role", str(role_file),
            "--prompt-file", str(prompt_file),
            "--permission-mode", "auto",
            "--timeout", "42",
        )
        assert dispatch_devin.main() == 0
        adapter = patch_adapter.instances[-1]
        assert adapter.devin_cli_path == "/path/to/devin"
        assert adapter.permission_mode == "auto"
        assert adapter.model == "claude-sonnet-4"
        invoke = adapter.invoke_calls[-1]
        assert invoke["timeout"] == 42
        # The merged prompt contains both role and task content.
        assert "Coder Role" in invoke["prompt"]
        assert "Do the thing" in invoke["prompt"]


class TestResolveRoleFileShortNameValidation:
    """M-1: resolve_role_file must reject short names containing path
    separators or traversal segments so they cannot resolve outside roles/."""

    def test_traversal_short_name_rejected(self):
        with pytest.raises(FileNotFoundError):
            dispatch_devin.resolve_role_file("../evil")

    def test_path_separator_short_name_rejected(self):
        with pytest.raises(FileNotFoundError):
            dispatch_devin.resolve_role_file("evil/role")

    def test_dot_short_name_rejected(self):
        with pytest.raises(FileNotFoundError):
            dispatch_devin.resolve_role_file("evil.role")

    def test_valid_short_name_resolves_under_roles(self, tmp_path, monkeypatch):
        # Resolve against a tmp repo root so we don't depend on the real
        # roles/ directory shipping a specific role.
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        (roles_dir / "coder.md").write_text("# Coder\n", encoding="utf-8")

        # Point __file__-relative resolution at the tmp root by monkeypatching
        # Path(__file__).parent used inside resolve_role_file.
        monkeypatch.setattr(
            dispatch_devin, "__file__", str(tmp_path / "dispatch_devin.py")
        )
        resolved = dispatch_devin.resolve_role_file("coder")
        assert resolved == roles_dir / "coder.md"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

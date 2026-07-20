"""Tests for v1 skill loading in devin_cli_adapter.

Verifies that ``DevinCliAdapter._load_skills`` supports both the legacy
``SKILL.md`` layout (used by ``workflow-engine/skills/``) and the canonical
v1 layout (``<skill>/<skill>.md`` with YAML frontmatter, optional
``<skill>.yaml`` sidecar). Also covers the new ``skill_filter`` argument on
``invoke`` / ``_inject_skills``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from devin_cli_adapter import DevinCliAdapter


@pytest.fixture()
def v1_skills_dir(tmp_path):
    """Build a temporary skills dir with one v1 skill (with sidecar) and one
    v1 skill (frontmatter only)."""
    skills = tmp_path / "skills"
    skills.mkdir()

    # v1 skill with both .md frontmatter and .yaml sidecar.
    foo = skills / "foo"
    foo.mkdir()
    (foo / "foo.md").write_text(
        "---\n"
        'name: foo\n'
        'description: "Use when doing foo things."\n'
        "---\n\n"
        "# Foo\n\nBody of foo skill.\n",
        encoding="utf-8",
    )
    (foo / "foo.yaml").write_text(
        "schema_version: 1\n"
        "name: foo\n"
        'description: "Use when doing foo things."\n'
        "iron_law: \"do not skip\"\n",
        encoding="utf-8",
    )

    # v1 skill with frontmatter only (no sidecar).
    bar = skills / "bar"
    bar.mkdir()
    (bar / "bar.md").write_text(
        "---\n"
        'name: bar\n'
        'description: "Use when doing bar things."\n'
        "---\n\n"
        "# Bar\n\nBody of bar skill.\n",
        encoding="utf-8",
    )

    # v1 skill where frontmatter lacks name/description but the sidecar
    # provides them.
    baz = skills / "baz"
    baz.mkdir()
    (baz / "baz.md").write_text(
        "---\nother: 1\n---\n\n# Baz\n\nBody.\n",
        encoding="utf-8",
    )
    (baz / "baz.yaml").write_text(
        "name: baz\n"
        'description: "Use when doing baz things."\n',
        encoding="utf-8",
    )

    # A directory with no .md file at all should be skipped silently.
    empty = skills / "empty"
    empty.mkdir()

    return skills


@pytest.fixture()
def adapter(v1_skills_dir):
    """A DevinCliAdapter pointed at the v1 skills dir.

    Uses a throwaway workspace and a fake devin-cli path; we never invoke the
    CLI in these tests.
    """
    workspace = v1_skills_dir.parent / "workspace"
    workspace.mkdir()
    return DevinCliAdapter(
        devin_cli_path=str(v1_skills_dir.parent / "devin.exe"),
        workspace=str(workspace),
        skills_dir=str(v1_skills_dir),
    )


class TestV1SkillLoading:
    def test_loads_v1_skill_with_sidecar(self, adapter):
        assert "foo" in adapter.skills
        assert adapter.skills["foo"]["description"] == "Use when doing foo things."
        # Content is the full .md file text.
        assert adapter.skills["foo"]["content"].startswith("---\n")
        assert "# Foo" in adapter.skills["foo"]["content"]

    def test_loads_v1_skill_frontmatter_only(self, adapter):
        assert "bar" in adapter.skills
        assert adapter.skills["bar"]["description"] == "Use when doing bar things."

    def test_sidecar_fills_missing_frontmatter_fields(self, adapter):
        assert "baz" in adapter.skills
        assert adapter.skills["baz"]["description"] == "Use when doing baz things."

    def test_empty_dir_skipped(self, adapter):
        assert "empty" not in adapter.skills

    def test_all_three_v1_skills_loaded(self, adapter):
        assert set(adapter.skills.keys()) == {"foo", "bar", "baz"}


class TestLegacySkillLoading:
    """The legacy SKILL.md layout must still load correctly."""

    def test_legacy_layout_loads(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        legacy = skills / "ponytail"
        legacy.mkdir()
        (legacy / "SKILL.md").write_text(
            "---\n"
            'name: ponytail\n'
            'description: "Triggers on coding dispatches and implementation tasks."\n'
            "---\n\n"
            "# Ponytail\n\nBody.\n",
            encoding="utf-8",
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        adapter = DevinCliAdapter(
            devin_cli_path=str(tmp_path / "devin.exe"),
            workspace=str(workspace),
            skills_dir=str(skills),
        )
        assert "ponytail" in adapter.skills
        assert adapter.skills["ponytail"]["description"].startswith(
            "Triggers on coding dispatches"
        )


class TestSkillFilter:
    """skill_filter on _inject_skills / invoke restricts eligible skills."""

    def test_inject_skills_respects_filter(self, adapter):
        # skill_filter selects the eligible skill set. When a filter is provided,
        # those skills are injected unconditionally (this is the agent_skills
        # contract). Without a filter, auto-trigger matching uses the
        # ``triggers`` list from each skill's YAML sidecar/frontmatter.
        prompt = "coding dispatch and implementation task"

        # With no filter, no skill matches (foo/bar/baz have no trigger phrases).
        out_no_filter = adapter._inject_skills(prompt)
        assert out_no_filter == prompt

        # Add a ponytail skill whose triggers list matches the prompt.
        adapter.skills["ponytail"] = {
            "description": "",
            "content": "PONYTAIL-BODY",
            "triggers": ["coding dispatch", "implementation task"],
        }
        # No filter -> ponytail triggers on the prompt.
        out_all = adapter._inject_skills(prompt)
        assert "PONYTAIL-BODY" in out_all
        assert "# Foo" not in out_all
        assert "# Bar" not in out_all

        # A skill without a triggers field is not auto-triggered unfiltered.
        adapter.skills["notrigger"] = {
            "description": "",
            "content": "NOTRIGGER-BODY",
        }
        out_notrigger = adapter._inject_skills(prompt)
        assert "NOTRIGGER-BODY" not in out_notrigger

        # Filter excludes ponytail and includes foo/bar -> only foo/bar injected.
        out_filtered = adapter._inject_skills(prompt, skill_filter=["foo", "bar"])
        assert "PONYTAIL-BODY" not in out_filtered
        assert "# Foo" in out_filtered
        assert "# Bar" in out_filtered
        assert "# Baz" not in out_filtered

        # Filter includes only ponytail -> ponytail injected, foo/bar excluded.
        out_included = adapter._inject_skills(prompt, skill_filter=["ponytail"])
        assert "PONYTAIL-BODY" in out_included
        assert "# Foo" not in out_included
        assert "# Bar" not in out_included

    def test_invoke_passes_skill_filter(self, adapter, monkeypatch):
        # Verify invoke forwards skill_filter to _inject_skills.
        captured: dict = {}

        def fake_inject(prompt, skill_filter=None):
            captured["skill_filter"] = skill_filter
            return prompt

        monkeypatch.setattr(adapter, "_inject_skills", fake_inject)
        adapter.invoke("test prompt", enable_skills=True, skill_filter=["foo"])
        assert captured["skill_filter"] == ["foo"]

    def test_invoke_no_filter_passes_none(self, adapter, monkeypatch):
        captured: dict = {}

        def fake_inject(prompt, skill_filter=None):
            captured["skill_filter"] = skill_filter
            return prompt

        monkeypatch.setattr(adapter, "_inject_skills", fake_inject)
        adapter.invoke("test prompt", enable_skills=True)
        assert captured["skill_filter"] is None

    def test_invoke_disable_skills_skips_inject(self, adapter, monkeypatch):
        called = {"called": False}

        def fake_inject(prompt, skill_filter=None):
            called["called"] = True
            return prompt

        monkeypatch.setattr(adapter, "_inject_skills", fake_inject)
        adapter.invoke("test prompt", enable_skills=False, skill_filter=["foo"])
        assert called["called"] is False


class TestSkillsDirMissing:
    def test_missing_skills_dir_returns_empty(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        adapter = DevinCliAdapter(
            devin_cli_path=str(tmp_path / "devin.exe"),
            workspace=str(workspace),
            skills_dir=str(tmp_path / "does-not-exist"),
        )
        assert adapter.skills == {}


class TestTriggersAutoInjection:
    """Auto-trigger matching reads the ``triggers:`` list from the YAML sidecar
    (or frontmatter) instead of hardcoding skill names."""

    def _build(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        triggered = skills / "triggered-skill"
        triggered.mkdir()
        (triggered / "triggered-skill.md").write_text(
            "---\n"
            'name: triggered-skill\n'
            'description: "Use when something happens."\n'
            "---\n\n# Triggered\n\nBody.\n",
            encoding="utf-8",
        )
        (triggered / "triggered-skill.yaml").write_text(
            "schema_version: 1\n"
            "name: triggered-skill\n"
            'description: "Use when something happens."\n'
            "triggers:\n"
            "  - coding dispatch\n"
            "  - implementation task\n",
            encoding="utf-8",
        )
        plain = skills / "plain-skill"
        plain.mkdir()
        (plain / "plain-skill.md").write_text(
            "---\n"
            'name: plain-skill\n'
            'description: "Use when plain."\n'
            "---\n\n# Plain\n\nBody.\n",
            encoding="utf-8",
        )
        workspace = tmp_path / "ws"
        workspace.mkdir()
        return DevinCliAdapter(
            devin_cli_path=str(tmp_path / "devin.exe"),
            workspace=str(workspace),
            skills_dir=str(skills),
        )

    def test_triggers_loaded_from_sidecar(self, tmp_path):
        adapter = self._build(tmp_path)
        assert adapter.skills["triggered-skill"]["triggers"] == [
            "coding dispatch",
            "implementation task",
        ]
        # Skills without a triggers field get an empty list.
        assert adapter.skills["plain-skill"]["triggers"] == []

    def test_auto_trigger_matches_prompt_phrase(self, tmp_path):
        adapter = self._build(tmp_path)
        prompt = "This is a coding dispatch for the new feature."
        out = adapter._inject_skills(prompt)
        assert "# Triggered" in out
        assert "# Plain" not in out

    def test_no_trigger_no_injection(self, tmp_path):
        adapter = self._build(tmp_path)
        prompt = "Write a hello world program."
        out = adapter._inject_skills(prompt)
        assert out == prompt

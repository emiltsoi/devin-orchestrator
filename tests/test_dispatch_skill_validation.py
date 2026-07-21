#!/usr/bin/env python3
"""
Regression tests for dispatch_skill.py workspace validation base.

I-1: dispatch_skill.py must validate workspace against config.global_root
(not config.session_work_dir), matching the MCP server. Workspaces under
global_root but outside session_work_dir must pass validation.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from security_utils import SecurityError  # noqa: E402
from skill_invoker import SkillInvocationResult  # noqa: E402

import dispatch_skill  # noqa: E402


def _write_local_config(workspace: Path, base: Path) -> None:
    """Write a workspace-local config inside `workspace`.

    Sets global_root to `base` and session_work_dir to `base/work` so that
    `workspace` (under `base` but outside `base/work`) is accepted by
    global_root validation but would have been rejected by session_work_dir
    validation.
    """
    local_config_dir = workspace / ".devin-orchestrator"
    local_config_dir.mkdir(parents=True, exist_ok=True)
    (local_config_dir / "config.yaml").write_text(
        (
            f"global_root: {base}\n"
            f"skills_dir: {base / 'skills'}\n"
            f"workflows_dir: {base / 'workflows'}\n"
            f"session_work_dir: {base / 'work'}\n"
            "default_permission_mode: dangerous\n"
        ),
        encoding="utf-8",
    )
    for sub in ("skills", "workflows", "work"):
        (base / sub).mkdir(parents=True, exist_ok=True)


def _stub_invoker(monkeypatch, captured: dict) -> None:
    """Replace SkillInvoker in dispatch_skill with a recording stub."""

    class _StubInvoker:
        def __init__(self, *args, **kwargs):
            captured["init_kwargs"] = kwargs

        def invoke_skill(self, *, skill_name, context, workspace,
                         is_reviewer, config_overrides):
            captured["workspace"] = workspace
            captured["skill_name"] = skill_name
            return SkillInvocationResult(
                success=True,
                session_id=context["session_id"],
                output="ok",
                error=None,
            )

    monkeypatch.setattr(dispatch_skill, "SkillInvoker", _StubInvoker)


def test_dispatch_skill_accepts_workspace_under_global_root_outside_session_work(
    monkeypatch, capsys
):
    """A workspace under global_root but outside session_work_dir must pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "root"  # global_root
        base.mkdir(parents=True, exist_ok=True)
        # Workspace is under global_root but NOT under session_work_dir (base/work)
        workspace = base / "proj"
        workspace.mkdir(parents=True, exist_ok=True)
        _write_local_config(workspace, base=base)

        captured: dict = {}
        _stub_invoker(monkeypatch, captured)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dispatch_skill.py",
                "my-skill",
                "SESSION-001",
                str(workspace),
                "false",
                "false",
            ],
        )

        with pytest.raises(SystemExit) as exc_info:
            dispatch_skill.main()

        # Validation passed -> stub was called -> exit code 0
        assert exc_info.value.code == 0
        assert captured.get("workspace") == str(workspace)
        assert captured.get("skill_name") == "my-skill"

        # No validation error on stderr
        err = capsys.readouterr().err
        assert "Input validation error" not in err


def test_dispatch_skill_rejects_workspace_outside_global_root(
    monkeypatch, capsys
):
    """A workspace outside global_root must still be rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "root"  # global_root
        base.mkdir(parents=True, exist_ok=True)
        # Workspace is OUTSIDE global_root
        outside = Path(tmpdir) / "elsewhere"
        outside.mkdir(parents=True, exist_ok=True)
        # Local config inside `outside` still points global_root at `base`
        _write_local_config(outside, base=base)

        captured: dict = {}
        _stub_invoker(monkeypatch, captured)

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dispatch_skill.py",
                "my-skill",
                "SESSION-001",
                str(outside),
                "false",
                "false",
            ],
        )

        with pytest.raises(SecurityError):
            dispatch_skill.main()

        assert captured == {}  # invoker never reached


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

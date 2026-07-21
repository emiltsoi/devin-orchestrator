#!/usr/bin/env python3
"""
Security-focused unit tests for McpServer tool implementations.

Covers:
- _tool_read_artifact: workspace containment validation (C1)
- _tool_get_workflow: workflow name validation allowing underscores (I1)
- _tool_run_workflow: workflow name validation preventing manifest injection (I1)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server import McpServer


def _make_server_with_workspace(tmpdir: str) -> McpServer:
    """Build an McpServer whose config roots are contained inside tmpdir.

    Creates a workspace-local .devin-orchestrator/config.yaml so ConfigLoader
    resolves global_root / session_work_dir / skills_dir / workflows_dir under
    the temporary directory.
    """
    workspace = Path(tmpdir)
    local_config_dir = workspace / ".devin-orchestrator"
    local_config_dir.mkdir(parents=True, exist_ok=True)
    (local_config_dir / "config.yaml").write_text(
        (
            f"global_root: {workspace / 'root'}\n"
            f"skills_dir: {workspace / 'skills'}\n"
            f"workflows_dir: {workspace / 'workflows'}\n"
            f"session_work_dir: {workspace / 'work'}\n"
            "default_permission_mode: dangerous\n"
        ),
        encoding="utf-8",
    )
    for sub in ("root", "skills", "workflows", "work"):
        (workspace / sub).mkdir(exist_ok=True)
    return McpServer(workspace=str(workspace))


class TestReadArtifactWorkspaceContainment:
    """C1: _tool_read_artifact must validate workspace against global_root."""

    def test_read_artifact_rejects_workspace_outside_root(self):
        """A workspace outside global_root must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            # Create an outside directory with a secret file
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            secret = outside / "secret.txt"
            secret.write_text("TOPSECRET", encoding="utf-8")

            result = server._tool_read_artifact(
                {"path": "secret.txt", "workspace": str(outside)}
            )

            text = result[0]["text"]
            assert "Invalid workspace" in text
            assert "TOPSECRET" not in text

    def test_read_artifact_reads_file_inside_workspace(self):
        """A file inside an allowed workspace can be read."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            workspace = Path(tmpdir) / "root" / "proj"
            workspace.mkdir(parents=True)
            (workspace / "artifact.txt").write_text("hello", encoding="utf-8")

            result = server._tool_read_artifact(
                {"path": "artifact.txt", "workspace": str(workspace)}
            )

            assert result[0]["text"] == "hello"

    def test_read_artifact_falls_back_to_session_work_dir(self):
        """With no workspace/session_id, reads are contained to session_work_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)
            # Clear the pre-loaded workspace so neither argument nor server
            # workspace is set, exercising the session_work_dir fallback.
            server.workspace = None

            work_dir = Path(tmpdir) / "work"
            (work_dir / "note.txt").write_text("session-note", encoding="utf-8")

            result = server._tool_read_artifact({"path": "note.txt"})

            assert result[0]["text"] == "session-note"


class TestGetWorkflowNameValidation:
    """I1: _tool_get_workflow must accept underscored workflow names like code_review."""

    def test_get_workflow_accepts_underscore_name(self):
        """get_workflow('code_review') must not fail validation (file may be absent)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            workflows_dir = Path(tmpdir) / "workflows"
            manifest = workflows_dir / "code_review.manifest.yaml"
            manifest.write_text("description: review\n", encoding="utf-8")

            result = server._tool_get_workflow({"name": "code_review"})

            assert "# Manifest" in result[0]["text"]
            assert "review" in result[0]["text"]

    def test_get_workflow_rejects_traversal_name(self):
        """get_workflow must reject path-traversal workflow names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            result = server._tool_get_workflow({"name": "../etc/passwd"})

            assert "Invalid workflow name" in result[0]["text"]


class TestRunWorkflowNameValidation:
    """I1: _tool_run_workflow must validate the workflow name to prevent
    manifest injection from session directories."""

    def test_run_workflow_rejects_traversal_name(self):
        """run_workflow must reject path-traversal workflow names before
        reaching the orchestrator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            # Plant a fake manifest inside a session directory to simulate the
            # two-step attack described in I1. A traversal-style name should be
            # rejected by the MCP layer before the orchestrator is invoked.
            work_dir = Path(tmpdir) / "work"
            evil_dir = work_dir / "SESSION-001"
            evil_dir.mkdir(parents=True, exist_ok=True)
            (evil_dir / "evil.manifest.yaml").write_text(
                "description: evil\n", encoding="utf-8"
            )

            result = server._tool_run_workflow(
                {"workflow": "../work/SESSION-001/evil", "request": "do bad"}
            )

            text = result[0]["text"]
            assert "Invalid workflow name" in text
            # The planted manifest's content must never be executed/returned.
            assert "description: evil" not in text

    def test_run_workflow_rejects_path_separator_name(self):
        """run_workflow must reject workflow names containing path separators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            result = server._tool_run_workflow(
                {"workflow": "code/review", "request": "review me"}
            )

            assert "Invalid workflow name" in result[0]["text"]

    def test_run_workflow_rejects_missing_workflow_param(self):
        """run_workflow must report a clear error when workflow is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            result = server._tool_run_workflow({"request": "do something"})

            assert "Invalid workflow parameter" in result[0]["text"]


class TestGetSkillPathResolution:
    """C1: _tool_get_skill must resolve the skill directory against skills_dir
    instead of CWD, so valid skill names are not rejected by path validation."""

    def test_get_skill_reads_existing_skill(self):
        """get_skill for an existing skill returns its YAML/Markdown content,
        not a 'Path validation failed' error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            skills_dir = Path(tmpdir) / "skills"
            skill_dir = skills_dir / "my-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "my-skill.yaml").write_text(
                "description: demo skill\n", encoding="utf-8"
            )
            (skill_dir / "my-skill.md").write_text(
                "# my-skill narrative\n", encoding="utf-8"
            )

            result = server._tool_get_skill({"name": "my-skill"})

            text = result[0]["text"]
            assert "Path validation failed" not in text
            assert "# YAML" in text
            assert "demo skill" in text
            assert "# Markdown" in text
            assert "my-skill narrative" in text

    def test_get_skill_rejects_traversal_name(self):
        """get_skill must still reject path-traversal skill names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            result = server._tool_get_skill({"name": "../etc/passwd"})

            assert "Invalid skill name" in result[0]["text"]


class TestDispatchDevinRelativePaths:
    """I1: _tool_dispatch_devin must accept workspace-relative prompt_file and
    output_file paths, resolving them against work_dir rather than CWD."""

    def test_dispatch_devin_accepts_relative_prompt_file(self, monkeypatch):
        """A workspace-relative prompt_file must pass validation and reach the
        subprocess dispatch step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            work_dir = Path(tmpdir) / "root" / "proj"
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "prompt.md").write_text("do work", encoding="utf-8")

            captured: dict = {}

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                captured["cwd"] = kwargs.get("cwd")
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )

            monkeypatch.setattr(subprocess, "run", fake_run)

            result = server._tool_dispatch_devin(
                {
                    "role": "coder",
                    "prompt_file": "prompt.md",
                    "work_dir": str(work_dir),
                }
            )

            text = result[0]["text"]
            assert "Invalid prompt_file" not in text
            assert "Exit code: 0" in text
            # The prompt file path passed to the subprocess must resolve under
            # work_dir, not CWD.
            prompt_arg = captured["cmd"][
                captured["cmd"].index("--prompt-file") + 1
            ]
            assert str(work_dir / "prompt.md") == prompt_arg

    def test_dispatch_devin_accepts_relative_output_file(self, monkeypatch):
        """A workspace-relative output_file must pass validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            work_dir = Path(tmpdir) / "root" / "proj"
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "prompt.md").write_text("do work", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )

            monkeypatch.setattr(subprocess, "run", fake_run)

            result = server._tool_dispatch_devin(
                {
                    "role": "coder",
                    "prompt_file": "prompt.md",
                    "work_dir": str(work_dir),
                    "output_file": "out.log",
                }
            )

            text = result[0]["text"]
            assert "Invalid output_file" not in text
            assert "Invalid prompt_file" not in text
            assert "Exit code: 0" in text

    def test_dispatch_devin_rejects_prompt_file_outside_work_dir(self, monkeypatch):
        """A relative prompt_file that escapes work_dir via traversal must be
        rejected. PathTraversalError propagates out of the tool (mirroring the
        _tool_read_artifact pattern) and is surfaced as an error by
        _tools_call."""
        from security_utils import PathTraversalError

        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            work_dir = Path(tmpdir) / "root" / "proj"
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "prompt.md").write_text("do work", encoding="utf-8")

            # Plant a secret outside work_dir but inside the temp tree.
            outside = Path(tmpdir) / "secret.txt"
            outside.write_text("TOPSECRET", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )

            monkeypatch.setattr(subprocess, "run", fake_run)

            with pytest.raises(PathTraversalError):
                server._tool_dispatch_devin(
                    {
                        "role": "coder",
                        "prompt_file": "../../secret.txt",
                        "work_dir": str(work_dir),
                    }
                )

            # Also verify the public _tools_call path surfaces a graceful error
            # rather than dispatching or leaking the secret.
            response = server._tools_call(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "params": {
                        "name": "dispatch_devin",
                        "arguments": {
                            "role": "coder",
                            "prompt_file": "../../secret.txt",
                            "work_dir": str(work_dir),
                        },
                    },
                }
            )
            text = response["result"]["content"][0]["text"]
            assert response["result"]["isError"] is True
            assert "Path traversal" in text
            assert "TOPSECRET" not in text


class TestDispatchDevinTimeout:
    """I-1: _tool_dispatch_devin must not crash on subprocess.TimeoutExpired."""

    def test_dispatch_devin_timeout_returns_graceful_error(self, monkeypatch):
        """A timed-out Devin dispatch must return a clear error, not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            work_dir = Path(tmpdir) / "root" / "proj"
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "prompt.md").write_text("do work", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

            monkeypatch.setattr(subprocess, "run", fake_run)

            result = server._tool_dispatch_devin(
                {
                    "role": "coder",
                    "prompt_file": "prompt.md",
                    "work_dir": str(work_dir),
                    "timeout": 5,
                }
            )

            text = result[0]["text"]
            assert "timed out" in text.lower()
            assert "5" in text

    def test_dispatch_devin_timeout_surfaces_via_tools_call(self, monkeypatch):
        """The public _tools_call path must surface a graceful error response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            work_dir = Path(tmpdir) / "root" / "proj"
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "prompt.md").write_text("do work", encoding="utf-8")

            def fake_run(cmd, **kwargs):
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

            monkeypatch.setattr(subprocess, "run", fake_run)

            response = server._tools_call(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "params": {
                        "name": "dispatch_devin",
                        "arguments": {
                            "role": "coder",
                            "prompt_file": "prompt.md",
                            "work_dir": str(work_dir),
                            "timeout": 5,
                        },
                    },
                }
            )
            assert response["result"]["isError"] is False
            assert "timed out" in response["result"]["content"][0]["text"].lower()


class TestDispatchSkillTimeout:
    """I-1: _tool_dispatch_skill must not crash on subprocess.TimeoutExpired."""

    def test_dispatch_skill_timeout_returns_graceful_error(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            workspace = Path(tmpdir) / "root" / "proj"
            workspace.mkdir(parents=True, exist_ok=True)

            def fake_run(cmd, **kwargs):
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

            monkeypatch.setattr(subprocess, "run", fake_run)

            result = server._tool_dispatch_skill(
                {
                    "skill_name": "my-skill",
                    "session_id": "SESSION-001",
                    "workspace": str(workspace),
                    "timeout": 5,
                }
            )

            text = result[0]["text"]
            assert "timed out" in text.lower()
            assert "5" in text


class TestListSkillsMalformedYaml:
    """I-2: _tool_list_skills must skip malformed skill YAML instead of crashing."""

    def test_list_skills_skips_malformed_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            skills_dir = Path(tmpdir) / "skills"
            good_dir = skills_dir / "good-skill"
            good_dir.mkdir(parents=True, exist_ok=True)
            (good_dir / "good-skill.yaml").write_text(
                "description: good\n", encoding="utf-8"
            )

            bad_dir = skills_dir / "bad-skill"
            bad_dir.mkdir(parents=True, exist_ok=True)
            # Malformed YAML: unclosed flow mapping
            (bad_dir / "bad-skill.yaml").write_text(
                "description: [unclosed\n", encoding="utf-8"
            )

            result = server._tool_list_skills({})

            import json as _json
            data = _json.loads(result[0]["text"])
            names = [s["name"] for s in data]
            assert "good-skill" in names
            assert "bad-skill" not in names


class TestListWorkflowsMalformedYaml:
    """I-2: _tool_list_workflows must skip malformed manifests instead of crashing."""

    def test_list_workflows_skips_malformed_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            workflows_dir = Path(tmpdir) / "workflows"
            (workflows_dir / "good.manifest.yaml").write_text(
                "description: good\n", encoding="utf-8"
            )
            # Malformed YAML manifest
            (workflows_dir / "bad.manifest.yaml").write_text(
                "description: {unclosed\n", encoding="utf-8"
            )

            result = server._tool_list_workflows({})

            import json as _json
            data = _json.loads(result[0]["text"])
            names = [w["name"] for w in data]
            assert "good" in names
            assert "bad" not in names


class TestDispatchDevinOutputFileFromWorkDir:
    """M-1: _tool_dispatch_devin must read a relative output_file from work_dir,
    not CWD."""

    def test_relative_output_file_read_from_work_dir(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = _make_server_with_workspace(tmpdir)

            work_dir = Path(tmpdir) / "root" / "proj"
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / "prompt.md").write_text("do work", encoding="utf-8")
            # Write the output file inside work_dir
            (work_dir / "out.log").write_text(
                "OUTPUT-CONTENT", encoding="utf-8"
            )
            # Also write a same-named file at CWD to ensure it is NOT used.
            # (Don't actually pollute CWD; the absence at CWD plus presence
            # under work_dir proves the read resolves against work_dir.)

            def fake_run(cmd, **kwargs):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )

            monkeypatch.setattr(subprocess, "run", fake_run)

            result = server._tool_dispatch_devin(
                {
                    "role": "coder",
                    "prompt_file": "prompt.md",
                    "work_dir": str(work_dir),
                    "output_file": "out.log",
                }
            )

            text = result[0]["text"]
            assert "OUTPUT-CONTENT" in text
            assert "OUTPUT FILE" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

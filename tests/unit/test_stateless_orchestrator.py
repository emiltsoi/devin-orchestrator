"""
Tests for StatelessOrchestrator async dispatch helpers.
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from devin_orchestrator.stateless_orchestrator import StatelessOrchestrator


@pytest.fixture
def orchestrator(tmp_path):
    """Create a StatelessOrchestrator wired to a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".devin-orchestrator").mkdir()
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    cfg_path = workspace / ".devin-orchestrator" / "config.yaml"
    cfg_path.write_text(
        f"""
global_root: {tmp_path.as_posix()}
skills_dir: {skills_dir.as_posix()}
workflows_dir: {workflows_dir.as_posix()}
session_work_dir: {workspace.as_posix()}
""",
        encoding="utf-8",
    )
    return StatelessOrchestrator(workspace=str(workspace))


def test_run_workflow_async_starts_and_writes_result(orchestrator, tmp_path):
    """run_workflow_async returns immediately and writes result.json in thread."""
    workflows_dir = tmp_path / "workflows"
    (workflows_dir / "test.manifest.yaml").write_text(
        "name: test\nstages:\n  - name: s1\n    skill: brainstorming\n",
        encoding="utf-8",
    )

    with patch(
        "devin_orchestrator.stateless_orchestrator.OrchestrationEngine.execute_workflow"
    ) as mock_exec:
        mock_exec.return_value = {
            "session_id": "ignored",
            "final_status": "completed",
            "stages": [{"stage": "s1", "status": "completed"}],
        }
        result = orchestrator.run_workflow_async("test", "do it")

        assert result["status"] == "started"
        assert result["session_id"]
        session_dir = Path(result["workspace"])

        # Poll briefly for background thread to finish writing result.json
        for _ in range(20):
            if (session_dir / "result.json").exists():
                break
            time.sleep(0.05)

    result_file = session_dir / "result.json"
    assert result_file.exists()
    data = json.loads(result_file.read_text(encoding="utf-8"))
    assert data["final_status"] == "completed"

    status = orchestrator.get_workflow_status(result["session_id"])
    assert status["final_status"] == "completed"


def test_get_workflow_status_not_found(orchestrator):
    """A non-existent session reports not_found."""
    result = orchestrator.get_workflow_status("NOPE-001")
    assert result["status"] == "not_found"


def test_run_skill_async_starts_and_writes_result(orchestrator):
    """run_skill_async returns immediately and writes result.json in thread."""
    with patch(
        "devin_orchestrator.stateless_orchestrator.SkillInvoker.invoke_skill"
    ) as mock_invoke:
        mock_invoke.return_value = SimpleNamespace(
            success=True, output="ok", error=None
        )
        result = orchestrator.run_skill_async("brainstorming", "think")

        assert result["status"] == "started"
        assert result["session_id"].startswith("SKILL-")
        session_dir = Path(result["workspace"])

        for _ in range(20):
            if (session_dir / "result.json").exists():
                break
            time.sleep(0.05)

    result_file = session_dir / "result.json"
    assert result_file.exists()
    data = json.loads(result_file.read_text(encoding="utf-8"))
    assert data["success"] is True


def test_continue_workflow_async_starts_and_writes_result(orchestrator, tmp_path):
    """continue_workflow_async returns immediately and writes result.json in thread."""
    session_dir = tmp_path / "workspace" / "SESSION-001"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"session_id": "SESSION-001", "status": "waiting"}),
        encoding="utf-8",
    )

    with patch(
        "devin_orchestrator.stateless_orchestrator.OrchestrationEngine.continue_workflow"
    ) as mock_continue:
        mock_continue.return_value = {
            "session_id": "SESSION-001",
            "final_status": "completed",
            "stages": [{"stage": "s1", "status": "completed"}],
        }
        result = orchestrator.continue_workflow_async("SESSION-001")

        assert result["status"] == "started"

        for _ in range(20):
            if (session_dir / "result.json").exists():
                break
            time.sleep(0.05)

    result_file = session_dir / "result.json"
    assert result_file.exists()
    data = json.loads(result_file.read_text(encoding="utf-8"))
    assert data["final_status"] == "completed"


def test_execute_async_routes_to_implement(orchestrator, tmp_path):
    """execute_async auto-routes an implementation request to the superpower workflow."""
    workflows_dir = tmp_path / "workflows"
    (workflows_dir / "superpower.manifest.yaml").write_text(
        "name: superpower\nstages:\n  - name: s1\n    skill: brainstorming\n",
        encoding="utf-8",
    )

    with patch(
        "devin_orchestrator.stateless_orchestrator.OrchestrationEngine.execute_workflow"
    ) as mock_exec:
        mock_exec.return_value = {"final_status": "completed"}
        result = orchestrator.execute_async(
            "Add a new API endpoint", intent="implement"
        )

        assert result["status"] == "started"
        assert result["session_id"]

        session_dir = Path(result["workspace"])
        for _ in range(20):
            if (session_dir / "result.json").exists():
                break
            time.sleep(0.05)

    assert (session_dir / "result.json").exists()

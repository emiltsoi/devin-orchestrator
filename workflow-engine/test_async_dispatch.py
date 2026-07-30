"""
Tests for the async/cancel background dispatch flow.

These do not require a real Devin CLI; they exercise the MCP server and
StatelessOrchestrator helpers directly.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from stateless_orchestrator import StatelessOrchestrator  # noqa: E402

import mcp_server  # noqa: E402


@pytest.fixture
def server(tmp_path):
    """Create an McpServer wired to a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".devin-orchestrator").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "workflows").mkdir()
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir()
    (roles_dir / "coder.md").write_text("# coder role", encoding="utf-8")
    devin_cli = tmp_path / "devin" / "bin" / "devin.exe"
    devin_cli.parent.mkdir(parents=True, exist_ok=True)
    devin_cli.write_text("dummy", encoding="utf-8")
    cfg_path = workspace / ".devin-orchestrator" / "config.yaml"
    cfg_path.write_text(
        f"""
global_root: {tmp_path.as_posix()}
skills_dir: {(tmp_path / "skills").as_posix()}
workflows_dir: {(tmp_path / "workflows").as_posix()}
workflow_engine_dir: {(tmp_path / "engine").as_posix()}
session_work_dir: {workspace.as_posix()}
devin_cli_path: {devin_cli.as_posix()}
""",
        encoding="utf-8",
    )
    return mcp_server.McpServer(workspace=str(workspace))


def test_continue_workflow_passes_gate_arguments(server, tmp_path):
    """C1 regression: continue_workflow must forward gate/feedback/timeout args."""
    with patch.object(
        server,
        "_start_background_dispatch",
        return_value=[{"type": "text", "text": ""}],
    ) as mock_dispatch:
        server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "continue_workflow",
                    "arguments": {
                        "session_id": "S-001",
                        "gate_verdict": "approve",
                        "gate_notes": "lgtm",
                        "gate_id": "gate_review",
                        "correction_artifact": "/tmp/fix.md",
                        "feedback": "try again",
                        "timeout": 120,
                    },
                },
            }
        )

    assert mock_dispatch.called
    args, kwargs = mock_dispatch.call_args
    assert args[0] == "continue_workflow"
    extra = kwargs["extra_args"]
    assert extra["gate_verdict"] == "approve"
    assert extra["gate_notes"] == "lgtm"
    assert extra["gate_id"] == "gate_review"
    assert extra["correction_artifact"] == "/tmp/fix.md"
    assert extra["feedback"] == "try again"
    assert extra["timeout"] == 120


def test_start_background_dispatch_records_dispatcher_pid_for_continue(
    server, tmp_path
):
    """M8: for continue_workflow the dispatcher PID must be written before the ready wait."""
    session_id = "S-002"
    session_dir = server.config.session_work_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    proc = MagicMock()
    proc.pid = 12345
    proc.poll.return_value = None

    def wait_for_ready(ready_file, _proc, timeout):
        # Simulate the dispatcher writing the ready file.
        ready_file.write_text(
            json.dumps({"session_id": session_id, "workspace": str(session_dir)}),
            encoding="utf-8",
        )
        return {"session_id": session_id, "workspace": str(session_dir)}

    with patch("mcp_server.subprocess.Popen", return_value=proc) as mock_popen:
        with patch.object(server, "_wait_for_ready_file", side_effect=wait_for_ready):
            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "continue_workflow",
                        "arguments": {
                            "session_id": session_id,
                            "feedback": "retry",
                        },
                    },
                }
            )

    assert mock_popen.called
    pid_file = session_dir / "workflow-pid.txt"
    assert pid_file.exists()
    data = json.loads(pid_file.read_text(encoding="utf-8"))
    assert data["pid"] == 12345
    assert "create_time" in data


def test_cancel_workflow_does_not_cancel_completed_session(server, tmp_path):
    """L3: cancel must reject an already-completed session."""
    session_id = "S-003"
    session_dir = server.config.session_work_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.json").write_text(
        json.dumps({"final_status": "completed"}), encoding="utf-8"
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "cancel_workflow",
                "arguments": {"session_id": session_id},
            },
        }
    )

    text = response["result"]["content"][0]["text"]
    result = json.loads(text)
    assert result["success"] is False
    assert "already completed" in result["error"]


def test_cancel_workflow_skips_unrelated_process(server, tmp_path):
    """H2: verify process identity before killing a recorded PID."""
    session_id = "S-004"
    session_dir = server.config.session_work_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.json").write_text(json.dumps({}), encoding="utf-8")

    pid_file = session_dir / "pid.txt"
    pid_file.write_text(
        json.dumps({"pid": 99999, "create_time": time.time()}), encoding="utf-8"
    )

    orchestrator = StatelessOrchestrator(workspace=str(tmp_path / "workspace"))
    with patch.object(
        orchestrator,
        "_get_process_commandline",
        return_value=(["notepad.exe"], "notepad.exe"),
    ):
        with patch("stateless_orchestrator.subprocess.run") as mock_taskkill:
            result = orchestrator.cancel_workflow(session_id)

    assert result["success"] is True
    assert result["status"] == "cancelled"
    # Kill should have been skipped because the process is not one of ours.
    assert result["process_terminated"] is False
    mock_taskkill.assert_not_called()


def test_build_resume_detects_only_real_gates():
    """M4 regression: only stages starting with 'gate_' are gates."""
    orchestrator = StatelessOrchestrator()
    session_data = {
        "status": "waiting_for_input",
        "stages": [
            {"stage": "gather_context", "status": "completed"},
            {"stage": "generate_plan", "status": "completed"},
            {"stage": "gate_review", "status": "waiting"},
        ],
    }
    resume = orchestrator._build_resume_from_session("S-005", session_data, [])
    assert resume["tool"] == "mcp0_gate_decision"
    assert resume["arguments"]["gate_id"] == "review"


def test_kill_process_kills_matching_process(tmp_path):
    """H2: a process whose command line matches orchestrator markers is killed."""
    orchestrator = StatelessOrchestrator()
    with patch.object(
        orchestrator,
        "_get_process_commandline",
        return_value=(
            ["python", "dispatch_workflow.py"],
            "python dispatch_workflow.py",
        ),
    ):
        with patch("stateless_orchestrator.os.name", "posix"):
            with patch("stateless_orchestrator.os.kill") as mock_kill:
                killed = orchestrator._kill_process(42)

    assert killed is True
    # SIGTERM then the process is considered gone after the first signal.
    mock_kill.assert_any_call(42, 15)


def test_run_skill_is_background_dispatch(server, tmp_path):
    """M6: direct run_skill calls must also be dispatched in the background."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    skill_dir = skills_dir / "brainstorming"
    skill_dir.mkdir()
    (skill_dir / "brainstorming.yaml").write_text(
        "name: brainstorming\ndescription: Plan\n", encoding="utf-8"
    )

    with patch.object(
        server,
        "_start_background_dispatch",
        return_value=[{"type": "text", "text": ""}],
    ) as mock_dispatch:
        server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "run_skill",
                    "arguments": {
                        "skill": "brainstorming",
                        "request": "plan something",
                        "timeout": 90,
                    },
                },
            }
        )

    args, kwargs = mock_dispatch.call_args
    assert args[0] == "run_skill"
    assert kwargs["extra_args"]["skill"] == "brainstorming"
    assert kwargs["extra_args"]["timeout"] == 90

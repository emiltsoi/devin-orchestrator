"""
Tests for mcp_server.py

These tests exercise the MCP server's JSON-RPC message handling and tool
implementations without requiring a real Devin CLI.
"""

import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_server  # noqa: E402


@pytest.fixture
def server(tmp_path):
    """Create an McpServer wired to a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".devin-orchestrator").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "workflows").mkdir()
    cfg_path = workspace / ".devin-orchestrator" / "config.yaml"
    cfg_path.write_text(
        f"""
global_root: {tmp_path.as_posix()}
skills_dir: {(tmp_path / "skills").as_posix()}
workflows_dir: {(tmp_path / "workflows").as_posix()}
workflow_engine_dir: {(tmp_path / "engine").as_posix()}
session_work_dir: {workspace.as_posix()}
devin_cli_path: /usr/bin/devin
""",
        encoding="utf-8",
    )
    return mcp_server.McpServer(workspace=str(workspace))


def test_initialize():
    server = mcp_server.McpServer()
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == mcp_server.McpServer.PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["name"] == mcp_server.McpServer.SERVER_NAME


def test_initialized_notification_is_ignored():
    server = mcp_server.McpServer()
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
    )
    assert response is None


def test_tools_list():
    server = mcp_server.McpServer()
    response = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert response["id"] == 2
    tools = response["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "list_skills" in names
    assert "dispatch_devin" in names
    assert "read_artifact" in names


def test_unknown_method():
    server = mcp_server.McpServer()
    response = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "foo/bar", "params": {}}
    )
    assert response["error"]["code"] == -32601


def test_list_skills(server, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    skill_dir = skills_dir / "brainstorming"
    skill_dir.mkdir()
    (skill_dir / "brainstorming.yaml").write_text(
        "name: brainstorming\ndescription: Plan\n", encoding="utf-8"
    )
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "list_skills", "arguments": {}},
        }
    )
    assert response["id"] == 4
    text = response["result"]["content"][0]["text"]
    skills = json.loads(text)
    assert any(s["name"] == "brainstorming" for s in skills)


def test_get_skill(server, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    skill_dir = skills_dir / "brainstorming"
    skill_dir.mkdir()
    (skill_dir / "brainstorming.yaml").write_text(
        "name: brainstorming\ndescription: Plan\n", encoding="utf-8"
    )
    (skill_dir / "brainstorming.md").write_text(
        "# Brainstorming\nPlan\n", encoding="utf-8"
    )
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "get_skill", "arguments": {"name": "brainstorming"}},
        }
    )
    text = response["result"]["content"][0]["text"]
    assert "YAML" in text
    assert "Plan" in text


def test_list_workflows(server, tmp_path):
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    (workflows_dir / "superpower.manifest.yaml").write_text(
        "name: superpower\ndescription: Full methodology\nschema_version: 1\n",
        encoding="utf-8",
    )
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "list_workflows", "arguments": {}},
        }
    )
    text = response["result"]["content"][0]["text"]
    workflows = json.loads(text)
    assert any(w["name"] == "superpower" for w in workflows)


def test_get_workflow(server, tmp_path):
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    (workflows_dir / "superpower.manifest.yaml").write_text(
        "name: superpower\n", encoding="utf-8"
    )
    (workflows_dir / "superpower.runbook.md").write_text(
        "# Superpower\n", encoding="utf-8"
    )
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "get_workflow",
                "arguments": {"name": "superpower"},
            },
        }
    )
    text = response["result"]["content"][0]["text"]
    assert "Manifest" in text
    assert "Runbook" in text


def test_dispatch_devin_builds_command(server):
    with patch("mcp_server.subprocess.run") as mock_run:
        mock_run.return_value = Mock(
            returncode=0, stdout="ok", stderr="", args=[]
        )
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "dispatch_devin",
                    "arguments": {
                        "role": "coder",
                        "prompt_file": "/tmp/prompt.md",
                        "work_dir": "/tmp/ws",
                        "model": "glm-5-2",
                    },
                },
            }
        )
    assert response["result"]["isError"] is False
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "dispatch_devin.py" in cmd[-1] or "dispatch_devin.py" in str(cmd[1])
    assert "--role" in cmd
    assert "coder" in cmd
    assert "glm-5-2" in cmd


def test_dispatch_skill_builds_command(server):
    with patch("mcp_server.subprocess.run") as mock_run:
        mock_run.return_value = Mock(
            returncode=0, stdout='{"success": true}', stderr="", args=[]
        )
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "dispatch_skill",
                    "arguments": {
                        "skill_name": "brainstorming",
                        "session_id": "S1",
                        "workspace": "/tmp/ws",
                    },
                },
            }
        )
    assert response["result"]["isError"] is False
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "brainstorming" in cmd
    assert "S1" in cmd
    assert "/tmp/ws" in cmd


def test_read_artifact(server, tmp_path):
    workspace = tmp_path / "workspace"
    artifact = workspace / "result.md"
    artifact.write_text("# Result\n", encoding="utf-8")
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "read_artifact",
                "arguments": {"path": "result.md", "workspace": str(workspace)},
            },
        }
    )
    text = response["result"]["content"][0]["text"]
    assert "# Result" in text


def test_stdio_transport():
    """Round-trip a tools/list request through the stdio framing layer."""
    request = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/list",
        "params": {},
    }
    body = json.dumps(request).encode()
    stdin = BytesIO(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    stdout = BytesIO()
    server = mcp_server.McpServer()
    server.stdin = stdin
    server.stdout = stdout

    msg = server._read_message()
    response = server.handle(msg)
    server._write_message(response)

    stdout.seek(0)
    raw = stdout.read()
    # Parse the response framing
    header, rest = raw.split(b"\r\n\r\n", 1)
    length = int(header.split(b":", 1)[1].strip())
    payload = json.loads(rest[:length])
    assert payload["id"] == 11
    assert any(t["name"] == "list_skills" for t in payload["result"]["tools"])

"""
Tests for mcp_server.py

These tests exercise the MCP server's JSON-RPC message handling and tool
implementations without requiring a real Devin CLI.
"""

import base64
import json
import sys
import threading
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import devin_orchestrator.mcp_server as mcp_server


@pytest.fixture(autouse=True)
def _sync_threads(monkeypatch):
    """Run Thread.start() synchronously so dispatch tests are deterministic."""
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())


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


def test_initialize():
    server = mcp_server.McpServer()
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert (
        response["result"]["protocolVersion"] == mcp_server.McpServer.PROTOCOL_VERSION
    )
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
    work_dir = server.config.global_root / "devin_ws"
    work_dir.mkdir()
    prompt_file = work_dir / "prompt.md"
    prompt_file.write_text("# prompt", encoding="utf-8")

    with patch("devin_orchestrator.mcp_artifacts.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="", args=[])
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "dispatch_devin",
                    "arguments": {
                        "role": "coder",
                        "prompt_file": str(prompt_file),
                        "work_dir": str(work_dir),
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
    assert str(server.config.global_root / "roles" / "coder.md") in cmd
    assert "glm-5-2" in cmd


def test_dispatch_skill_builds_command(server):
    workspace = server.config.global_root / "skill_ws"
    workspace.mkdir()

    with patch("devin_orchestrator.mcp_artifacts.subprocess.run") as mock_run:
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
                        "workspace": str(workspace),
                    },
                },
            }
        )
    assert response["result"]["isError"] is False
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "brainstorming" in cmd
    assert "S1" in cmd
    assert str(workspace) in cmd


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


def test_read_artifact_offset_limit(server, tmp_path):
    """read_artifact respects 1-based offset and limit."""
    workspace = tmp_path / "workspace"
    (workspace / "note.txt").write_text(
        "line one\nline two\nline three\n", encoding="utf-8"
    )
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "read_artifact",
                "arguments": {
                    "path": "note.txt",
                    "workspace": str(workspace),
                    "offset": 2,
                    "limit": 1,
                },
            },
        }
    )
    assert response["result"]["isError"] is False
    assert response["result"]["content"][0]["text"] == "line two"


def test_read_artifact_binary_image(server, tmp_path):
    """Binary image files are returned as MCP image content."""
    workspace = tmp_path / "workspace"
    data = b"\x89PNG\r\n\x1a\n"
    (workspace / "img.png").write_bytes(data)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "read_artifact",
                "arguments": {"path": "img.png", "workspace": str(workspace)},
            },
        }
    )
    assert response["result"]["isError"] is False
    content = response["result"]["content"][0]
    assert content["type"] == "image"
    assert content["mimeType"] == "image/png"
    assert base64.b64decode(content["data"]) == data


def test_list_directory(server, tmp_path):
    """list_directory returns files and directories under a workspace."""
    workspace = tmp_path / "workspace"
    (workspace / "dir1").mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {
                "name": "list_directory",
                "arguments": {"path": ".", "workspace": str(workspace)},
            },
        }
    )
    assert response["result"]["isError"] is False
    entries = json.loads(response["result"]["content"][0]["text"])
    names = {e["name"] for e in entries}
    assert "a.txt" in names
    assert "dir1" in names


def test_list_artifacts(server, tmp_path):
    """list_artifacts returns files only, recursively."""
    workspace = tmp_path / "workspace"
    (workspace / "sub").mkdir()
    (workspace / "sub" / "b.txt").write_text("b", encoding="utf-8")
    (workspace / "dir2").mkdir()
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {
                "name": "list_artifacts",
                "arguments": {"path": ".", "workspace": str(workspace)},
            },
        }
    )
    assert response["result"]["isError"] is False
    entries = json.loads(response["result"]["content"][0]["text"])
    names = {e["name"] for e in entries}
    assert "b.txt" in names
    assert "dir2" not in names


def test_write_artifact(server, tmp_path):
    """write_artifact creates files under a workspace."""
    workspace = tmp_path / "workspace"
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {
                "name": "write_artifact",
                "arguments": {
                    "path": "new.txt",
                    "content": "hello",
                    "workspace": str(workspace),
                },
            },
        }
    )
    assert response["result"]["isError"] is False
    assert "Wrote" in response["result"]["content"][0]["text"]
    assert (workspace / "new.txt").read_text(encoding="utf-8") == "hello"


def test_apply_patch(server, tmp_path):
    """apply_patch applies a simple unified diff to a file."""
    workspace = tmp_path / "workspace"
    (workspace / "file.txt").write_text(
        "line1\nline2\nline3\n", encoding="utf-8"
    )
    patch = (
        "--- file.txt\n"
        "+++ file.txt\n"
        "@@ -2,2 +2,3 @@\n"
        " line2\n"
        "+line2.5\n"
        " line3\n"
    )
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 17,
            "method": "tools/call",
            "params": {
                "name": "apply_patch",
                "arguments": {
                    "path": "file.txt",
                    "patch": patch,
                    "workspace": str(workspace),
                },
            },
        }
    )
    assert response["result"]["isError"] is False
    text = (workspace / "file.txt").read_text(encoding="utf-8")
    assert "line2.5" in text


def test_list_sessions(server, tmp_path):
    """list_sessions returns session metadata for session work dir entries."""
    workspace = tmp_path / "workspace"
    (workspace / "SESSION-001").mkdir()
    (workspace / "SESSION-001" / "session.json").write_text(
        json.dumps({"status": "completed"}), encoding="utf-8"
    )
    (workspace / "DISPATCH-001").mkdir()
    (workspace / "DISPATCH-001" / "session.json").write_text(
        json.dumps({"status": "running"}), encoding="utf-8"
    )
    (workspace / "SKILL-001").mkdir()
    (workspace / "SKILL-001" / "session.json").write_text(
        json.dumps({"status": "completed"}), encoding="utf-8"
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 18,
            "method": "tools/call",
            "params": {
                "name": "list_sessions",
                "arguments": {"workspace": str(workspace)},
            },
        }
    )
    assert response["result"]["isError"] is False
    sessions = json.loads(response["result"]["content"][0]["text"])
    assert len(sessions) == 3
    types = {s["type"] for s in sessions}
    assert types == {"workflow", "dispatch", "skill"}

    # Filter to dispatch only
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 19,
            "method": "tools/call",
            "params": {
                "name": "list_sessions",
                "arguments": {"workspace": str(workspace), "session_type": "dispatch"},
            },
        }
    )
    sessions = json.loads(response["result"]["content"][0]["text"])
    assert len(sessions) == 1
    assert sessions[0]["type"] == "dispatch"

    # Limit
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {
                "name": "list_sessions",
                "arguments": {"workspace": str(workspace), "limit": 1},
            },
        }
    )
    sessions = json.loads(response["result"]["content"][0]["text"])
    assert len(sessions) == 1


def test_cancel_session(server, tmp_path):
    """cancel_session marks a session as cancelling."""
    workspace = tmp_path / "workspace"
    session_dir = workspace / "SESSION-002"
    session_dir.mkdir()
    (session_dir / "session.json").write_text(
        json.dumps({"status": "running"}), encoding="utf-8"
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "cancel_session",
                "arguments": {
                    "session_id": "SESSION-002",
                    "workspace": str(workspace),
                },
            },
        }
    )
    assert response["result"]["isError"] is False
    result = json.loads(response["result"]["content"][0]["text"])
    assert result["status"] == "cancelling"

    data = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    assert data["status"] == "cancelling"


def test_initialize_reports_resource_capability():
    """The initialize response advertises resources support."""
    server = mcp_server.McpServer()
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert "resources" in response["result"]["capabilities"]


def test_resources_templates_list(server):
    """resources/templates/list returns workspace and session templates."""
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "resources/templates/list",
            "params": {},
        }
    )
    templates = response["result"]["resourceTemplates"]
    assert any(t["uriTemplate"] == "workspace://{path}" for t in templates)
    assert any(t["uriTemplate"] == "session://{session_id}/{path}" for t in templates)


def test_resources_list_workspace(server, tmp_path):
    """resources/list exposes workspace files as workspace:// resources."""
    workspace = tmp_path / "workspace"
    (workspace / "resource.txt").write_text("hello resources", encoding="utf-8")

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "resources/list",
            "params": {},
        }
    )
    uris = {r["uri"] for r in response["result"]["resources"]}
    assert "workspace://resource.txt" in uris


def test_resources_list_session(server, tmp_path):
    """resources/list exposes session artifact files as session:// resources."""
    workspace = tmp_path / "workspace"
    session_dir = workspace / "SESSION-003"
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{}", encoding="utf-8")
    (session_dir / "artifact.txt").write_text("session artifact", encoding="utf-8")

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "resources/list",
            "params": {},
        }
    )
    uris = {r["uri"] for r in response["result"]["resources"]}
    assert "session://SESSION-003/artifact.txt" in uris


def test_resources_read_workspace(server, tmp_path):
    """resources/read returns text content for a workspace:// resource."""
    workspace = tmp_path / "workspace"
    (workspace / "read.txt").write_text("resource content", encoding="utf-8")

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 25,
            "method": "resources/read",
            "params": {"uri": "workspace://read.txt"},
        }
    )
    contents = response["result"]["contents"][0]
    assert contents["uri"] == "workspace://read.txt"
    assert contents["text"] == "resource content"


def test_resources_read_session(server, tmp_path):
    """resources/read returns text content for a session:// resource."""
    workspace = tmp_path / "workspace"
    session_dir = workspace / "SESSION-004"
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{}", encoding="utf-8")
    (session_dir / "artifact.txt").write_text("session content", encoding="utf-8")

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 26,
            "method": "resources/read",
            "params": {"uri": "session://SESSION-004/artifact.txt"},
        }
    )
    contents = response["result"]["contents"][0]
    assert contents["uri"] == "session://SESSION-004/artifact.txt"
    assert contents["text"] == "session content"


def test_resources_read_binary(server, tmp_path):
    """resources/read returns a base64 blob for binary files."""
    workspace = tmp_path / "workspace"
    (workspace / "binary.dat").write_bytes(b"\x80\x81\x82")

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 27,
            "method": "resources/read",
            "params": {"uri": "workspace://binary.dat"},
        }
    )
    contents = response["result"]["contents"][0]
    assert "blob" in contents
    assert base64.b64decode(contents["blob"]) == b"\x80\x81\x82"


def test_missing_required_argument(server):
    """tools/call returns a clear error when required arguments are missing."""
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 28,
            "method": "tools/call",
            "params": {"name": "get_skill", "arguments": {}},
        }
    )
    assert response["result"]["isError"] is True
    assert "Missing required arguments: name" in response["result"]["content"][0]["text"]


def test_close_is_idempotent(server):
    """McpServer.close can be called repeatedly without failing."""
    server.close()
    server.close()
    assert server._closed is True

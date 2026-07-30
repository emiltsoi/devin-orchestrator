"""Integration tests for MCP server JSON-RPC interface."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def _mcp_message(msg_id, method, params=None) -> bytes:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {},
        }
    )
    header = f"Content-Length: {len(payload)}\r\n\r\n"
    return (header + payload).encode("utf-8")


def _read_response(stream) -> dict | None:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
    content_length = 0
    for line in header.decode("utf-8").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
    if not content_length:
        return None
    body = stream.read(content_length)
    return json.loads(body.decode("utf-8"))


def test_mcp_server_initializes_and_lists_tools(tmp_path: Path):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "devin_orchestrator.mcp_server",
            "--workspace",
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(_mcp_message(1, "initialize", {"protocolVersion": "2024-11-05"}))
        proc.stdin.flush()

        init_response = _read_response(proc.stdout)
        assert init_response is not None
        assert "result" in init_response
        assert init_response["result"].get("protocolVersion") == "2024-11-05"

        proc.stdin.write(_mcp_message(2, "tools/list"))
        proc.stdin.flush()

        tools_response = _read_response(proc.stdout)
        assert tools_response is not None
        assert "result" in tools_response
        tools = tools_response["result"].get("tools", [])
        tool_names = {t["name"] for t in tools}
        assert "health" in tool_names
        assert "run_workflow" in tool_names
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


def test_mcp_server_health_tool(tmp_path: Path):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "devin_orchestrator.mcp_server",
            "--workspace",
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(_mcp_message(1, "initialize", {"protocolVersion": "2024-11-05"}))
        proc.stdin.flush()
        _read_response(proc.stdout)

        proc.stdin.write(
            _mcp_message(
                2,
                "tools/call",
                {"name": "health", "arguments": {"work_dir": str(tmp_path)}},
            )
        )
        proc.stdin.flush()

        health_response = _read_response(proc.stdout)
        assert health_response is not None
        assert "result" in health_response
        content = health_response["result"].get("content", [])
        assert content
        data = json.loads(content[0]["text"])
        assert "overall_status" in data
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)

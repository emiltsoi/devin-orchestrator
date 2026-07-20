#!/usr/bin/env python3
"""
MCP server for devin-orchestrator.

Exposes skills, workflows, and dispatch scripts as MCP tools over stdio using
JSON-RPC 2.0 with Content-Length framing. Clients such as Claude Desktop,
Cursor, OpenClaw, or any other MCP-compatible agent can connect to this server
and dispatch Devin workers without learning bash paths.

Usage:
    py -3.14 mcp_server.py [--workspace <path>]

The optional --workspace pre-loads a workspace-local config from
<workspace>/.devin-orchestrator/config.yaml. Tool arguments can still supply
arbitrary work_dir / workspace paths at call time.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

# Add workflow-engine to Python path so we can import ConfigLoader and
# security_utils without requiring the harness to be installed as a package.
WORKFLOW_ENGINE_DIR = Path(__file__).parent / "workflow-engine"
sys.path.insert(0, str(WORKFLOW_ENGINE_DIR))

from config_loader import ConfigLoader  # noqa: E402
from security_utils import validate_path_safe  # noqa: E402


class McpServer:
    """Minimal stdio MCP server backed by the devin-orchestrator harness."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "devin-orchestrator"
    SERVER_VERSION = "0.1.0"

    def __init__(self, workspace: str | None = None) -> None:
        self.workspace = workspace
        self.config = ConfigLoader.load(workspace=workspace)
        self.stdin = sys.stdin.buffer
        self.stdout = sys.stdout.buffer

    # --------------------------------------------------------------------- #
    # Tool definitions (exposed via tools/list)
    # --------------------------------------------------------------------- #
    @staticmethod
    def _tool_specs() -> list[dict]:
        return [
            {
                "name": "list_skills",
                "description": "List all available devin-orchestrator skills.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_skill",
                "description": "Get the YAML definition and markdown narrative for a skill.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill name (must match a directory under skills/)",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "list_workflows",
                "description": "List all available workflow manifests.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_workflow",
                "description": "Get a workflow manifest and its runbook.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Workflow name (e.g. superpower, code_review)",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "dispatch_devin",
                "description": "Dispatch a generic Devin run with a role and prompt file.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "description": "Role name (coder, reviewer, etc.) or path to role markdown",
                        },
                        "prompt_file": {
                            "type": "string",
                            "description": "Absolute or workspace-relative path to the prompt markdown file",
                        },
                        "work_dir": {
                            "type": "string",
                            "description": "Workspace directory where Devin runs and writes outputs",
                        },
                        "model": {"type": "string"},
                        "agent": {"type": "string"},
                        "phase": {"type": "string"},
                        "output_file": {"type": "string"},
                        "focused_context": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Paths to include as focused context",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds",
                            "default": 600,
                        },
                    },
                    "required": ["role", "prompt_file", "work_dir"],
                },
            },
            {
                "name": "dispatch_skill",
                "description": "Invoke a named skill in a target workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "session_id": {"type": "string"},
                        "workspace": {"type": "string"},
                        "is_reviewer": {"type": "boolean", "default": False},
                        "demo_mode": {"type": "boolean", "default": False},
                        "config_overrides": {"type": "object", "default": {}},
                    },
                    "required": ["skill_name", "session_id", "workspace"],
                },
            },
            {
                "name": "read_artifact",
                "description": "Read a file from a workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "workspace": {"type": "string"},
                    },
                    "required": ["path"],
                },
            },
        ]

    # --------------------------------------------------------------------- #
    # JSON-RPC message handling
    # --------------------------------------------------------------------- #
    def handle(self, request: dict) -> dict | None:
        """Dispatch a single JSON-RPC request. Notifications return None."""
        method = request.get("method")
        if method == "initialize":
            return self._initialize(request)
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return self._tools_list(request)
        if method == "tools/call":
            return self._tools_call(request)
        return self._error(request, -32601, f"Method not found: {method}")

    def _initialize(self, request: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": self.SERVER_NAME,
                    "version": self.SERVER_VERSION,
                },
            },
        }

    def _tools_list(self, request: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": self._tool_specs()},
        }

    def _tools_call(self, request: dict) -> dict:
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            content = self._run_tool(name, arguments)
            is_error = False
        except Exception as e:
            content = [self._text_content(f"Error: {e}")]
            is_error = True
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"content": content, "isError": is_error},
        }

    def _error(self, request: dict, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": code, "message": message},
        }

    # --------------------------------------------------------------------- #
    # Tool implementations
    # --------------------------------------------------------------------- #
    def _run_tool(self, name: str, arguments: dict) -> list[dict]:
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            raise ValueError(f"Unknown tool: {name}")
        return method(arguments)

    @staticmethod
    def _text_content(text: str) -> dict:
        return {"type": "text", "text": text}

    def _tool_list_skills(self, _arguments: dict) -> list[dict]:
        skills_dir = self.config.skills_dir
        skills = []
        if skills_dir.exists():
            for entry in sorted(skills_dir.iterdir()):
                yaml_file = entry / f"{entry.name}.yaml"
                if entry.is_dir() and yaml_file.exists():
                    data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                    skills.append(
                        {
                            "name": entry.name,
                            "description": data.get("description", ""),
                            "iron_law": data.get("iron_law", ""),
                        }
                    )
        return [self._text_content(json.dumps(skills, indent=2))]

    def _tool_get_skill(self, arguments: dict) -> list[dict]:
        name = arguments["name"]
        skill_dir = self.config.skills_dir / name
        yaml_file = skill_dir / f"{name}.yaml"
        md_file = skill_dir / f"{name}.md"
        if not yaml_file.exists():
            raise FileNotFoundError(f"Skill not found: {name}")
        parts = ["# YAML\n", yaml_file.read_text(encoding="utf-8")]
        if md_file.exists():
            parts.extend(["\n# Markdown\n", md_file.read_text(encoding="utf-8")])
        return [self._text_content("".join(parts))]

    def _tool_list_workflows(self, _arguments: dict) -> list[dict]:
        workflows_dir = self.config.workflows_dir
        workflows = []
        if workflows_dir.exists():
            for manifest in sorted(workflows_dir.glob("*.manifest.yaml")):
                data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                workflows.append(
                    {
                        "name": manifest.stem.replace(".manifest", ""),
                        "description": data.get("description", ""),
                        "schema_version": data.get("schema_version", ""),
                    }
                )
        return [self._text_content(json.dumps(workflows, indent=2))]

    def _tool_get_workflow(self, arguments: dict) -> list[dict]:
        name = arguments["name"]
        workflows_dir = self.config.workflows_dir
        manifest = workflows_dir / f"{name}.manifest.yaml"
        runbook = workflows_dir / f"{name}.runbook.md"
        if not manifest.exists():
            raise FileNotFoundError(f"Workflow not found: {name}")
        parts = ["# Manifest\n", manifest.read_text(encoding="utf-8")]
        if runbook.exists():
            parts.extend(["\n# Runbook\n", runbook.read_text(encoding="utf-8")])
        return [self._text_content("".join(parts))]

    def _tool_dispatch_devin(self, arguments: dict) -> list[dict]:
        script = Path(__file__).parent / "dispatch_devin.py"
        cmd = [sys.executable, str(script)]
        if arguments.get("model"):
            cmd.extend(["--model", str(arguments["model"])])
        if arguments.get("agent"):
            cmd.extend(["--agent", str(arguments["agent"])])
        if arguments.get("phase"):
            cmd.extend(["--phase", str(arguments["phase"])])
        cmd.extend(["--role", str(arguments["role"])])
        cmd.extend(["--prompt-file", str(arguments["prompt_file"])])
        cmd.extend(["--work-dir", str(arguments["work_dir"])])
        if arguments.get("output_file"):
            cmd.extend(["--output-file", str(arguments["output_file"])])
        for ctx in arguments.get("focused_context", []):
            cmd.extend(["--focused-context", str(ctx)])
        if arguments.get("timeout"):
            cmd.extend(["--timeout", str(arguments["timeout"])])

        timeout = int(arguments.get("timeout", 600))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(arguments["work_dir"]),
        )
        text = f"Exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}"
        if result.stderr:
            text += f"\n\nSTDERR:\n{result.stderr}"
        if arguments.get("output_file"):
            out_path = Path(arguments["output_file"])
            if out_path.exists():
                text += f"\n\n--- OUTPUT FILE ({out_path}) ---\n"
                text += out_path.read_text(encoding="utf-8")
        return [self._text_content(text)]

    def _tool_dispatch_skill(self, arguments: dict) -> list[dict]:
        script = Path(__file__).parent / "dispatch_skill.py"
        cmd = [
            sys.executable,
            str(script),
            str(arguments["skill_name"]),
            str(arguments["session_id"]),
            str(arguments["workspace"]),
            str(arguments.get("is_reviewer", False)).lower(),
            str(arguments.get("demo_mode", False)).lower(),
        ]
        overrides = arguments.get("config_overrides", {})
        if overrides:
            cmd.append(json.dumps(overrides))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        text = f"Exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}"
        if result.stderr:
            text += f"\n\nSTDERR:\n{result.stderr}"
        return [self._text_content(text)]

    def _tool_read_artifact(self, arguments: dict) -> list[dict]:
        path = Path(arguments["path"])
        workspace = arguments.get("workspace") or self.workspace
        base = Path(workspace) if workspace else Path.cwd()
        if path.is_absolute():
            target = validate_path_safe(base, path, allow_absolute=True)
        else:
            target = validate_path_safe(base, base / path, allow_absolute=True)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        return [self._text_content(target.read_text(encoding="utf-8"))]

    # --------------------------------------------------------------------- #
    # stdio transport
    # --------------------------------------------------------------------- #
    def _read_message(self) -> dict | None:
        headers: dict[str, str] = {}
        while True:
            line = self.stdin.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            # Strip trailing CRLF/LF
            if line.endswith(b"\r\n"):
                line = line[:-2]
            elif line.endswith(b"\n"):
                line = line[:-1]
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.strip().lower().decode()] = value.strip().decode()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = self.stdin.read(length)
        return json.loads(body)

    def _write_message(self, message: dict) -> None:
        body = json.dumps(message).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        self.stdout.write(header + body)
        self.stdout.flush()

    def run(self) -> None:
        while True:
            request = self._read_message()
            if request is None:
                break
            response = self.handle(request)
            if response is not None:
                self._write_message(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="devin-orchestrator MCP server")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Optional workspace path to pre-load local config from",
    )
    args = parser.parse_args()
    server = McpServer(workspace=args.workspace)
    server.run()


if __name__ == "__main__":
    main()

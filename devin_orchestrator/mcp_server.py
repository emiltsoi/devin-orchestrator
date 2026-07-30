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
import atexit
import base64
import binascii
import contextlib
import json
import logging
import mimetypes
import os
import re
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from devin_orchestrator.stateless_orchestrator import StatelessOrchestrator

logger = logging.getLogger(__name__)

# security_utils without requiring the harness to be installed as a package.

try:
    import yaml
except ModuleNotFoundError as e:
    raise SystemExit(
        "The PyYAML package is required. Install it with: pip install PyYAML>=5.1"
    ) from e

from devin_orchestrator import __version__  # noqa: E402
from devin_orchestrator.config_loader import ConfigLoader  # noqa: E402
from devin_orchestrator.deterministic_tools import session_init  # noqa: E402
from devin_orchestrator.log_rotate import (  # noqa: E402
    cleanup_old_logs,
    rotate_if_needed,
)
from devin_orchestrator.mcp_artifacts import (  # noqa: E402
    McpCallLogger,
    SubprocessArtifactRunner,
)
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    parse_config_overrides,
    validate_path_safe,
    validate_session_id,
    validate_skill_name,
    validate_workflow_name,
    validate_workspace_path,
)
from devin_orchestrator.session_manager import create_session  # noqa: E402


class McpServer:
    """Minimal stdio MCP server backed by the devin-orchestrator harness."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "devin-orchestrator"
    SERVER_VERSION = __version__
    MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    # Maximum bytes of subprocess output to keep per stdout/stderr stream.
    # Larger outputs are truncated before being returned to MCP clients.
    MAX_OUTPUT_BYTES = 5 * 1024 * 1024  # 5 MB
    # Rate limiting: max 10 calls per tool per 60-second window
    RATE_LIMIT_MAX_CALLS = 10
    RATE_LIMIT_WINDOW_SECONDS = 60
    # Timeout validation: min 1 second, max 1 hour (3600 seconds)
    DEFAULT_TIMEOUT_SECONDS = 300
    MIN_TIMEOUT_SECONDS = 1
    MAX_TIMEOUT_SECONDS = 3600

    DEFAULT_MESSAGE_LOG = (
        Path.home() / ".devin-orchestrator" / "logs" / "mcp-server.jsonl"
    )
    DEFAULT_MCP_CALLS_LOG = (
        McpCallLogger.DEFAULT_LOG_DIR / "mcp-calls.jsonl"
    )

    def __init__(
        self,
        workspace: str | None = None,
        message_log_path: str | None = None,
        mcp_calls_log_path: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.config = ConfigLoader.load(workspace=workspace)
        self.stdin = sys.stdin.buffer
        self.stdout = sys.stdout.buffer
        self._framing: str | None = None  # "ndjson" or "content-length"
        # Rate limiting: track tool call timestamps per tool name
        self._tool_call_history: defaultdict[str, list[float]] = defaultdict(list)
        self._message_log: IO[str] | None = None
        if message_log_path is not None:
            self._open_message_log(message_log_path)
        self._calls_log = McpCallLogger(mcp_calls_log_path)
        self._closed = False
        self._tool_required: dict[str, list[str]] = {
            tool["name"]: tool.get("inputSchema", {}).get("required", [])
            for tool in self._tool_specs()
        }
        atexit.register(self.close)

    def _open_message_log(self, message_log_path: str) -> None:
        """Open the NDJSON message log file, creating its directory if needed."""
        try:
            log_path = Path(message_log_path).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            rotate_if_needed(log_path)
            cleanup_old_logs(log_path.parent, pattern="*.ndjson", max_age_days=7)
            self._message_log = open(  # noqa: SIM115
                log_path, "a", encoding="utf-8", buffering=1
            )
            logger.info("MCP message log: %s", log_path)
        except (OSError, ValueError) as e:
            logger.warning("Cannot open MCP message log %s: %s", message_log_path, e)
            self._message_log = None

    def _log_message(self, direction: str, payload: dict[str, Any] | bytes) -> None:
        """Append a JSON-RPC message (or raw bytes) to the message log."""
        if self._message_log is None:
            return
        try:
            if isinstance(payload, bytes):
                message: Any = {"_raw": payload.decode("utf-8", errors="replace")}
            else:
                message = payload
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "direction": direction,
                "message": message,
            }
            self._message_log.write(json.dumps(entry, default=str) + "\n")
        except (OSError, TypeError) as e:
            logger.warning("Failed to write to MCP message log: %s", e)

    def close(self) -> None:
        """Flush and close log files. Idempotent; safe to call multiple times."""
        if self._closed:
            return
        self._closed = True
        if self._message_log is not None:
            with contextlib.suppress(OSError):
                self._message_log.flush()
                self._message_log.close()
            self._message_log = None
        self._calls_log.close()
        # Give background threads a brief window to finish writing artifacts
        try:
            from devin_orchestrator.stateless_orchestrator import _join_active_threads
            _join_active_threads(timeout=2.0)
        except Exception:
            pass

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
                "description": "MCP tool: dispatch a focused, single-shot Devin worker. Best for targeted implementation fixes or reviews where you specify exact acceptance criteria, focused files, and an output file. For full feature development prefer `implement` or `run_workflow`; for process skills prefer `run_skill`. Do not run `dispatch_devin.py` directly; use this tool.",
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
                        "model": {
                            "type": "string",
                            "description": "Model to use for the worker (e.g. swe-1.6). Overrides default routing.",
                        },
                        "agent": {
                            "type": "string",
                            "description": "Optional agent identifier or override.",
                        },
                        "phase": {
                            "type": "string",
                            "description": "Optional workflow phase context.",
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path where the worker writes a structured execution report.",
                        },
                        "focused_context": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Paths to include as focused context",
                        },
                        "permission_mode": {
                            "type": "string",
                            "description": "Devin permission mode (e.g. dangerous); defaults to config",
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
                "description": "MCP tool: invoke a named skill as a Devin worker in a target workspace. This dispatches a fresh subagent to follow the skill; prefer `execute`, `implement`, or `dispatch_devin` for most tasks. Do not run `dispatch_skill.py` directly; use this tool.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "session_id": {"type": "string"},
                        "workspace": {"type": "string"},
                        "is_reviewer": {"type": "boolean", "default": False},
                        "demo_mode": {"type": "boolean", "default": False},
                        "config_overrides": {"type": "object", "default": {}},
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds",
                            "default": 600,
                        },
                    },
                    "required": ["skill_name", "session_id", "workspace"],
                },
            },
            {
                "name": "read_artifact",
                "description": "Read a file from a workspace or session directory. Text files support optional line offset/limit and are truncated to a max size. Binary files are returned as base64 (images as MCP image content).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "offset": {
                            "type": "integer",
                            "description": "1-based starting line for text files",
                            "default": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of lines to return for text files",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "list_directory",
                "description": "List files and directories under a validated workspace or session path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "recursive": {"type": "boolean", "default": False},
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum directory depth when recursive",
                            "default": 3,
                        },
                    },
                },
            },
            {
                "name": "list_artifacts",
                "description": "List files recursively in a session directory or workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "recursive": {"type": "boolean", "default": True},
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum directory depth when recursive",
                            "default": 10,
                        },
                    },
                },
            },
            {
                "name": "write_artifact",
                "description": "Write or overwrite a text or base64 file under a validated workspace or session path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "encoding": {
                            "type": "string",
                            "description": "'utf-8' for text, 'base64' for binary",
                            "default": "utf-8",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "apply_patch",
                "description": "Apply a unified diff patch to a file under a validated workspace or session path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "patch": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["path", "patch"],
                },
            },
            {
                "name": "execute",
                "description": "Main entry point. Execute a request with automatic intent routing, starting the matched workflow/skill in the background. Prefer this for general requests. Use query_workflow_status to poll for completion.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The user request to execute",
                        },
                        "intent": {
                            "type": "string",
                            "description": "Intent to use (auto, implement, review, investigate, plan)",
                            "default": "auto",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "implement",
                "description": "Implement a feature or fix using the full `superpower` workflow (brainstorming, worktrees, plan, subagent-driven development, tests, review, completion). Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The implementation request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "review",
                "description": "Review code changes using the `code_review` workflow. Use for code diff review, PR review, or general code quality evaluation. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The review request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "investigate",
                "description": "Investigate an incident, bug, or failure using the `rca` workflow. Read-only; no git write operations. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The investigation request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "plan",
                "description": "Create a detailed implementation plan using the `writing-plans` skill. Produces a plan.md with bite-sized tasks. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The planning request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "run_workflow",
                "description": "Run a named workflow (superpower, code_review, rca, pr_review) with a request. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "string",
                            "description": "Name of the workflow to run",
                        },
                        "request": {
                            "type": "string",
                            "description": "The user request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["workflow", "request"],
                },
            },
            {
                "name": "gate_decision",
                "description": "Submit a human/agent decision for a workflow gate.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "gate_id": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "description": "approve | request_changes | block",
                        },
                        "notes": {"type": "string"},
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id", "gate_id", "verdict"],
                },
            },
            {
                "name": "continue_workflow",
                "description": "Resume a workflow that is paused at a gate. Optionally supply a gate verdict. The workflow resumes in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "gate_verdict": {
                            "type": "string",
                            "description": "Optional verdict to write before resuming (approve | request_changes | block)",
                        },
                        "gate_notes": {"type": "string"},
                        "gate_id": {"type": "string"},
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "query_workflow_status",
                "description": "Poll the status of a started or continued workflow. Returns session status, stages, and the final result once available.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID returned by run_workflow/continue_workflow/execute/implement/review/investigate/plan/run_skill",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "run_skill",
                "description": "Run a process skill (e.g. brainstorming, writing-plans, systematic-debugging) in a fresh session. Starts in the background; use query_workflow_status to poll. NOT for implementation or code-fix tasks; use `implement`, `run_workflow`, or `dispatch_devin` for those.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "description": "Name of the process skill to run (e.g. brainstorming, writing-plans, systematic-debugging). Avoid implementation skills like executing-plans here; prefer implement/run_workflow/dispatch_devin.",
                        },
                        "request": {
                            "type": "string",
                            "description": "The request to process. For broad implementation requests, the server may direct you to a more appropriate tool.",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["skill", "request"],
                },
            },
            {
                "name": "list_sessions",
                "description": "List sessions in the configured session work directory. Returns session_id, type, status, and last update time.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_type": {
                            "type": "string",
                            "description": "Filter by session type: all, workflow, dispatch, skill",
                            "default": "all",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of sessions to return (0 for all)",
                            "default": 0,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                },
            },
            {
                "name": "cancel_session",
                "description": "Request cancellation of a running or waiting workflow, skill, or dispatch session.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID to cancel",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id"],
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
        if method == "prompts/list":
            return self._prompts_list(request)
        if method == "prompts/get":
            return self._prompts_get(request)
        if method == "resources/list":
            return self._resources_list(request)
        if method == "resources/read":
            return self._resources_read(request)
        if method == "resources/templates/list":
            return self._resources_templates_list(request)
        if method == "resources/subscribe":
            return self._resources_subscribe(request)
        if method == "resources/unsubscribe":
            return self._resources_unsubscribe(request)
        return self._error(request, -32601, f"Method not found: {method}")

    def _initialize(self, request: dict) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                "serverInfo": {
                    "name": self.SERVER_NAME,
                    "version": self.SERVER_VERSION,
                },
            },
        }

    def _tools_list(self, request: dict) -> dict:
        tools = self._tool_specs()
        # Order tools so agents see high-level/intent tools before low-level dispatch/skill tools.
        tool_order = {
            "execute": 0,
            "implement": 1,
            "review": 2,
            "investigate": 3,
            "plan": 4,
            "run_workflow": 5,
            "run_skill": 6,
            "dispatch_devin": 7,
            "dispatch_skill": 8,
            "read_artifact": 9,
            "list_directory": 10,
            "list_artifacts": 11,
            "write_artifact": 12,
            "apply_patch": 13,
            "list_skills": 14,
            "get_skill": 15,
            "list_workflows": 16,
            "get_workflow": 17,
            "gate_decision": 18,
            "continue_workflow": 19,
            "query_workflow_status": 20,
            "list_sessions": 21,
            "cancel_session": 22,
        }
        tools.sort(key=lambda tool: tool_order.get(str(tool.get("name") or ""), 100))
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"tools": tools},
        }

    def _prompts_list(self, request: dict) -> dict:
        """Return the list of available MCP prompts."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "prompts": [
                    {
                        "name": "devin-orchestrator-usage",
                        "description": "Usage guide for the devin-orchestrator MCP server.",
                    }
                ]
            },
        }

    def _prompts_get(self, request: dict) -> dict:
        """Return the devin-orchestrator usage prompt content."""
        params = request.get("params", {})
        prompt_name = params.get("name")
        if prompt_name != "devin-orchestrator-usage":
            return self._error(request, -32602, f"Unknown prompt: {prompt_name}")

        usage_text = """# Devin Orchestrator MCP Usage

Pick the highest-level tool that matches your task. All workflow and skill tools now start in the background and return a session_id; use query_workflow_status to poll.

1. execute — main entry point; auto-routes by intent.
2. implement — full superpower workflow for feature/bug-fix implementation.
3. review — code_review workflow for code or PR review.
4. investigate — rca workflow for root-cause analysis (read-only).
5. plan — writing-plans skill to produce an implementation plan.
6. run_workflow — run a specific named workflow.
7. run_skill — process skills only (brainstorming, writing-plans, systematic-debugging).
8. gate_decision — write a verdict for a waiting gate.
9. continue_workflow — resume a workflow after a gate decision.
10. query_workflow_status — poll status and result for any session_id.
11. list_sessions — list sessions with status, type, and last update.
12. cancel_session — request cancellation of a running session.
13. dispatch_devin — focused single-shot worker with prompt_file, focused_context, model, output_file.

Do NOT use run_skill for implementation tasks. It has no focused_context and bypasses the workflow gates. For coding work, use implement, run_workflow, or dispatch_devin.
"""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": usage_text},
                    }
                ]
            },
        }

    def _extract_session_id(self, content: list[dict]) -> str | None:
        """Best-effort parse of a session_id from a tool response."""
        if not content or content[0].get("type") != "text":
            return None
        text = content[0].get("text", "")
        # Quick heuristic: background tools return JSON containing session_id.
        if not text.strip().startswith("{"):
            return None
        try:
            data = json.loads(text)
            return data.get("session_id") or data.get("sessionId")
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    def _tools_call(self, request: dict) -> dict:
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        call_id = f"{name}-{time.time()}"
        start = time.time()

        # Validate required arguments and rate limit
        missing = [
            arg
            for arg in self._tool_required.get(str(name), [])
            if arg not in arguments
        ]
        if missing:
            content = [
                self._text_content(f"Missing required arguments: {', '.join(missing)}")
            ]
            is_error = True
        elif not self._check_rate_limit(name):
            content = [
                self._text_content(
                    f"Rate limit exceeded for tool '{name}'. Maximum {self.RATE_LIMIT_MAX_CALLS} calls per {self.RATE_LIMIT_WINDOW_SECONDS} seconds."
                )
            ]
            is_error = True
        else:
            try:
                content = self._run_tool(name, arguments)
                is_error = False
            except (
                FileNotFoundError,
                ValueError,
                InvalidInputError,
                PathTraversalError,
            ) as e:
                content = [self._text_content(f"Error: {e}")]
                is_error = True
            except (KeyError, TypeError) as e:
                content = [self._text_content(f"Invalid arguments: {e}")]
                is_error = True
            except (OSError, RuntimeError) as e:
                content = [self._text_content(f"System error: {e}")]
                is_error = True

        duration_ms = round((time.time() - start) * 1000, 3)
        session_id = self._extract_session_id(content)
        error_text = content[0].get("text", "") if is_error and content else None
        response_summary = None
        if content and not is_error and content[0].get("type") == "text":
            text = content[0].get("text", "")
            response_summary = text[:1000] + "..." if len(text) > 1000 else text

        log_record = {
            "call_id": call_id,
            "tool": name,
            "arguments": arguments,
            "session_id": session_id,
            "workspace": arguments.get("work_dir") or arguments.get("workspace"),
            "is_error": is_error,
            "error": error_text,
            "duration_ms": duration_ms,
            "response_summary": response_summary,
        }
        self._calls_log.log_call(log_record)
        if session_id:
            self._calls_log.append_session_call(
                self.config.session_work_dir, session_id, log_record
            )

        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"content": content, "isError": is_error},
        }

    def _check_rate_limit(self, tool_name: str) -> bool:
        """
        Check if the tool call is within rate limits.

        Args:
            tool_name: Name of the tool being called

        Returns:
            True if the call is allowed, False if rate limit is exceeded
        """
        current_time = time.time()
        # Clean up old calls outside the time window
        self._tool_call_history[tool_name] = [
            timestamp
            for timestamp in self._tool_call_history[tool_name]
            if current_time - timestamp < self.RATE_LIMIT_WINDOW_SECONDS
        ]

        # Check if under the limit
        if len(self._tool_call_history[tool_name]) >= self.RATE_LIMIT_MAX_CALLS:
            return False

        # Record this call
        self._tool_call_history[tool_name].append(current_time)
        return True

    def _validate_timeout(self, timeout: int | None) -> int:
        """
        Validate and normalize a timeout value.

        Args:
            timeout: Optional timeout value in seconds

        Returns:
            Validated timeout in seconds (clamped to MIN/MAX_TIMEOUT_SECONDS)

        Raises:
            InvalidInputError: If timeout is invalid
        """
        if timeout is None:
            return self.DEFAULT_TIMEOUT_SECONDS

        if not isinstance(timeout, int):
            raise InvalidInputError(
                f"Timeout must be an integer, got {type(timeout).__name__}"
            )

        if timeout < self.MIN_TIMEOUT_SECONDS:
            raise InvalidInputError(
                f"Timeout must be at least {self.MIN_TIMEOUT_SECONDS} seconds"
            )

        if timeout > self.MAX_TIMEOUT_SECONDS:
            raise InvalidInputError(
                f"Timeout cannot exceed {self.MAX_TIMEOUT_SECONDS} seconds"
            )

        return timeout

    def _orchestrator_for_call(
        self, arguments: dict, **overrides: Any
    ) -> StatelessOrchestrator:
        """
        Build a StatelessOrchestrator using the per-call workspace if provided,
        otherwise falling back to the server's pre-loaded workspace.
        """
        from devin_orchestrator.stateless_orchestrator import StatelessOrchestrator

        workspace = arguments.get("workspace") or self.workspace
        return StatelessOrchestrator(
            workspace=workspace,
            demo_mode=overrides.get("demo_mode", False),
            timeout=overrides.get("timeout"),
            gate_mode=overrides.get("gate_mode"),
        )

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
        """
        List all available skills with their metadata.

        Args:
            _arguments: Tool arguments (unused)

        Returns:
            List containing JSON-formatted skill definitions
        """
        skills_dir = self.config.skills_dir
        skills = []
        if skills_dir.exists():
            for entry in sorted(skills_dir.iterdir()):
                yaml_file = entry / f"{entry.name}.yaml"
                if entry.is_dir() and yaml_file.exists():
                    try:
                        data = (
                            yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                        )
                    except yaml.YAMLError as e:
                        # Skip malformed skill YAML files so a single corrupt
                        # file does not crash the listing operation.
                        logger.warning(
                            "Skipping malformed skill YAML %s: %s",
                            yaml_file,
                            e,
                        )
                        continue
                    skills.append(
                        {
                            "name": entry.name,
                            "description": data.get("description", ""),
                            "iron_law": data.get("iron_law", ""),
                        }
                    )
        return [self._text_content(json.dumps(skills, indent=2))]

    def _tool_get_skill(self, arguments: dict) -> list[dict]:
        """
        Get the YAML definition and markdown narrative for a skill.

        Args:
            arguments: Tool arguments containing skill name

        Returns:
            List containing skill definition and narrative

        Raises:
            FileNotFoundError: If skill is not found
        """
        try:
            name = arguments["name"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid name parameter: {e}")]

        # Validate skill name to prevent path traversal
        try:
            skill_name = validate_skill_name(name)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid skill name: {e}")]

        # Resolve the skill directory against skills_dir before validation so
        # relative names are contained correctly (validate_path_safe resolves
        # bare relative paths against CWD, which would escape the base
        # directory). Mirrors the _tool_get_workflow pattern.
        try:
            skill_dir = validate_path_safe(
                self.config.skills_dir,
                self.config.skills_dir / skill_name,
                allow_absolute=True,
            )
        except (InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Path validation failed: {e}")]

        yaml_file = skill_dir / f"{skill_name}.yaml"
        md_file = skill_dir / f"{skill_name}.md"
        if not yaml_file.exists():
            raise FileNotFoundError(f"Skill not found: {skill_name}")
        parts = ["# YAML\n", yaml_file.read_text(encoding="utf-8")]
        if md_file.exists():
            parts.extend(["\n# Markdown\n", md_file.read_text(encoding="utf-8")])
        return [self._text_content("".join(parts))]

    def _tool_list_workflows(self, _arguments: dict) -> list[dict]:
        """
        List all available workflow manifests with their metadata.

        Args:
            _arguments: Tool arguments (unused)

        Returns:
            List containing JSON-formatted workflow definitions
        """
        workflows_dir = self.config.workflows_dir
        workflows = []
        use_case_map: dict[str, list[dict]] = {}
        use_cases_file = workflows_dir / "use-cases.yaml"
        if use_cases_file.exists():
            try:
                use_cases_data = (
                    yaml.safe_load(use_cases_file.read_text(encoding="utf-8")) or {}
                )
                for uc in use_cases_data.get("use_cases", []):
                    wf_name = uc.get("workflow")
                    if not wf_name:
                        continue
                    use_case_map.setdefault(wf_name, []).append(
                        {
                            "id": uc.get("id"),
                            "name": uc.get("name"),
                            "type": uc.get("type"),
                            "description": uc.get("description"),
                            "slash_command": uc.get("slash_command"),
                            "git_operations": uc.get("git_operations"),
                            "session_id_format": uc.get("session_id_format"),
                        }
                    )
            except (FileNotFoundError, yaml.YAMLError, ValueError, KeyError):
                # Silently handle errors in use-cases file to avoid breaking workflow listing
                pass
        if workflows_dir.exists():
            for manifest in sorted(workflows_dir.glob("*.manifest.yaml")):
                try:
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as e:
                    # Skip malformed workflow manifests so a single corrupt
                    # file does not crash the listing operation.
                    logger.warning(
                        "Skipping malformed workflow manifest %s: %s",
                        manifest,
                        e,
                    )
                    continue
                wf_name = manifest.stem.replace(".manifest", "")
                workflows.append(
                    {
                        "name": wf_name,
                        "description": data.get("description", ""),
                        "schema_version": data.get("schema_version", ""),
                        "use_cases": use_case_map.get(wf_name, []),
                    }
                )
        return [self._text_content(json.dumps(workflows, indent=2))]

    def _tool_get_workflow(self, arguments: dict) -> list[dict]:
        """
        Get a workflow manifest and its runbook.

        Args:
            arguments: Tool arguments containing workflow name

        Returns:
            List containing workflow manifest and runbook

        Raises:
            FileNotFoundError: If workflow is not found
        """
        try:
            name = arguments["name"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid name parameter: {e}")]

        # Validate workflow name to prevent path traversal. Workflow names allow
        # underscores (e.g. code_review) unlike skill names which are hyphen-only.
        try:
            workflow_name = validate_workflow_name(name)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid workflow name: {e}")]

        # Workflow files are directly in workflows_dir. Resolve the manifest
        # path against workflows_dir before validation so relative names are
        # contained correctly (validate_path_safe resolves bare relative paths
        # against CWD, which would escape the base directory).
        try:
            manifest = validate_path_safe(
                self.config.workflows_dir,
                self.config.workflows_dir / f"{workflow_name}.manifest.yaml",
                allow_absolute=True,
            )
        except (InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Path validation failed: {e}")]

        runbook = manifest.parent / f"{workflow_name}.runbook.md"
        if not manifest.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_name}")
        parts = ["# Manifest\n", manifest.read_text(encoding="utf-8")]
        if runbook.exists():
            parts.extend(["\n# Runbook\n", runbook.read_text(encoding="utf-8")])
        return [self._text_content("".join(parts))]

    @staticmethod
    def _truncate_output(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
        """Truncate ``text`` to ``max_bytes`` UTF-8 bytes and append a marker."""
        if not text:
            return text
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        marker = "\n... [output truncated]\n"
        keep = max(0, max_bytes - len(marker.encode("utf-8")))
        truncated = encoded[:keep].decode("utf-8", errors="ignore")
        return truncated + marker

    def _tool_dispatch_devin(self, arguments: dict) -> list[dict]:
        """
        Dispatch a generic Devin run with a role and prompt file.

        Args:
            arguments: Tool arguments containing role, prompt_file, work_dir, etc.

        Returns:
            List containing dispatch result with exit code and output
        """
        # Validate work_dir is under global_root
        try:
            work_dir = validate_workspace_path(
                arguments["work_dir"], base_allowed_dir=self.config.global_root
            )
        except InvalidInputError as e:
            return [self._text_content(f"Invalid work_dir: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid work_dir parameter: {e}")]

        # Validate prompt_file is under work_dir. Relative paths resolve
        # against work_dir (not CWD) by joining first, mirroring the
        # _tool_read_artifact pattern.
        try:
            prompt_input = Path(arguments["prompt_file"])
            if prompt_input.is_absolute():
                prompt_file = validate_path_safe(
                    work_dir, prompt_input, allow_absolute=True
                )
            else:
                prompt_file = validate_path_safe(
                    work_dir, work_dir / prompt_input, allow_absolute=True
                )
        except InvalidInputError as e:
            return [self._text_content(f"Invalid prompt_file: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid prompt_file parameter: {e}")]

        # Validate output_file if provided is under work_dir, with the same
        # relative-path handling as prompt_file. Keep the validated path so we
        # read the output from work_dir rather than CWD (M-1).
        validated_output_file: Path | None = None
        if arguments.get("output_file"):
            try:
                output_input = Path(arguments["output_file"])
                if output_input.is_absolute():
                    validated_output_file = validate_path_safe(
                        work_dir, output_input, allow_absolute=True
                    )
                else:
                    validated_output_file = validate_path_safe(
                        work_dir, work_dir / output_input, allow_absolute=True
                    )
            except InvalidInputError as e:
                return [self._text_content(f"Invalid output_file: {e}")]

        # Validate role is either a short name or a path under global_root/roles.
        # Short names are restricted to safe characters (no path separators or
        # traversal) and resolved to global_root/roles/<role>.md before being
        # passed to the subprocess, so dispatch_devin.py never receives a raw
        # relative name that could resolve against CWD or escape roles/.
        role = arguments["role"]
        roles_dir = self.config.global_root / "roles"
        role_path = Path(role)
        if role_path.is_absolute():
            # If absolute, must be under global_root/roles
            try:
                resolved_role = validate_path_safe(
                    roles_dir, role_path, allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                return [self._text_content(f"Invalid role path: {e}")]
        else:
            # Short name - validate it contains only safe characters (no path
            # separators, dots, or traversal segments).
            if not re.match(r"^[a-zA-Z0-9_-]+$", role):
                return [self._text_content(f"Invalid role name: {role}")]
            try:
                resolved_role = validate_path_safe(
                    roles_dir, roles_dir / f"{role}.md", allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                return [self._text_content(f"Invalid role name: {e}")]
        if not resolved_role.is_file():
            return [self._text_content(f"Role file not found: {resolved_role}")]

        script = Path(__file__).parent / "dispatch_devin.py"
        cmd = [sys.executable, str(script)]
        if arguments.get("model"):
            cmd.extend(["--model", str(arguments["model"])])
        if arguments.get("agent"):
            cmd.extend(["--agent", str(arguments["agent"])])
        if arguments.get("phase"):
            cmd.extend(["--phase", str(arguments["phase"])])
        cmd.extend(["--role", str(resolved_role)])
        cmd.extend(["--prompt-file", str(prompt_file)])
        cmd.extend(["--work-dir", str(work_dir)])
        if validated_output_file is not None:
            cmd.extend(["--output-file", str(validated_output_file)])
        for ctx in arguments.get("focused_context", []):
            try:
                validated_ctx = validate_path_safe(
                    work_dir, Path(ctx), allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                return [self._text_content(f"Invalid focused_context path: {e}")]
            cmd.extend(["--focused-context", str(validated_ctx)])

        if arguments.get("permission_mode"):
            cmd.extend(["--permission-mode", str(arguments["permission_mode"])])

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        cmd.extend(["--timeout", str(timeout)])

        # Create a dispatch session so the call is non-blocking and leaves
        # replayable artifacts (cmd.json, stdout.txt, stderr.txt, result.json).
        try:
            dispatch_id, dispatch_dir = create_session(
                self.config.session_work_dir, "DISPATCH-NNN"
            )
        except (InvalidInputError, OSError) as e:
            return [self._text_content(f"Failed to create dispatch session: {e}")]

        request_content = f"role={role}\nprompt={prompt_file}\nwork_dir={work_dir}"
        session_init(dispatch_id, self.config.session_work_dir, request_content)

        thread = threading.Thread(
            target=SubprocessArtifactRunner.run,
            args=(dispatch_dir, cmd, work_dir, timeout),
            daemon=True,
        )
        thread.start()

        result = {
            "session_id": dispatch_id,
            "workspace": str(dispatch_dir),
            "status": "started",
        }
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_dispatch_skill(self, arguments: dict) -> list[dict]:
        """
        Invoke a named skill in a target workspace.

        Args:
            arguments: Tool arguments containing skill_name, session_id, workspace, etc.

        Returns:
            List containing dispatch result with exit code and output
        """
        # Validate workspace is under global_root
        try:
            workspace = validate_workspace_path(
                arguments["workspace"], base_allowed_dir=self.config.global_root
            )
        except InvalidInputError as e:
            return [self._text_content(f"Invalid workspace: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid workspace parameter: {e}")]

        # Validate skill_name
        try:
            skill_name = validate_skill_name(arguments["skill_name"])
        except InvalidInputError as e:
            return [self._text_content(f"Invalid skill_name: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid skill_name parameter: {e}")]

        # Validate session_id
        try:
            session_id = validate_session_id(arguments["session_id"])
        except InvalidInputError as e:
            return [self._text_content(f"Invalid session_id: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid session_id parameter: {e}")]

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        # Validate and parse config_overrides
        try:
            overrides = parse_config_overrides(arguments.get("config_overrides"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid config_overrides: {e}")]

        script = Path(__file__).parent / "dispatch_skill.py"
        cmd = [
            sys.executable,
            str(script),
            str(skill_name),
            str(session_id),
            str(workspace),
            str(arguments.get("is_reviewer", False)).lower(),
            str(arguments.get("demo_mode", False)).lower(),
        ]
        if overrides:
            cmd.append(json.dumps(overrides))

        # Create a dispatch session so the call is non-blocking and leaves
        # replayable artifacts (cmd.json, stdout.txt, stderr.txt, result.json).
        try:
            dispatch_id, dispatch_dir = create_session(
                self.config.session_work_dir, "DISPATCH-NNN"
            )
        except (InvalidInputError, OSError) as e:
            return [self._text_content(f"Failed to create dispatch session: {e}")]

        request_content = f"skill={skill_name}\nsession_id={session_id}\nworkspace={workspace}"
        session_init(dispatch_id, self.config.session_work_dir, request_content)

        thread = threading.Thread(
            target=SubprocessArtifactRunner.run,
            args=(dispatch_dir, cmd, None, timeout),
            daemon=True,
        )
        thread.start()

        result = {
            "session_id": dispatch_id,
            "workspace": str(dispatch_dir),
            "status": "started",
        }
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_read_artifact(self, arguments: dict) -> list[dict]:
        """
        Read a file from a workspace or session directory.

        Text files support optional 1-based line offset/limit and are
        truncated to MAX_OUTPUT_BYTES. Binary files are returned as base64,
        with image types exposed as MCP image content.

        Args:
            arguments: Tool arguments containing path, optional session_id,
                workspace, offset, and limit.

        Returns:
            List containing file contents

        Raises:
            FileNotFoundError: If file is not found
        """
        try:
            path = Path(arguments["path"])
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid path parameter: {e}")]

        try:
            base = self._resolve_artifact_base(arguments)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base: {e}")]

        try:
            if path.is_absolute():
                target = validate_path_safe(base, path, allow_absolute=True)
            else:
                target = validate_path_safe(base, base / path, allow_absolute=True)
        except (InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid path: {e}")]

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")

        try:
            offset = int(arguments.get("offset", 1))
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid offset: {e}")]

        limit = arguments.get("limit")
        try:
            if limit is not None:
                limit = int(limit)
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid limit: {e}")]

        if offset < 1:
            return [self._text_content("offset must be >= 1")]
        if limit is not None and limit < 0:
            return [self._text_content("limit must be >= 0")]

        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self._read_binary_artifact(target)

        lines = text.splitlines()
        start = offset - 1
        end = None if limit is None else start + limit
        selected = lines[start:end]
        content = "\n".join(selected)

        raw = content.encode("utf-8")
        if len(raw) > self.MAX_OUTPUT_BYTES:
            truncated = raw[: self.MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            total = len(text.encode("utf-8"))
            content = (
                truncated
                + f"\n\n[... output truncated at {self.MAX_OUTPUT_BYTES} bytes; "
                f"total {total} bytes ...]"
            )

        return [self._text_content(content)]

    def _tool_execute(self, arguments: dict) -> list[dict]:
        """
        Execute a request with automatic or explicit intent routing.

        Starts the matched workflow/skill in a background thread and returns
        the session_id immediately. Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, intent, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        intent = arguments.get("intent", "auto")
        result = orchestrator.execute_async(request, intent)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_implement(self, arguments: dict) -> list[dict]:
        """
        Execute an implementation request using the superpower workflow.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.implement_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_review(self, arguments: dict) -> list[dict]:
        """
        Execute a review request using the code_review workflow.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.review_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_investigate(self, arguments: dict) -> list[dict]:
        """
        Execute an investigation request using the rca workflow.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.investigate_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_plan(self, arguments: dict) -> list[dict]:
        """
        Execute a planning request using the writing-plans skill.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
        )
        request = arguments["request"]
        result = orchestrator.plan_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_run_workflow(self, arguments: dict) -> list[dict]:
        """
        Run a specific workflow with a request.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing workflow, request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )

        # Validate workflow name to prevent path traversal / manifest injection.
        # Mirrors the pattern used in _tool_get_workflow. Workflow names allow
        # underscores (e.g. code_review) unlike skill names which are hyphen-only.
        try:
            workflow = arguments["workflow"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid workflow parameter: {e}")]
        try:
            workflow_name = validate_workflow_name(workflow)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid workflow name: {e}")]

        request = arguments["request"]
        result = orchestrator.run_workflow_async(workflow_name, request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_gate_decision(self, arguments: dict) -> list[dict]:
        """
        Write a gate decision to the session's gate decision file.

        Args:
            arguments: Tool arguments containing session_id, gate_id, verdict, notes,
                and optional workspace

        Returns:
            List containing success message
        """
        from devin_orchestrator.session_manager import resolve_session

        session_id = arguments.get("session_id")
        gate_id = arguments.get("gate_id")
        verdict = arguments.get("verdict")
        notes = arguments.get("notes", "")

        if not all([session_id, gate_id, verdict]):
            return [self._text_content("session_id, gate_id, and verdict are required")]

        assert isinstance(session_id, str)

        workspace = arguments.get("workspace") or self.workspace
        session_work_dir = (
            ConfigLoader.load(workspace=workspace).session_work_dir
            if workspace
            else self.config.session_work_dir
        )

        try:
            session_dir = resolve_session(session_work_dir, session_id)
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            return [self._text_content(f"Failed to resolve session: {e}")]

        decision_file = session_dir / f"gate-{gate_id}-decision.md"
        try:
            decision_file.write_text(
                f"verdict: {verdict}\nnotes: {notes}\n", encoding="utf-8"
            )
        except (OSError, PermissionError) as e:
            return [self._text_content(f"Failed to write gate decision: {e}")]

        return [
            self._text_content(
                f"Gate decision written for {gate_id}. "
                f"Call continue_workflow with session_id {session_id} to resume."
            )
        ]

    def _tool_continue_workflow(self, arguments: dict) -> list[dict]:
        """
        Resume a workflow that is paused at a gate.

        Starts the continuation in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing session_id, optional workspace,
                demo_mode, timeout, gate_mode, and optional gate verdict

        Returns:
            List containing session info with session_id and status
        """
        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        result = orchestrator.continue_workflow_async(
            session_id=session_id,
            gate_verdict=arguments.get("gate_verdict"),
            gate_notes=arguments.get("gate_notes"),
            gate_id=arguments.get("gate_id"),
        )
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_run_skill(self, arguments: dict) -> list[dict]:
        """
        Run a specific skill with a request.

        Starts the skill in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing skill, request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        # Validate skill name to prevent path traversal. This is the single
        # validation point at the MCP tool entry for the run_skill chain.
        try:
            skill = arguments["skill"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid skill parameter: {e}")]
        try:
            skill_name = validate_skill_name(skill)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid skill name: {e}")]

        # run_skill is a low-level tool intended for process skills that do not
        # require project context or focused artifacts. Implementation, review,
        # and investigation skills should use the dedicated high-level tools or
        # focused dispatch_devin so the worker gets the right files and criteria.
        process_skills = {
            "brainstorming",
            "writing-plans",
            "systematic-debugging",
        }
        if skill_name not in process_skills:
            return [
                self._text_content(
                    json.dumps(
                        {
                            "success": False,
                            "error": (
                                f"run_skill is not the right tool for '{skill_name}'. "
                                "It is intended for process skills only. "
                                "For implementation use `implement`, `run_workflow`, or "
                                "`dispatch_devin`. For review use `review` or "
                                "`dispatch_devin` with a reviewer role. For investigation "
                                "use `investigate` or `dispatch_devin` with a reviewer role."
                            ),
                            "skill": skill_name,
                            "suggested_tools": [
                                "implement",
                                "run_workflow",
                                "dispatch_devin",
                                "review",
                                "investigate",
                            ],
                        },
                        indent=2,
                    )
                )
            ]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
        )
        request = arguments["request"]
        result = orchestrator.run_skill_async(skill_name, request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_query_workflow_status(self, arguments: dict) -> list[dict]:
        """
        Poll the status of a started or continued workflow/skill.

        Args:
            arguments: Tool arguments containing session_id and optional workspace

        Returns:
            List containing status, stages, and result
        """
        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        orchestrator = self._orchestrator_for_call(arguments)
        result = orchestrator.get_workflow_status(session_id)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_list_sessions(self, arguments: dict) -> list[dict]:
        """
        List sessions in the configured session work directory.

        Args:
            arguments: Tool arguments containing optional session_type and limit

        Returns:
            List of session records
        """
        try:
            orchestrator = self._orchestrator_for_call(arguments)
            base = orchestrator.config.session_work_dir
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            return [self._text_content(f"Invalid workspace: {e}")]

        if not base.is_dir():
            return [self._text_content(f"Session directory not found: {base}")]

        session_type = arguments.get("session_type", "all")
        if session_type not in ("all", "workflow", "dispatch", "skill"):
            return [self._text_content("session_type must be all, workflow, dispatch, or skill")]

        try:
            limit = int(arguments.get("limit", 0))
        except (TypeError, ValueError):
            return [self._text_content("Invalid limit")]

        session_re = re.compile(r"^[A-Za-z0-9_-]+-\d+$")
        entries: list[dict[str, Any]] = []
        for entry in sorted(
            base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if not entry.is_dir() or not session_re.match(entry.name):
                continue
            entry_type = "workflow"
            if entry.name.startswith("DISPATCH-"):
                entry_type = "dispatch"
            elif entry.name.startswith("SKILL-"):
                entry_type = "skill"
            if session_type != "all" and entry_type != session_type:
                continue

            session_file = entry / "session.json"
            result_file = entry / "result.json"
            status = "unknown"
            last_update = entry.stat().st_mtime
            if session_file.exists():
                try:
                    data = json.loads(session_file.read_text(encoding="utf-8"))
                    status = data.get("status", status)
                    last_update = max(last_update, session_file.stat().st_mtime)
                except (OSError, json.JSONDecodeError):
                    pass
            if result_file.exists():
                last_update = max(last_update, result_file.stat().st_mtime)

            entries.append(
                {
                    "session_id": entry.name,
                    "type": entry_type,
                    "status": status,
                    "last_update": datetime.fromtimestamp(
                        last_update, tz=timezone.utc
                    ).isoformat(),
                    "workspace": str(entry),
                }
            )

        if limit > 0:
            entries = entries[:limit]

        return [self._text_content(json.dumps(entries, indent=2, default=str))]

    def _tool_cancel_session(self, arguments: dict) -> list[dict]:
        """
        Request cancellation of a session.

        Args:
            arguments: Tool arguments containing session_id and optional workspace

        Returns:
            JSON with session_id and status
        """
        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        try:
            orchestrator = self._orchestrator_for_call(arguments)
            result = orchestrator.cancel_session(str(session_id))
            return [self._text_content(json.dumps(result, indent=2))]
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            return [self._text_content(f"Failed to cancel session: {e}")]

    # --------------------------------------------------------------------- #
    # stdio transport
    # --------------------------------------------------------------------- #
    def _read_message(self) -> dict | None:
        # Auto-detect framing: NDJSON (one JSON object per line, MCP 2025-11-25)
        # or LSP-style Content-Length headers (older MCP / TypeScript SDK).
        while True:
            # Bound the line read so a missing newline cannot cause unbounded
            # memory consumption on the stdio transport. readline(n) returns at
            # most n bytes; if the line is longer than the limit it will be
            # returned without a trailing newline.
            line = self.stdin.readline(self.MAX_MESSAGE_SIZE + 1)
            if not line:
                return None
            if len(line) > self.MAX_MESSAGE_SIZE and b"\n" not in line:
                logger.error(
                    "NDJSON line exceeds maximum message size %d",
                    self.MAX_MESSAGE_SIZE,
                )
                return self._error(
                    {"id": None},
                    -32700,
                    f"Message size exceeds maximum {self.MAX_MESSAGE_SIZE}",
                )
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.lower().startswith(b"content-length:"):
                return self._read_content_length_message(stripped)
            self._framing = self._framing or "ndjson"
            self._log_message("in", stripped)
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as e:
                # Return parse error for malformed JSON
                return self._error({"id": None}, -32700, f"JSON parse error: {e}")

    def _read_content_length_message(self, first_line: bytes) -> dict | None:
        headers: dict[str, str] = {}
        # first_line already stripped, e.g. b"Content-Length: 123"
        if b":" in first_line:
            key, value = first_line.split(b":", 1)
            headers[key.strip().lower().decode()] = value.strip().decode()
        while True:
            header_line = self.stdin.readline()
            if not header_line:
                return None
            if header_line in (b"\r\n", b"\n"):
                break
            h = header_line.strip()
            if b":" in h:
                k, v = h.split(b":", 1)
                headers[k.strip().lower().decode()] = v.strip().decode()

        # Validate and parse Content-Length
        content_length_str = headers.get("content-length", "0")
        try:
            length = int(content_length_str)
        except ValueError:
            # Invalid Content-Length header - return parse error
            return self._error({"id": None}, -32700, "Invalid Content-Length header")

        if length <= 0:
            return self._error({"id": None}, -32700, "Content-Length must be positive")

        if length > self.MAX_MESSAGE_SIZE:
            return self._error(
                {"id": None},
                -32700,
                f"Message size {length} exceeds maximum {self.MAX_MESSAGE_SIZE}",
            )

        body = self._read_exactly(length)
        self._framing = self._framing or "content-length"
        self._log_message("in", body)
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            return self._error({"id": None}, -32700, f"JSON parse error: {e}")

    def _read_exactly(self, n: int) -> bytes:
        chunks: list[bytes] = []
        remaining = n
        while remaining > 0:
            chunk = self.stdin.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _write_message(self, message: dict) -> None:
        self._log_message("out", message)
        body = json.dumps(message).encode()
        if self._framing == "ndjson":
            self.stdout.write(body + b"\n")
        else:
            header = f"Content-Length: {len(body)}\r\n\r\n".encode()
            self.stdout.write(header + body)
        self.stdout.flush()

    def run(self) -> None:
        try:
            while True:
                request = self._read_message()
                if request is None:
                    break
                # If _read_message returned an error response, write it directly
                if "error" in request:
                    self._write_message(request)
                    continue
                response = self.handle(request)
                if response is not None:
                    self._write_message(response)
        except KeyboardInterrupt:
            logger.info("MCP server received KeyboardInterrupt, shutting down.")
        finally:
            self.close()

    # --------------------------------------------------------------------- #
    # MCP resources support
    # --------------------------------------------------------------------- #
    def _is_session_dir_name(self, name: str) -> bool:
        return bool(re.match(r"^[A-Za-z0-9_-]+-\d+$", name))

    def _collect_resources(self, base: Path, uri_prefix: str) -> list[dict]:
        """Walk a directory and return file records as MCP resources."""
        resources: list[dict] = []
        for p in sorted(base.rglob("*"), key=lambda x: str(x)):
            if not p.is_file():
                continue
            rel = p.relative_to(base).as_posix()
            mime, _ = mimetypes.guess_type(str(p))
            try:
                size = p.stat().st_size
            except OSError:
                size = -1
            resources.append(
                {
                    "uri": f"{uri_prefix}{rel}",
                    "name": p.name,
                    "mimeType": mime or "application/octet-stream",
                    "size": size,
                }
            )
        return resources

    def _read_resource_contents(self, uri: str, target: Path) -> dict:
        """Return an MCP ResourceContents dict for a file."""
        try:
            text = target.read_text(encoding="utf-8")
            raw = text.encode("utf-8")
            if len(raw) > self.MAX_OUTPUT_BYTES:
                truncated = raw[: self.MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
                text = truncated + "\n\n[... resource truncated ...]"
            mime = mimetypes.guess_type(str(target))[0] or "text/plain"
            return {"uri": uri, "mimeType": mime, "text": text}
        except UnicodeDecodeError:
            data = target.read_bytes()
            if len(data) > self.MAX_OUTPUT_BYTES:
                data = data[: self.MAX_OUTPUT_BYTES]
            b64 = base64.b64encode(data).decode("ascii")
            mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            return {"uri": uri, "mimeType": mime, "blob": b64}

    def _resources_list(self, request: dict) -> dict:
        """List workspace and session artifacts as MCP resources with pagination."""
        params = request.get("params", {})
        try:
            cursor = int(params.get("cursor", "0") or "0")
        except (TypeError, ValueError):
            return self._error(request, -32602, "Invalid cursor")
        page_size = 100

        resources: list[dict] = []
        if self.workspace:
            workspace_path = Path(self.workspace).expanduser()
            if workspace_path.is_dir():
                resources.extend(
                    self._collect_resources(workspace_path, "workspace://")
                )
        session_dir = self.config.session_work_dir
        if session_dir.is_dir():
            for entry in sorted(
                session_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
            ):
                if not entry.is_dir() or not self._is_session_dir_name(entry.name):
                    continue
                resources.extend(
                    self._collect_resources(entry, f"session://{entry.name}/")
                )

        total = len(resources)
        page = resources[cursor : cursor + page_size]
        result: dict[str, Any] = {"resources": page}
        if cursor + page_size < total:
            result["nextCursor"] = str(cursor + page_size)
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result,
        }

    def _resources_read(self, request: dict) -> dict:
        """Read a resource URI and return its contents."""
        params = request.get("params", {})
        uri = params.get("uri")
        if not uri or "://" not in uri:
            return self._error(request, -32602, "Missing or invalid uri")

        scheme, _, rest = uri.partition("://")
        if scheme == "workspace":
            if not self.workspace:
                return self._error(request, -32602, "Workspace not configured")
            base = Path(self.workspace).expanduser()
            if not base.is_dir():
                return self._error(request, -32602, "Workspace not found")
            try:
                target = validate_path_safe(base, base / rest, allow_absolute=False)
            except (InvalidInputError, PathTraversalError) as e:
                return self._error(request, -32602, f"Invalid workspace resource: {e}")
        elif scheme == "session":
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return self._error(request, -32602, "Invalid session resource uri")
            session_id, path = parts
            from devin_orchestrator.session_manager import resolve_session
            try:
                base = resolve_session(self.config.session_work_dir, session_id)
            except (FileNotFoundError, ValueError, InvalidInputError, PathTraversalError) as e:
                return self._error(request, -32602, f"Invalid session: {e}")
            try:
                target = validate_path_safe(base, base / path, allow_absolute=False)
            except (InvalidInputError, PathTraversalError) as e:
                return self._error(request, -32602, f"Invalid session resource: {e}")
        else:
            return self._error(request, -32602, f"Unsupported resource scheme: {scheme}")

        if not target.is_file():
            return self._error(request, -32602, f"Resource not found: {uri}")

        contents = self._read_resource_contents(uri, target)
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"contents": [contents]},
        }

    def _resources_templates_list(self, request: dict) -> dict:
        """Return available resource URI templates."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "resourceTemplates": [
                    {
                        "uriTemplate": "workspace://{path}",
                        "name": "Workspace file",
                    },
                    {
                        "uriTemplate": "session://{session_id}/{path}",
                        "name": "Session artifact",
                    },
                ]
            },
        }

    def _resources_subscribe(self, request: dict) -> dict:
        """Subscribe to resource changes (no-op; dynamic updates not supported)."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {},
        }

    def _resources_unsubscribe(self, request: dict) -> dict:
        """Unsubscribe from resource changes (no-op)."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {},
        }

    def _resolve_artifact_base(self, arguments: dict) -> Path:
        """Resolve the base directory for artifact operations."""
        from devin_orchestrator.session_manager import resolve_session

        session_id = arguments.get("session_id")
        if session_id:
            try:
                return resolve_session(self.config.session_work_dir, str(session_id))
            except (FileNotFoundError, ValueError, InvalidInputError, PathTraversalError) as e:
                raise FileNotFoundError(f"Failed to resolve session {session_id}: {e}") from e

        provided_workspace = arguments.get("workspace") or self.workspace
        if provided_workspace:
            try:
                return validate_workspace_path(
                    str(provided_workspace), base_allowed_dir=self.config.global_root
                )
            except (InvalidInputError, PathTraversalError) as e:
                raise InvalidInputError(f"Invalid workspace: {e}") from e

        return self.config.session_work_dir

    def _resolve_artifact_target(self, arguments: dict, base: Path) -> Path:
        """Resolve and validate a path relative to an artifact base directory."""
        try:
            path = Path(arguments["path"])
        except (KeyError, TypeError) as e:
            raise InvalidInputError(f"Invalid path parameter: {e}") from e

        try:
            if path.is_absolute():
                return validate_path_safe(base, path, allow_absolute=True)
            return validate_path_safe(base, base / path, allow_absolute=True)
        except (InvalidInputError, PathTraversalError) as e:
            raise InvalidInputError(f"Invalid path: {e}") from e

    def _read_binary_artifact(self, target: Path) -> list[dict]:
        """Return a binary artifact as base64 text, or as an image blob."""
        data = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        mime = mime or "application/octet-stream"
        if len(data) > self.MAX_OUTPUT_BYTES:
            data = data[: self.MAX_OUTPUT_BYTES]
        b64 = base64.b64encode(data).decode("ascii")
        if mime.startswith("image/"):
            return [{"type": "image", "mimeType": mime, "data": b64}]
        payload = json.dumps({"encoding": "base64", "mime": mime, "data": b64})
        return [self._text_content(payload)]

    def _walk_directory(
        self, target: Path, recursive: bool, max_depth: int, files_only: bool
    ) -> list[dict]:
        """Walk a directory and return a list of sanitized entry records."""
        entries: list[dict] = []

        if not recursive:
            for entry in sorted(target.iterdir()):
                etype = "directory" if entry.is_dir() else "file"
                if files_only and etype == "directory":
                    continue
                rel = str(entry.relative_to(target))
                size = 0
                try:
                    if etype == "file" and entry.is_file():
                        size = entry.stat().st_size
                except OSError:
                    size = -1
                entries.append({"name": entry.name, "type": etype, "size": size, "path": rel})
            return entries

        for root, dirs, files in os.walk(target):
            rel_root = Path(os.path.relpath(root, target))
            depth = 0 if rel_root == Path(".") else len(rel_root.parts)
            if depth > max_depth:
                continue
            if depth == max_depth:
                dirs[:] = []

            if not files_only:
                for d in sorted(dirs):
                    full = Path(root) / d
                    entries.append(
                        {
                            "name": d,
                            "type": "directory",
                            "size": 0,
                            "path": str(rel_root / d),
                        }
                    )
            for f in sorted(files):
                full = Path(root) / f
                size = 0
                try:
                    if full.is_file():
                        size = full.stat().st_size
                except OSError:
                    size = -1
                entries.append(
                    {
                        "name": f,
                        "type": "file",
                        "size": size,
                        "path": str(rel_root / f),
                    }
                )
        return entries

    def _tool_list_directory(self, arguments: dict) -> list[dict]:
        """List files and directories under a validated workspace or session path."""
        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")

        try:
            recursive = bool(arguments.get("recursive", False))
            max_depth = int(arguments.get("max_depth", 3 if recursive else 1))
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid list options: {e}")]

        if max_depth < 0:
            return [self._text_content("max_depth must be >= 0")]

        entries = self._walk_directory(target, recursive, max_depth, files_only=False)
        return [self._text_content(json.dumps(entries, indent=2, default=str))]

    def _tool_list_artifacts(self, arguments: dict) -> list[dict]:
        """List files recursively in a session directory or workspace."""
        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")

        try:
            recursive = bool(arguments.get("recursive", True))
            max_depth = int(arguments.get("max_depth", 10))
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid list options: {e}")]

        if max_depth < 0:
            return [self._text_content("max_depth must be >= 0")]

        entries = self._walk_directory(target, recursive, max_depth, files_only=True)
        return [self._text_content(json.dumps(entries, indent=2, default=str))]

    def _tool_write_artifact(self, arguments: dict) -> list[dict]:
        """Write or overwrite a text or base64 file under a validated path."""
        try:
            content = arguments["content"]
            encoding = arguments.get("encoding", "utf-8")
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid arguments: {e}")]

        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if target.is_dir():
            return [self._text_content("Cannot write to a directory path")]

        if encoding not in ("utf-8", "base64"):
            return [self._text_content("encoding must be 'utf-8' or 'base64'")]

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if encoding == "base64":
                raw = base64.b64decode(content)
                target.write_bytes(raw)
            else:
                target.write_text(content, encoding="utf-8")
        except (OSError, binascii.Error, ValueError) as e:
            return [self._text_content(f"Failed to write {target}: {e}")]

        return [self._text_content(f"Wrote {target}")]

    def _tool_apply_patch(self, arguments: dict) -> list[dict]:
        """Apply a unified diff patch to a file under a validated path."""
        try:
            patch = arguments["patch"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid arguments: {e}")]

        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")

        try:
            self._apply_unified_diff(target, patch)
        except (InvalidInputError, OSError) as e:
            return [self._text_content(f"Failed to apply patch: {e}")]

        return [self._text_content(f"Patched {target}")]

    def _apply_unified_diff(self, file_path: Path, diff: str) -> None:
        """Apply a unified diff to a text file in-place."""
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        lines = file_path.read_text(encoding="utf-8").splitlines()
        diff_lines = diff.splitlines()
        hunks: list[tuple[int, list[str]]] = []

        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("@@"):
                m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if not m:
                    raise InvalidInputError(f"Invalid hunk header: {line}")
                old_start = int(m.group(1))
                i += 1
                hunk: list[str] = []
                while (
                    i < len(diff_lines)
                    and not diff_lines[i].startswith("@@")
                    and not diff_lines[i].startswith("---")
                    and not diff_lines[i].startswith("+++")
                ):
                    hunk.append(diff_lines[i])
                    i += 1
                hunks.append((old_start, hunk))
            else:
                i += 1

        offset = 0
        for old_start, hunk in hunks:
            pos = old_start - 1 + offset
            if pos < 0 or pos > len(lines):
                raise InvalidInputError(f"Hunk starting at line {old_start} is out of range")
            old_idx = pos
            new_lines: list[str] = []
            for dl in hunk:
                if not dl:
                    continue
                if dl.startswith("\\"):
                    continue
                if dl.startswith(" "):
                    if old_idx >= len(lines) or lines[old_idx] != dl[1:]:
                        raise InvalidInputError(f"Context mismatch at line {old_idx + 1}")
                    new_lines.append(dl[1:])
                    old_idx += 1
                elif dl.startswith("-"):
                    if old_idx >= len(lines) or lines[old_idx] != dl[1:]:
                        raise InvalidInputError(f"Remove mismatch at line {old_idx + 1}")
                    old_idx += 1
                elif dl.startswith("+"):
                    new_lines.append(dl[1:])
                else:
                    raise InvalidInputError(f"Unexpected diff line: {dl!r}")
            lines[pos:old_idx] = new_lines
            offset += len(new_lines) - (old_idx - pos)

        file_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="devin-orchestrator MCP server")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Optional workspace path to pre-load local config from",
    )
    parser.add_argument(
        "--message-log",
        nargs="?",
        const=str(McpServer.DEFAULT_MESSAGE_LOG),
        default=None,
        help="Log JSON-RPC messages to an NDJSON file (default: %(const)s)",
    )
    parser.add_argument(
        "--mcp-calls-log",
        nargs="?",
        const=str(McpServer.DEFAULT_MCP_CALLS_LOG),
        default=None,
        help="Log structured MCP tool calls to an NDJSON file (default: %(const)s)",
    )
    args = parser.parse_args()
    server = McpServer(
        workspace=args.workspace,
        message_log_path=args.message_log,
        mcp_calls_log_path=args.mcp_calls_log,
    )
    server.run()


if __name__ == "__main__":
    main()

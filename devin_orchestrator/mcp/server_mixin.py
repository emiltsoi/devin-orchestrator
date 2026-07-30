from __future__ import annotations

import atexit
import contextlib
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from devin_orchestrator.config_loader import ConfigLoader  # noqa: E402
from devin_orchestrator.log_rotate import (  # noqa: E402
    cleanup_old_logs,
    rotate_if_needed,
)
from devin_orchestrator.mcp._base import McpServerBase
from devin_orchestrator.mcp_artifacts import (  # noqa: E402
    McpCallLogger,
)
from devin_orchestrator.otel_tracing import trace_span  # noqa: E402
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
)

logger = logging.getLogger(__name__)


class McpServerMixin(McpServerBase):
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
            logger.debug("Failed to join active threads during close", exc_info=True)

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
            {
                "name": "health",
                "description": "Return the health status of the devin-orchestrator installation and active sessions.",
                "inputSchema": {"type": "object", "properties": {}},
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
                with trace_span(
                    "mcp_tool_call", {"tool_name": name, "session_id": "unknown"}
                ) as span:
                    content = self._run_tool(name, arguments)
                    session_id = self._extract_session_id(content)
                    if session_id:
                        span.set_attribute("session_id", session_id)
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

    def _error(self, request: dict, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def _text_content(text: str) -> dict:
        return {"type": "text", "text": text}

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

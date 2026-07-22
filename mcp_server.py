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
import logging
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, IO

import yaml

logger = logging.getLogger(__name__)

# Add workflow-engine to Python path so we can import ConfigLoader and
# security_utils without requiring the harness to be installed as a package.
WORKFLOW_ENGINE_DIR = Path(__file__).parent / "workflow-engine"
sys.path.insert(0, str(WORKFLOW_ENGINE_DIR))

from config_loader import ConfigLoader  # noqa: E402
from security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_session_id,
    validate_skill_name,
    validate_workflow_name,
    validate_workspace_path,
)


class McpServer:
    """Minimal stdio MCP server backed by the devin-orchestrator harness."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "devin-orchestrator"
    SERVER_VERSION = "0.1.0"
    MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    # Rate limiting: max 10 calls per tool per 60-second window
    RATE_LIMIT_MAX_CALLS = 10
    RATE_LIMIT_WINDOW_SECONDS = 60
    # Timeout validation: min 1 second, max 1 hour (3600 seconds)
    DEFAULT_TIMEOUT_SECONDS = 300
    MIN_TIMEOUT_SECONDS = 1
    MAX_TIMEOUT_SECONDS = 3600

    DEFAULT_MESSAGE_LOG = Path.home() / ".devin-orchestrator" / "logs" / "mcp-server.jsonl"

    def __init__(
        self, workspace: str | None = None, message_log_path: str | None = None
    ) -> None:
        self.workspace = workspace
        self.config = ConfigLoader.load(workspace=workspace)
        self.stdin = sys.stdin.buffer
        self.stdout = sys.stdout.buffer
        self._framing: str | None = None  # "ndjson" or "content-length"
        # Rate limiting: track tool call timestamps per tool name
        self._tool_call_history: defaultdict[str, list[float]] = defaultdict(list)
        self._message_log_path: Path | None = None
        self._message_log: IO[str] | None = None
        if message_log_path is not None:
            self._open_message_log(message_log_path)

    def _open_message_log(self, message_log_path: str) -> None:
        """Open the NDJSON message log file, creating its directory if needed."""
        try:
            log_path = Path(message_log_path).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._message_log_path = log_path
            self._message_log = open(
                log_path, "a", encoding="utf-8", buffering=1
            )
            logger.info("MCP message log: %s", log_path)
        except (OSError, ValueError) as e:
            logger.warning("Cannot open MCP message log %s: %s", message_log_path, e)
            self._message_log_path = None
            self._message_log = None

    def _log_message(
        self, direction: str, payload: dict[str, Any] | bytes
    ) -> None:
        """Append a JSON-RPC message (or raw bytes) to the message log."""
        if self._message_log is None:
            return
        try:
            if isinstance(payload, bytes):
                message: Any = {
                    "_raw": payload.decode("utf-8", errors="replace")
                }
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
                "description": "Read a file from a workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "execute",
                "description": "Execute a request with automatic or explicit intent routing.",
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
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "implement",
                "description": "Execute an implementation request using the superpower workflow.",
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
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "review",
                "description": "Execute a review request using the code_review workflow.",
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
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "investigate",
                "description": "Execute an investigation request using the rca workflow.",
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
                "description": "Execute a planning request using the writing-plans skill.",
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
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "run_workflow",
                "description": "Run a specific workflow with a request.",
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
                    },
                    "required": ["session_id", "gate_id", "verdict"],
                },
            },
            {
                "name": "continue_workflow",
                "description": "Resume a workflow that is paused at a gate. Optionally supply a gate verdict.",
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
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "run_skill",
                "description": "Run a specific skill with a request.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "description": "Name of the skill to run",
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
                    },
                    "required": ["skill", "request"],
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

        # Check rate limit for this tool
        if not self._check_rate_limit(name):
            content = [self._text_content(f"Rate limit exceeded for tool '{name}'. Maximum {self.RATE_LIMIT_MAX_CALLS} calls per {self.RATE_LIMIT_WINDOW_SECONDS} seconds.")]
            is_error = True
        else:
            try:
                content = self._run_tool(name, arguments)
                is_error = False
            except (FileNotFoundError, ValueError, InvalidInputError, PathTraversalError) as e:
                content = [self._text_content(f"Error: {e}")]
                is_error = True
            except (KeyError, TypeError) as e:
                content = [self._text_content(f"Invalid arguments: {e}")]
                is_error = True
            except (OSError, RuntimeError) as e:
                content = [self._text_content(f"System error: {e}")]
                is_error = True
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
            timestamp for timestamp in self._tool_call_history[tool_name]
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
            raise InvalidInputError(f"Timeout must be an integer, got {type(timeout).__name__}")

        if timeout < self.MIN_TIMEOUT_SECONDS:
            raise InvalidInputError(f"Timeout must be at least {self.MIN_TIMEOUT_SECONDS} seconds")

        if timeout > self.MAX_TIMEOUT_SECONDS:
            raise InvalidInputError(f"Timeout cannot exceed {self.MAX_TIMEOUT_SECONDS} seconds")

        return timeout

    def _parse_config_overrides(self, config_overrides: Any) -> dict:
        """
        Parse and validate config_overrides parameter.

        Args:
            config_overrides: Config overrides (can be dict, JSON string, or other types)

        Returns:
            Validated config overrides dictionary

        Raises:
            InvalidInputError: If config_overrides is invalid or malformed JSON
        """
        if config_overrides is None:
            return {}

        # If it's already a dict, validate and return it
        if isinstance(config_overrides, dict):
            return self._validate_config_overrides_dict(config_overrides)

        # If it's a string, try to parse as JSON
        if isinstance(config_overrides, str):
            try:
                parsed = json.loads(config_overrides)
                if not isinstance(parsed, dict):
                    raise InvalidInputError(
                        "config_overrides JSON must parse to an object/dictionary"
                    )
                return self._validate_config_overrides_dict(parsed)
            except json.JSONDecodeError as e:
                raise InvalidInputError(
                    f"config_overrides contains malformed JSON: {e}"
                ) from e

        # Any other type is invalid
        raise InvalidInputError(
            f"config_overrides must be a dictionary or JSON string, got {type(config_overrides).__name__}"
        )

    def _validate_config_overrides_dict(self, config_overrides: dict) -> dict:
        """
        Validate that config_overrides dictionary contains only safe values.

        Args:
            config_overrides: Dictionary to validate

        Returns:
            Validated dictionary

        Raises:
            InvalidInputError: If dictionary contains invalid keys or values
        """
        # Validate config_overrides keys are strings and values are basic types
        valid_types = (str, int, float, bool, type(None))
        for key, value in config_overrides.items():
            if not isinstance(key, str):
                raise InvalidInputError(
                    f"config_overrides key must be string, got {type(key).__name__}"
                )
            if not isinstance(value, valid_types):
                raise InvalidInputError(
                    f"config_overrides value for key '{key}' must be basic type (str, int, float, bool, None), got {type(value).__name__}"
                )

        return config_overrides

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
                        data = yaml.safe_load(
                            yaml_file.read_text(encoding="utf-8")
                        ) or {}
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
                use_cases_data = yaml.safe_load(use_cases_file.read_text(encoding="utf-8")) or {}
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
                    data = yaml.safe_load(
                        manifest.read_text(encoding="utf-8")
                    ) or {}
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
            cmd.extend(["--focused-context", str(ctx)])

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        cmd.extend(["--timeout", str(timeout)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(work_dir),
            )
        except subprocess.TimeoutExpired:
            return [self._text_content(
                f"Devin dispatch timed out after {timeout} seconds."
            )]
        text = f"Exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}"
        if result.stderr:
            text += f"\n\nSTDERR:\n{result.stderr}"
        if validated_output_file is not None and validated_output_file.exists():
            text += f"\n\n--- OUTPUT FILE ({validated_output_file}) ---\n"
            text += validated_output_file.read_text(encoding="utf-8")
        return [self._text_content(text)]

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
            overrides = self._parse_config_overrides(arguments.get("config_overrides"))
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

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return [self._text_content(
                f"Skill dispatch timed out after {timeout} seconds."
            )]
        text = f"Exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}"
        if result.stderr:
            text += f"\n\nSTDERR:\n{result.stderr}"
        return [self._text_content(text)]

    def _tool_read_artifact(self, arguments: dict) -> list[dict]:
        """
        Read a file from a workspace.

        Args:
            arguments: Tool arguments containing path, optional session_id and workspace

        Returns:
            List containing file contents

        Raises:
            FileNotFoundError: If file is not found
        """
        from session_manager import resolve_session

        try:
            path = Path(arguments["path"])
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid path parameter: {e}")]

        session_id = arguments.get("session_id")

        # If session_id is provided, resolve the workspace from session
        if session_id:
            try:
                workspace = resolve_session(self.config.session_work_dir, session_id)
            except (FileNotFoundError, ValueError) as e:
                return [self._text_content(f"Failed to resolve session {session_id}: {e}")]
            base = Path(workspace)
        else:
            # Without a session_id, use the caller-supplied workspace (or the
            # server's pre-loaded workspace). Validate it against global_root so
            # a client cannot point at an arbitrary location on the filesystem.
            # Fall back to session_work_dir (never Path.cwd()) when nothing is
            # supplied, keeping reads contained within the harness root.
            workspace = arguments.get("workspace") or self.workspace
            if workspace:
                try:
                    base = validate_workspace_path(
                        workspace, base_allowed_dir=self.config.global_root
                    )
                except (InvalidInputError, PathTraversalError) as e:
                    return [self._text_content(f"Invalid workspace: {e}")]
            else:
                base = self.config.session_work_dir
        try:
            if path.is_absolute():
                target = validate_path_safe(base, path, allow_absolute=True)
            else:
                target = validate_path_safe(base, base / path, allow_absolute=True)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid path: {e}")]

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        return [self._text_content(target.read_text(encoding="utf-8"))]

    def _tool_execute(self, arguments: dict) -> list[dict]:
        """
        Execute a request with automatic or explicit intent routing.

        Args:
            arguments: Tool arguments containing request, intent, demo_mode, timeout

        Returns:
            List containing execution result
        """
        from stateless_orchestrator import StatelessOrchestrator

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        intent = arguments.get("intent", "auto")
        result = orchestrator.execute(request, intent)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_implement(self, arguments: dict) -> list[dict]:
        """
        Execute an implementation request using the superpower workflow.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout

        Returns:
            List containing implementation result
        """
        from stateless_orchestrator import StatelessOrchestrator

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.implement(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_review(self, arguments: dict) -> list[dict]:
        """
        Execute a review request using the code_review workflow.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout

        Returns:
            List containing review result
        """
        from stateless_orchestrator import StatelessOrchestrator

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.review(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_investigate(self, arguments: dict) -> list[dict]:
        """
        Execute an investigation request using the rca workflow.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout

        Returns:
            List containing investigation result
        """
        from stateless_orchestrator import StatelessOrchestrator

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.investigate(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_plan(self, arguments: dict) -> list[dict]:
        """
        Execute a planning request using the writing-plans skill.

        Args:
            arguments: Tool arguments containing request, demo_mode

        Returns:
            List containing planning result
        """
        from stateless_orchestrator import StatelessOrchestrator

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            demo_mode=arguments.get("demo_mode", False),
        )
        request = arguments["request"]
        result = orchestrator.plan(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_run_workflow(self, arguments: dict) -> list[dict]:
        """
        Run a specific workflow with a request.

        Args:
            arguments: Tool arguments containing workflow, request, demo_mode, timeout

        Returns:
            List containing workflow execution result
        """
        from stateless_orchestrator import StatelessOrchestrator

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
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
        result = orchestrator.run_workflow(workflow_name, request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_gate_decision(self, arguments: dict) -> list[dict]:
        """
        Write a gate decision to the session's gate decision file.

        Args:
            arguments: Tool arguments containing session_id, gate_id, verdict, notes

        Returns:
            List containing success message
        """
        from session_manager import resolve_session

        session_id = arguments.get("session_id")
        gate_id = arguments.get("gate_id")
        verdict = arguments.get("verdict")
        notes = arguments.get("notes", "")

        if not all([session_id, gate_id, verdict]):
            return [self._text_content("session_id, gate_id, and verdict are required")]

        try:
            session_dir = resolve_session(self.config.session_work_dir, session_id)
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

        Args:
            arguments: Tool arguments containing session_id and optional gate verdict

        Returns:
            List containing continuation result
        """
        from stateless_orchestrator import StatelessOrchestrator

        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        result = orchestrator.continue_workflow(
            session_id=session_id,
            gate_verdict=arguments.get("gate_verdict"),
            gate_notes=arguments.get("gate_notes"),
            gate_id=arguments.get("gate_id"),
        )
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_run_skill(self, arguments: dict) -> list[dict]:
        """
        Run a specific skill with a request.

        Args:
            arguments: Tool arguments containing skill, request, demo_mode, timeout

        Returns:
            List containing skill execution result
        """
        from stateless_orchestrator import StatelessOrchestrator

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = StatelessOrchestrator(
            workspace=self.workspace,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
        )
        skill = arguments["skill"]
        request = arguments["request"]
        result = orchestrator.run_skill(skill, request)
        return [self._text_content(json.dumps(result, indent=2))]

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
        finally:
            if self._message_log is not None:
                try:
                    self._message_log.close()
                except OSError:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="devin-orchestrator MCP server")
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
    args = parser.parse_args()
    server = McpServer(
        workspace=args.workspace,
        message_log_path=args.message_log,
    )
    server.run()


if __name__ == "__main__":
    main()

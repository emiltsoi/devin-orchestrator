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
import logging
from pathlib import Path

from devin_orchestrator.mcp.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_MESSAGE_SIZE,
    MAX_OUTPUT_BYTES,
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    RATE_LIMIT_MAX_CALLS,
    RATE_LIMIT_WINDOW_SECONDS,
)

logger = logging.getLogger(__name__)

# security_utils without requiring the harness to be installed as a package.

try:
    import yaml  # noqa: F401
except ModuleNotFoundError as e:
    raise SystemExit(
        "The PyYAML package is required. Install it with: pip install PyYAML>=5.1"
    ) from e

from devin_orchestrator import __version__  # noqa: E402
from devin_orchestrator.mcp.artifact_mixin import McpArtifactMixin  # noqa: E402
from devin_orchestrator.mcp.dispatch_mixin import McpDispatchMixin  # noqa: E402
from devin_orchestrator.mcp.prompts_mixin import McpPromptsMixin  # noqa: E402
from devin_orchestrator.mcp.resources_mixin import McpResourcesMixin  # noqa: E402
from devin_orchestrator.mcp.security_mixin import McpSecurityMixin  # noqa: E402
from devin_orchestrator.mcp.server_mixin import McpServerMixin  # noqa: E402
from devin_orchestrator.mcp.tools_mixin import McpToolsMixin  # noqa: E402
from devin_orchestrator.mcp_artifacts import (  # noqa: E402
    McpCallLogger,
)


class McpServer(
    McpServerMixin,
    McpToolsMixin,
    McpDispatchMixin,
    McpArtifactMixin,
    McpPromptsMixin,
    McpResourcesMixin,
    McpSecurityMixin,
):
    """Minimal stdio MCP server backed by the devin-orchestrator harness."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "devin-orchestrator"
    SERVER_VERSION = __version__
    MAX_MESSAGE_SIZE = MAX_MESSAGE_SIZE
    # Maximum bytes of subprocess output to keep per stdout/stderr stream.
    # Larger outputs are truncated before being returned to MCP clients.
    MAX_OUTPUT_BYTES = MAX_OUTPUT_BYTES
    # Rate limiting: max 10 calls per tool per 60-second window
    RATE_LIMIT_MAX_CALLS = RATE_LIMIT_MAX_CALLS
    RATE_LIMIT_WINDOW_SECONDS = RATE_LIMIT_WINDOW_SECONDS
    # Timeout validation: min 1 second, max 1 hour (3600 seconds)
    DEFAULT_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS
    MIN_TIMEOUT_SECONDS = MIN_TIMEOUT_SECONDS
    MAX_TIMEOUT_SECONDS = MAX_TIMEOUT_SECONDS

    DEFAULT_MESSAGE_LOG = (
        Path.home() / ".devin-orchestrator" / "logs" / "mcp-server.jsonl"
    )
    DEFAULT_MCP_CALLS_LOG = (
        McpCallLogger.DEFAULT_LOG_DIR / "mcp-calls.jsonl"
    )


def main(argv: list[str] | None = None) -> None:
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
    args = parser.parse_args(argv)
    server = McpServer(
        workspace=args.workspace,
        message_log_path=args.message_log,
        mcp_calls_log_path=args.mcp_calls_log,
    )
    server.run()


if __name__ == "__main__":
    main()

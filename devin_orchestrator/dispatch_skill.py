#!/usr/bin/env python3
"""
Dispatch skill to Devin via skill_invoker

If you are an agent connected to the devin-orchestrator MCP server, use the
`mcp0_dispatch_skill` MCP tool instead of this script. This script is a legacy
CLI fallback for environments without the MCP server.

This script is a lightweight wrapper for skill_invoker.invoke_skill() that can be called
from bash to dispatch skills to Devin.
"""

import argparse
import json
import os
import sys

# This works regardless of installation location
from devin_orchestrator import __version__
from devin_orchestrator.config_loader import ConfigLoader
from devin_orchestrator.security_utils import (
    InvalidInputError,
    parse_config_overrides,
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
)
from devin_orchestrator.skill_invoker import SkillInvoker


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dispatch-skill",
        description="Dispatch a devin-orchestrator skill.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    # Positional form (legacy) and optional form (new unified CLI).
    parser.add_argument("skill_name", nargs="?", help="Name of the skill to dispatch")
    parser.add_argument("session_id", nargs="?", help="Session identifier")
    parser.add_argument("workspace", nargs="?", help="Workspace directory")
    parser.add_argument(
        "is_reviewer", nargs="?", default="false", help="Run skill in reviewer mode"
    )
    parser.add_argument("demo_mode", nargs="?", default="false", help="Use demo mode")
    parser.add_argument(
        "config_overrides_json", nargs="?", default=None, help="JSON config overrides"
    )

    parser.add_argument("--skill-name", dest="skill_name", help="Name of the skill")
    parser.add_argument("--session-id", dest="session_id", help="Session identifier")
    parser.add_argument("--workspace", dest="workspace", help="Workspace directory")
    parser.add_argument(
        "--is-reviewer", dest="is_reviewer_flag", action="store_true"
    )
    parser.add_argument("--demo-mode", dest="demo_mode_flag", action="store_true")
    parser.add_argument(
        "--config-overrides", dest="config_overrides_json", help="JSON config overrides"
    )
    return parser.parse_args(argv)


def _coerce_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    skill_name = args.skill_name
    session_id = args.session_id
    workspace = args.workspace
    is_reviewer = args.is_reviewer_flag or _coerce_bool(args.is_reviewer)
    demo_mode = args.demo_mode_flag or _coerce_bool(args.demo_mode)
    config_overrides_json = args.config_overrides_json

    if not skill_name or not session_id or not workspace:
        print(
            "Usage: dispatch-skill <skill_name> <session_id> <workspace>",
            file=sys.stderr,
        )
        return 1

    # Load config first so we can constrain workspace validation to the
    # configured session work directory. Workspace-local config overrides
    # global settings when available.
    config = ConfigLoader.load(workspace=workspace)

    # Validate and sanitize inputs
    try:
        skill_name = validate_skill_name(skill_name)
        session_id = validate_session_id(session_id)
        # Validate against global_root to match the MCP server"s containment
        # check. session_work_dir is a subdirectory of global_root, so this
        # accepts any workspace the MCP server would accept (including those
        # under global_root but outside session_work_dir).
        workspace = str(
            validate_workspace_path(workspace, base_allowed_dir=config.global_root)
        )
    except InvalidInputError as e:
        print(f"Input validation error: {e}", file=sys.stderr)
        return 1

    # Parse config overrides if provided
    try:
        config_overrides = parse_config_overrides(config_overrides_json)
    except InvalidInputError as e:
        print(f"Input validation error: {e}", file=sys.stderr)
        return 1

    # Create skill invoker
    skill_invoker = SkillInvoker(demo_mode=demo_mode)

    # Prepare context
    context = {
        "session_id": session_id,
        "stage": skill_name,
        "skill": skill_name,
        "config_overrides": config_overrides,
    }

    # Invoke skill
    result = skill_invoker.invoke_skill(
        skill_name=skill_name,
        context=context,
        workspace=workspace,
        is_reviewer=is_reviewer,
        config_overrides=config_overrides,
    )

    # Output result as JSON
    output = {
        "success": result.success,
        "session_id": result.session_id,
        "output": result.output,
        "error": result.error,
    }

    print(json.dumps(output, indent=2))

    # Exit with appropriate code
    code = 0 if result.success else 1
    if argv is None:
        sys.exit(code)
    return code


def shim() -> int:
    """Deprecated legacy entry point; routes through the unified CLI."""
    import warnings

    warnings.warn(
        "dispatch-skill is deprecated; use 'devin-orchestrator dispatch' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    os.environ["DEVIN_ORCHESTRATOR_NO_DEPRECATION"] = "1"
    from devin_orchestrator.cli import main as cli_main

    return cli_main(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

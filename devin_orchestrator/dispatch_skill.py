#!/usr/bin/env python3
"""
Dispatch skill to Devin via skill_invoker

If you are an agent connected to the devin-orchestrator MCP server, use the
`mcp0_dispatch_skill` MCP tool instead of this script. This script is a legacy
CLI fallback for environments without the MCP server.

This script is a lightweight wrapper for skill_invoker.invoke_skill() that can be called
from bash to dispatch skills to Devin.
"""

import json
import sys


# This works regardless of installation location

from devin_orchestrator.config_loader import ConfigLoader
from devin_orchestrator.security_utils import (
    InvalidInputError,
    parse_config_overrides,
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
)
from devin_orchestrator.skill_invoker import SkillInvoker


def main():
    # Parse command line arguments
    if len(sys.argv) < 4:
        print(
            "Usage: dispatch_skill.py <skill_name> <session_id> <workspace> [is_reviewer] [demo_mode] [config_overrides]"
        )
        sys.exit(1)

    skill_name = sys.argv[1]
    session_id = sys.argv[2]
    workspace = sys.argv[3]
    is_reviewer = len(sys.argv) > 4 and sys.argv[4].lower() == "true"
    demo_mode = len(sys.argv) > 5 and sys.argv[5].lower() == "true"
    config_overrides_json = sys.argv[6] if len(sys.argv) > 6 else None

    # Load config first so we can constrain workspace validation to the
    # configured session work directory. Workspace-local config overrides
    # global settings when available.
    config = ConfigLoader.load(workspace=workspace)

    # Validate and sanitize inputs
    try:
        skill_name = validate_skill_name(skill_name)
        session_id = validate_session_id(session_id)
        # Validate against global_root to match the MCP server's containment
        # check. session_work_dir is a subdirectory of global_root, so this
        # accepts any workspace the MCP server would accept (including those
        # under global_root but outside session_work_dir).
        workspace = str(
            validate_workspace_path(workspace, base_allowed_dir=config.global_root)
        )
    except InvalidInputError as e:
        print(f"Input validation error: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse config overrides if provided
    try:
        config_overrides = parse_config_overrides(config_overrides_json)
    except InvalidInputError as e:
        print(f"Input validation error: {e}", file=sys.stderr)
        sys.exit(1)

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
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
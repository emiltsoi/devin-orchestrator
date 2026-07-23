#!/usr/bin/env python3
"""
Dispatch skill to Devin via skill_invoker

If you are an agent connected to the devin-orchestrator MCP server, use the
`mcp0_dispatch_skill` MCP tool instead of this script. This script is a legacy
CLI fallback for environments without the MCP server.

This script is a lightweight wrapper for skill_invoker.invoke_skill() that can be called
from bash to dispatch skills to Devin.
"""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

# Add workflow-engine to Python path using script location
# This works regardless of installation location
script_dir = Path(__file__).parent
workflow_engine_dir = script_dir / "workflow-engine"
if workflow_engine_dir.exists():
    sys.path.insert(0, str(workflow_engine_dir))
else:
    # Fallback to relative import if script is in workflow-engine directory
    if script_dir.name == "workflow-engine":
        sys.path.insert(0, str(script_dir))
    else:
        # Last resort: try the global installation path
        global_path = Path.home() / ".devin-orchestrator" / "workflow-engine"
        if global_path.exists():
            sys.path.insert(0, str(global_path))

from config_loader import ConfigLoader
from security_utils import (
    InvalidInputError,
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
)
from skill_invoker import SkillInvoker


def main():
    parser = argparse.ArgumentParser(
        description="Dispatch a skill to Devin. Legacy CLI fallback for the mcp0_dispatch_skill tool."
    )
    parser.add_argument("skill_name", help="Name of the skill to dispatch")
    parser.add_argument("session_id", help="Session identifier")
    parser.add_argument("workspace", help="Workspace/session directory path")
    parser.add_argument("is_reviewer", nargs="?", default="false", help="true if reviewer stage")
    parser.add_argument("demo_mode", nargs="?", default="false", help="true for simulated dispatch")
    parser.add_argument("config_overrides_json", nargs="?", default=None, help="JSON config overrides")
    parser.add_argument("--focused-context", dest="focused_context", action="append", default=[], help="File paths to inject as focused context")
    parser.add_argument("--output-file", dest="output_file", default=None, help="Path to write structured output report")
    args = parser.parse_args()

    skill_name = args.skill_name
    session_id = args.session_id
    workspace = args.workspace
    is_reviewer = args.is_reviewer.lower() == "true"
    demo_mode = args.demo_mode.lower() == "true"
    config_overrides_json = args.config_overrides_json

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
            validate_workspace_path(
                workspace, base_allowed_dir=config.global_root
            )
        )
    except InvalidInputError as e:
        print(f"Input validation error: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse config overrides if provided
    config_overrides = {}
    if config_overrides_json:
        try:
            config_overrides = json.loads(config_overrides_json)
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON for config_overrides: {config_overrides_json}")

    # Create skill invoker
    skill_invoker = SkillInvoker(demo_mode=demo_mode)

    # Prepare context
    context = {
        'session_id': session_id,
        'stage': skill_name,
        'skill': skill_name,
        'config_overrides': config_overrides
    }

    # Invoke skill
    result = skill_invoker.invoke_skill(
        skill_name=skill_name,
        context=context,
        workspace=workspace,
        is_reviewer=is_reviewer,
        config_overrides=config_overrides,
        focused_context=args.focused_context or None,
    )

    # If an output file was requested, write the worker output there as well
    output_file_path = None
    if args.output_file:
        try:
            from security_utils import validate_path_safe
            output_file = validate_path_safe(Path(workspace), Path(args.output_file), allow_absolute=True)
            output_file.write_text(result.output or "", encoding="utf-8")
            output_file_path = str(output_file)
        except Exception as e:
            logger.warning(f"Failed to write output_file: {e}")

    # Build artifact list from workspace files if available
    artifact_paths = []
    workspace_path = Path(workspace)
    if output_file_path:
        artifact_paths.append(output_file_path)
    if workspace_path.exists():
        for f in sorted(workspace_path.iterdir()):
            if f.is_file() and f.name not in {".session.json", "session.json"}:
                artifact_paths.append(str(f))

    # Output result as JSON
    output = {
        "success": result.success,
        "session_id": result.session_id,
        "workspace": workspace,
        "output": result.output,
        "error": result.error,
        "output_file": output_file_path,
        "artifact_paths": artifact_paths,
    }

    print(json.dumps(output, indent=2))

    # Exit with appropriate code
    sys.exit(0 if result.success else 1)

if __name__ == "__main__":
    main()

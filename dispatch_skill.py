#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dispatch skill to Devin via skill_invoker

This script is a lightweight wrapper for skill_invoker.invoke_skill() that can be called
from bash to dispatch skills to Devin. This allows Cascade to dispatch skills using the bash tool.

The wrapper is necessary because Cascade cannot import Python modules directly, but can use
the bash tool to execute scripts.
"""

import sys
import json
from pathlib import Path

# Add global orchestrator to Python path
sys.path.insert(0, str(Path.home() / ".devin-orchestrator" / "workflow-engine"))

from skill_invoker import SkillInvoker
from config_loader import ConfigLoader
from security_utils import (
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
    InvalidInputError
)

def main():
    # Parse command line arguments
    if len(sys.argv) < 4:
        print("Usage: dispatch_skill.py <skill_name> <session_id> <workspace> [is_reviewer] [demo_mode] [config_overrides]")
        sys.exit(1)
    
    skill_name = sys.argv[1]
    session_id = sys.argv[2]
    workspace = sys.argv[3]
    is_reviewer = len(sys.argv) > 4 and sys.argv[4].lower() == 'true'
    demo_mode = len(sys.argv) > 5 and sys.argv[5].lower() == 'true'
    config_overrides_json = sys.argv[6] if len(sys.argv) > 6 else None
    
    # Validate and sanitize inputs
    try:
        skill_name = validate_skill_name(skill_name)
        session_id = validate_session_id(session_id)
        workspace = str(validate_workspace_path(workspace))
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
    
    # Load config
    config = ConfigLoader.load()
    
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
        config_overrides=config_overrides
    )
    
    # Output result as JSON
    output = {
        'success': result.success,
        'session_id': result.session_id,
        'output': result.output,
        'error': result.error
    }
    
    print(json.dumps(output, indent=2))
    
    # Exit with appropriate code
    sys.exit(0 if result.success else 1)

if __name__ == "__main__":
    main()

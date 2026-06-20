#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dispatch skill to Devin via skill_invoker

This script is a wrapper for skill_invoker.invoke_skill() that can be called
from bash to dispatch skills to Devin. This allows Cascade to dispatch skills
using the bash tool.
"""

import sys
import json
from pathlib import Path

# Add global orchestrator to Python path
sys.path.insert(0, str(Path.home() / ".devin-orchestrator" / "workflow-engine"))

from skill_invoker import SkillInvoker
from config_loader import ConfigLoader

def main():
    # Parse command line arguments
    if len(sys.argv) < 4:
        print("Usage: dispatch_skill.py <skill_name> <session_id> <workspace> [is_reviewer] [demo_mode]")
        sys.exit(1)
    
    skill_name = sys.argv[1]
    session_id = sys.argv[2]
    workspace = sys.argv[3]
    is_reviewer = len(sys.argv) > 4 and sys.argv[4].lower() == 'true'
    demo_mode = len(sys.argv) > 5 and sys.argv[5].lower() == 'true'
    
    # Load config
    config = ConfigLoader.load()
    
    # Create skill invoker
    skill_invoker = SkillInvoker(demo_mode=demo_mode)
    
    # Prepare context
    context = {
        'session_id': session_id,
        'stage': skill_name,
        'skill': skill_name
    }
    
    # Invoke skill
    result = skill_invoker.invoke_skill(
        skill_name=skill_name,
        context=context,
        workspace=workspace,
        is_reviewer=is_reviewer
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

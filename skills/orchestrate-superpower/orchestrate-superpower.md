---
name: orchestrate-superpower
description: "Use when orchestrating a multi-stage superpower workflow that dispatches each stage skill to Devin via dispatch_skill.py."
---

# Orchestrate Superpower Workflow

You are the orchestrator. Your job is to load the superpower manifest and execute each stage using dispatch_skill.py to dispatch Devin, reasoning through results and making triage decisions.

## Process

### 1. Load Manifest
- Read `workflows/superpower.manifest.yaml`
- Parse stages, skills, gates, and artifacts
- Understand the workflow structure

### 2. Execute Stages
For each stage in the manifest:
- Check if stage is optional and should be skipped
- If `skip_brainstorming` is true and stage is brainstorming: skip stage
- If stage is skipped: create placeholder artifacts and continue
- Load skill definition and narrative
- **Dispatch skill using dispatch_skill.py to call Devin**
- Read output artifacts
- Validate structural floor (no TODO, no placeholders, non-empty)
- Reason about results
- Make triage decision (proceed/retry/escalate)
- Handle gate if present

### 2.1. Skipping Brainstorming
When the spec is already clear, you can skip brainstorming:
- Set `skip_brainstorming: true` in the manifest
- Or set it via environment/session context
- When skipped: create a minimal design.md placeholder
- Continue to next stage (using-git-worktrees)

Skip logic:
```python
if manifest.get('skip_brainstorming', False) and stage['name'] == 'brainstorming':
    # Create minimal design.md placeholder
    design_placeholder = f"# Design\n\nSkipping brainstorming - spec is clear.\n\nRequest: {request_content}\n"
    (session_dir / 'design.md').write_text(design_placeholder)
    continue to next stage
```

### 3. Skill Invocation (IMPORTANT)
You MUST use the dispatch_skill.py script to dispatch Devin. Do NOT execute the skill yourself - dispatch it to Devin.

Use the bash tool to call dispatch_skill.py:
```bash
python ~/.devin-orchestrator/dispatch_skill.py <skill_name> <session_id> <workspace> [is_reviewer] [demo_mode] [config_overrides]
```

Example:
```bash
python ~/.devin-orchestrator/dispatch_skill.py brainstorming SUPERPOWER-001 ~/.devin-orchestrator/work/SUPERPOWER-001 false true
```

Parameters:
- skill_name: Name of the skill to dispatch (e.g., brainstorming, writing-plans)
- session_id: Session identifier (e.g., SUPERPOWER-001)
- workspace: Path to session directory
- is_reviewer: true if this is a reviewer stage (requesting-code-review), false otherwise
- demo_mode: true for testing (simulated dispatch), false for production (real Devin dispatch)
- config_overrides: Optional JSON string with configuration overrides (e.g., '{"interactive_mode": true}')

### 3.1. Managing Interactive vs Non-Interactive Mode

The brainstorming skill supports two modes:
- **Non-interactive mode (default)**: Makes reasonable assumptions, proceeds autonomously
- **Interactive mode**: Asks questions one at a time, waits for human responses

**How to determine which mode to use:**
- Check the orchestrate-superpower skill configuration for `interactive_mode` setting
- If `interactive_mode: true` in configuration, pass `{"interactive_mode": true}` as config_overrides to brainstorming
- If `interactive_mode: false` (default), pass `{"interactive_mode": false}` or omit config_overrides

**Example dispatch with interactive mode:**
```bash
python ~/.devin-orchestrator/dispatch_skill.py brainstorming SUPERPOWER-001 ~/.devin-orchestrator/work/SUPERPOWER-001 false false '{"interactive_mode": true}'
```

**Example dispatch with non-interactive mode (default):**
```bash
python ~/.devin-orchestrator/dispatch_skill.py brainstorming SUPERPOWER-001 ~/.devin-orchestrator/work/SUPERPOWER-001 false false
```

The script returns JSON output with success, session_id, output, and error fields.

### 4. Structural Floor Validation
Check each output artifact:
- File exists
- File is not empty
- No TODO placeholders
- No PLACEHOLDER text

If structural floor fails: triage decision = retry

### 5. Triage Decision
Based on:
- Skill invocation success/failure
- Structural floor validation
- Reviewer verdict (if reviewer stage)
- Gate status (if gate present)

Decisions:
- `proceed`: Continue to next stage
- `retry`: Retry current stage (with feedback)
- `escalate`: Escalate to human (stop workflow)

### 6. Gate Handling
If stage has a gate:
- In production: Wait for human decision (approve/request changes/block)
- In demo mode: Simulate approval
- If gate blocks: Stop workflow
- If gate requests changes: Return to implementation stage

### 7. Session Management
- Create session directory: `~/.devin-orchestrator/work/{session_id}/`
- Create initial artifacts: request.md, status.md, session-audit.md
- Update status.md after each stage
- Append to session-audit.md after each stage

## Important
- You are the orchestrator, not a mechanical script
- **You MUST use dispatch_skill.py via bash tool to dispatch Devin for each stage**
- Do NOT execute skills yourself - dispatch them to Devin
- Reason through each stage's results
- Make intelligent triage decisions
- Handle gates appropriately
- Stop workflow if escalation needed

---
name: orchestrate-superpower
description: "Use when a multi-stage superpower workflow is needed. Prefer mcp0_run_workflow('superpower') for end-to-end automation; only dispatch per stage manually when you need agent-level control over each stage."
---

# Orchestrate Superpower Workflow

Your job is to run the full superpower methodology end-to-end. The engine can do this automatically; only orchestrate stage-by-stage manually when you need explicit control over each stage.

## Process

### 1. Load Manifest
- Read `workflows/superpower.manifest.yaml`
- Parse stages, skills, gates, and artifacts
- Understand the workflow structure

### 2. Preferred path: end-to-end with `mcp0_run_workflow`
Call the devin-orchestrator MCP tool `mcp0_run_workflow` with `workflow: "superpower"`. The engine runs all 7 stages, handles gates, and returns a structured result.

Arguments:
- `workflow`: `"superpower"`
- `request`: the feature or bug-fix request
- `demo_mode`: `true` for simulation (no real Devin dispatches)
- `gate_mode`: `"auto"` to auto-approve bypassable gates (recommended); `"signal"` to return a `resume` ticket for agent decisions; `"interactive"` to wait for human
- `focused_context`: optional file paths to seed into every stage
- `output_file`: optional path for a final summary report

Example MCP tool call:
```json
{
  "name": "mcp0_run_workflow",
  "arguments": {
    "workflow": "superpower",
    "request": "Implement a stateless MCP dispatch contract for high-quality dispatches",
    "demo_mode": true,
    "gate_mode": "auto",
    "output_file": "output/superpower-report.md"
  }
}
```

Handle the result:
- If `final_status` is `completed`, the workflow is done.
- If `final_status` is `waiting_for_input`, `escalated`, or `blocked`, read the `resume` ticket and call the indicated next MCP tool (`mcp0_gate_decision`, `mcp0_continue_workflow`, etc.).

### 2.1. Skipping Brainstorming
When the spec is already clear, pass `skip_brainstorming: true` to `mcp0_run_workflow`. The engine creates a minimal `design.md` placeholder and starts at `using-git-worktrees`.

You can also set `skip_brainstorming: true` in `workflows/superpower.manifest.yaml` to make skipping the default.

### 3. Fallback: Per-Stage Dispatch
Only use this section if `mcp0_run_workflow` is unavailable or the workflow returned a `resume` ticket instructing you to dispatch a specific stage manually.

For each stage in `workflows/superpower.manifest.yaml`:
- Check if stage is optional and should be skipped
- If `skip_brainstorming` is true and stage is `brainstorming`: skip stage and create placeholder `design.md`
- Load skill definition and narrative
- Dispatch the stage skill with `mcp0_dispatch_skill` (or `dispatch_skill` if your client does not prefix tool names)
- Read output artifacts
- Validate structural floor (no TODO, no placeholders, non-empty)
- Reason about results and make triage decision (proceed/retry/escalate)
- Handle gate if present

Example MCP tool call:
```json
{
  "name": "mcp0_dispatch_skill",
  "arguments": {
    "skill_name": "brainstorming",
    "session_id": "SUPERPOWER-001",
    "workspace": "C:/Users/<username>/.devin-orchestrator/work/SUPERPOWER-001",
    "is_reviewer": false,
    "demo_mode": true,
    "config_overrides": {"interactive_mode": true}
  }
}
```

If you do not have MCP tool access, use the `dispatch_skill.py` script via bash:
```bash
python ~/.devin-orchestrator/dispatch_skill.py <skill_name> <session_id> <workspace> [is_reviewer] [demo_mode] [config_overrides]
```

The tool/script returns JSON output with `success`, `session_id`, `output`, `error`, `output_file`, and `artifact_paths`.

### 3.1. Managing Interactive vs Non-Interactive Mode

The brainstorming skill supports two modes:
- **Non-interactive mode (default)**: Makes reasonable assumptions, proceeds autonomously
- **Interactive mode**: Asks questions one at a time, waits for human responses

**How to determine which mode to use:**
- Check the orchestrate-superpower skill configuration for `interactive_mode` setting
- If `interactive_mode: true` in configuration, pass `{"interactive_mode": true}` as `config_overrides` to `mcp0_dispatch_skill` (or the script)
- If `interactive_mode: false` (default), pass `{"interactive_mode": false}` or omit `config_overrides`

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
- **Prefer `mcp0_run_workflow` with `workflow: "superpower"` for end-to-end automation.**
- Only dispatch per stage manually as a fallback or when the engine returns a `resume` ticket that requires it.
- Do NOT execute skills yourself - let the engine run the workflow or dispatch skills to Devin
- Reason through results and make intelligent triage decisions
- Handle gates appropriately
- Stop workflow if escalation needed

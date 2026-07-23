# Stateless MCP Dispatch Plan

## Context

The devin-orchestrator MCP server already exposes high-level tools (`implement`, `review`, `investigate`, `plan`, `run_workflow`, `run_skill`, `dispatch_devin`, `dispatch_skill`) and gate control tools (`gate_decision`, `continue_workflow`). The previous fix stopped agents from defaulting to `run_skill` and from calling Python scripts directly. The next tightening is to make the MCP tools feel native to a **stateless agent**: every call carries all required context, every result returns enough information to continue without hidden state.

## Problem

A stateless agent (no memory between tool calls) cannot do high-quality dispatches today because:

1. **Missing focused context** — `run_skill`, `run_workflow`, and the intent wrappers (`implement`, `review`, etc.) do not accept `focused_context` file paths, so the worker may not see the exact files it needs.
2. **No explicit output artifact** — `run_skill` and `dispatch_skill` do not accept an `output_file` parameter, so the agent cannot tell the worker where to write its report.
3. **No artifact list in results** — tool results do not return `artifact_paths`, forcing the agent to guess which files were produced.
4. **Unclear resume contract** — when a workflow pauses at a gate or escalates, the result is nested JSON/text and does not pre-fill the arguments for the next MCP tool call.
5. **No correction/redispatch path** — `continue_workflow` does not accept a `correction_artifact` or `feedback` parameter, so an agent cannot hand a fix back to a failed stage.

## Design Principles

1. **Self-contained calls** — every tool accepts all inputs the worker needs (`request`, `focused_context`, `output_file`, `model`, `role`, `gate_mode`).
2. **Structured, actionable results** — every result is JSON with `success`, `output`, `error`, `session_id`, `workspace`, `artifact_paths`, and a `resume` block.
3. **Resume tickets** — when a workflow pauses or escalates, the result contains a `resume` object with `tool`, `arguments`, and `then` (next tool) so the agent can continue without remembering prior context.
4. **Process vs implementation split remains** — `run_skill` stays for process skills; `dispatch_devin`/`dispatch_skill` are focused dispatch; `run_workflow`/`implement` are full methodologies.

## Proposed Tool Contracts

### `dispatch_devin` (already close)

**Inputs:** `role`, `prompt_file`, `work_dir`, `focused_context[]`, `model`, `agent`, `phase`, `output_file`, `timeout`

**Result:**
```json
{
  "success": true,
  "output": "<worker output>",
  "error": null,
  "workspace": "...",
  "output_file": ".../output.md",
  "artifact_paths": [".../output.md"],
  "exit_code": 0
}
```

### `dispatch_skill`

**Inputs:** add `focused_context[]` and `output_file`. Keep `skill_name`, `session_id`, `workspace`, `is_reviewer`, `demo_mode`, `config_overrides`, `timeout`.

**Result:** same shape as `dispatch_devin`.

### `run_skill`

**Inputs:** add `focused_context[]`, `output_file`, and `workspace` (project root for context). Keep `skill`, `request`, `demo_mode`, `timeout`.

**Result:**
```json
{
  "session_id": "SKILL-001",
  "workspace": ".../work/SKILL-001",
  "success": true,
  "output": "<worker output>",
  "error": null,
  "artifact_paths": [".../work/SKILL-001/plan.md"],
  "output_file": ".../work/SKILL-001/plan.md"
}
```

### `run_workflow`, `implement`, `review`, `investigate`, `plan`, `execute`

**Inputs:** add `focused_context[]` and `output_file` (for `plan`/`execute` single-shot reports). Keep `request`, `demo_mode`, `timeout`, `gate_mode`.

**Result:**
```json
{
  "session_id": "SUPERPOWER-001",
  "workspace": ".../work/SUPERPOWER-001",
  "success": false,
  "final_status": "waiting_for_input",
  "stage": "planning",
  "gate_id": "g2_plan_approval",
  "error": null,
  "output": "<full workflow output>",
  "artifact_paths": [".../work/SUPERPOWER-001/design.md", ".../work/SUPERPOWER-001/plan.md"],
  "resume": {
    "tool": "mcp0_gate_decision",
    "arguments": {
      "session_id": "SUPERPOWER-001",
      "gate_id": "g2_plan_approval",
      "verdict": "approve|request_changes|block",
      "notes": "<agent fills this in>"
    },
    "then": {
      "tool": "mcp0_continue_workflow",
      "arguments": { "session_id": "SUPERPOWER-001" }
    }
  }
}
```

### `gate_decision`

**Inputs:** `session_id`, `gate_id`, `verdict`, `notes`

**Result:** a structured JSON message confirming the decision and reminding the agent to call `continue_workflow`.

### `continue_workflow`

**Inputs:** add `correction_artifact` and `feedback` for retry after escalation. Keep `session_id`, `gate_verdict`, `gate_notes`, `gate_id`, `config_overrides`, `gate_mode`.

**Result:** same shape as `run_workflow`.

## Gate / Escalation Resume Contract

When a gate or escalation happens, the tool result must be a **resume ticket**:

```json
{
  "final_status": "waiting_for_input | escalated | blocked | completed",
  "session_id": "<id>",
  "workspace": "<path>",
  "stage": "<failing stage>",
  "gate_id": "<id or null>",
  "error": "<error or null>",
  "artifact_paths": ["<paths to read>"],
  "resume": {
    "tool": "<next MCP tool name>",
    "arguments": { "<pre-filled args>" }
  }
}
```

For `waiting_for_input`:
- `resume.tool` = `mcp0_gate_decision`
- `resume.arguments` = `{ session_id, gate_id, verdict, notes }`
- `resume.then.tool` = `mcp0_continue_workflow`

For `escalated`:
- `resume.tool` = `mcp0_continue_workflow`
- `resume.arguments` = `{ session_id, correction_artifact: "...", gate_mode: "auto" }`

For `blocked`:
- `resume` may be null or point to `mcp0_read_artifact` so the agent can inspect artifacts before deciding.

## Implementation Steps

1. **Add `focused_context` and `output_file` to tool schemas** (`mcp_server.py` `_tool_specs`).
2. **Update `dispatch_skill.py`** to accept `--focused-context` and `--output-file` arguments and return structured JSON.
3. **Update `StatelessOrchestrator.run_skill`** to accept `focused_context`, `output_file`, pass `focused_context` to `SkillInvoker.invoke_skill`, and return `artifact_paths`.
4. **Update `StatelessOrchestrator.run_workflow`** to accept `focused_context`, seed/copy files into the session, pass `focused_context` into the `OrchestrationEngine`, and return `artifact_paths`.
5. **Update `OrchestrationEngine`** to:
   - persist `request`, `focused_context`, and `manifest` in `session.json`;
   - accept `correction_artifact`/`feedback` in `continue_workflow` and pass it to the failing stage;
   - build the `resume` block for gate/escalation results.
6. **Update `mcp_server.py` tool methods** to wrap results with `resume` tickets and `artifact_paths`.
7. **Update `MCP-CLIENTS.md`** and the MCP usage prompt with the new result contract.
8. **Add tests** for the new resume/artifact behavior (or at least syntax checks).
9. **Bump version, commit, tag, deploy.**

## Files to Edit

- `mcp_server.py` — tool specs, tool methods, result wrapping
- `dispatch_skill.py` — argument parsing, JSON output
- `workflow-engine/stateless_orchestrator.py` — `run_skill`, `run_workflow`
- `workflow-engine/orchestration_engine.py` — `execute_workflow`, `continue_workflow`, gate/escalation resume, session persistence
- `workflow-engine/session_manager.py` — helper for session state persistence
- `MCP-CLIENTS.md` — usage and result contract docs
- `mcp_server.py` prompts — update usage guide

## Success Criteria

- `dispatch_devin` and `dispatch_skill` accept `focused_context` and `output_file` and return structured JSON with `artifact_paths`.
- `run_skill` accepts `focused_context` and `output_file` and returns `artifact_paths`.
- `run_workflow`/`implement`/`review`/`investigate`/`plan`/`execute` accept `focused_context` and return `artifact_paths`.
- When a workflow pauses at a gate, the tool result contains a `resume` block with the exact arguments for `mcp0_gate_decision` and `mcp0_continue_workflow`.
- When a workflow escalates, the result contains a `resume` block for `mcp0_continue_workflow` with a `correction_artifact` argument.
- `MCP-CLIENTS.md` documents the new stateless dispatch and resume contract.

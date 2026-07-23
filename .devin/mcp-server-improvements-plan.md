# MCP Server Improvements Plan

## Problem

When a Devin/Cascade agent loads the devin-orchestrator MCP server, it defaults to `run_skill` for implementation tasks (e.g. `executing-plans`). This produces broad, shallow passes because the MCP tool descriptions are neutral, the tool list ordering buries the high-level tools, and `run_skill` strips away project context and skill narrative.

## Goals

1. Make the right tool obvious from its name and description.
2. Prevent `run_skill` from being used as a generic implementation tool.
3. Ensure `run_skill` actually runs the skill it names (with iron law, checklist, and narrative).
4. Update client documentation so users and agents know which tool to pick.

## Steps

### Step 1 — Rewrite MCP tool descriptions and ordering (`mcp_server.py`)

Update `_tool_specs()` so each description is prescriptive and encodes the decision tree. Reorder the list from highest-level to lowest-level tools.

High-level intent tools first:

- `execute` — auto-router; preferred default for most requests.
- `implement` — `superpower` workflow; for feature/bug-fix implementation.
- `review` — `code_review` workflow.
- `investigate` — `rca` workflow.
- `plan` — `writing-plans` skill.
- `run_workflow` — run any named workflow explicitly.

Lower-level / special-purpose tools after:

- `run_skill` — process-skill runner only; explicitly warn against implementation use.
- `dispatch_devin` — focused single-shot Devin worker with `focused_context`, `model`, `output_file`.
- `dispatch_skill` — dispatch a named skill as a Devin worker.
- `list_workflows`, `get_workflow`, `list_skills`, `get_skill`, `read_artifact` — discovery.
- `gate_decision`, `continue_workflow` — gate control.

Also add missing `description` fields for `dispatch_devin` parameters (`model`, `output_file`, `phase`, `agent`).

### Step 2 — Add runtime guard in `_tool_run_skill` (`mcp_server.py`)

Before running an implementation-oriented skill (`executing-plans`, `subagent-driven-development`, `test-driven-development`, `writing-plans` with implementation intent) without `focused_context` or a referenced plan artifact, return a structured warning that points the agent to `implement` or `dispatch_devin`.

### Step 3 — Fix `StatelessOrchestrator.run_skill` (`stateless_orchestrator.py`)

Stop passing `custom_prompt=request` to `SkillInvoker.invoke_skill`. Instead pass the request in `context` so `SkillInvoker.build_skill_prompt` prepends the skill name, iron law, announcement, checklist, and narrative. The worker then follows the actual skill discipline.

### Step 4 — Update `MCP-CLIENTS.md`

Add a “Which tool should I use?” section at the top with a short decision tree, and reorder examples to show `implement` and `dispatch_devin` first.

### Step 5 (Optional) — Add MCP `prompts` capability

Expose a server prompt `devin-orchestrator-usage` via MCP `prompts/list` and `prompts/get`. This gives clients that read prompts a concise usage guide. This step is optional; tool descriptions and guardrails are the priority.

## Success Criteria

- `tools/list` returns descriptions that steer an agent away from `run_skill` for implementation.
- `run_skill` with `executing-plans` and a vague request returns a warning/suggestion rather than a shallow execution.
- `run_skill` with a process skill produces a prompt containing the skill narrative and iron law.
- `MCP-CLIENTS.md` documents the decision tree.

## Files to Edit

- `mcp_server.py`
- `workflow-engine/stateless_orchestrator.py`
- `MCP-CLIENTS.md`
- (Optional) `mcp_server.py` for prompts capability

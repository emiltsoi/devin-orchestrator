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

### Step 6 — Improve stateless-agent ergonomics for `continue_workflow`

The current `mcp0_continue_workflow` / `mcp0_gate_decision` split forces a stateless agent to remember `session_id`, gate id, stage, and the exact resume schema. The `SUPERPOWER-005` hang also shows that calling `continue_workflow` with only `session_id` re-runs the failing stage with no new feedback, producing long or non-blocking retries. Add:

1. **Generic `mcp0_resume` tool** that accepts the whole `resume` object returned by a previous run and dispatches the correct underlying tool (`continue_workflow`, `gate_decision`, etc.). A stateless agent then only has to copy `resume` and fill in `verdict`/`notes`/`feedback`.
2. **Smart `mcp0_continue_workflow` defaults:**
   - If the session is `escalated`/`blocked` and no `feedback` or `correction_artifact` is supplied, return immediately with the resume ticket instead of re-executing the failing stage.
   - Auto-detect the failing stage/gate from `session.json` so `gate_id` and `stage` arguments are optional.
   - Add `timeout` and `demo_mode` parameters to `mcp0_continue_workflow` (currently missing).
3. **Session introspection tools:** add `mcp0_list_sessions` and `mcp0_get_session_status` so an agent can discover `session_id`s and see `final_status`, current stage, and available next actions without reading files directly.
4. **`mcp0_cancel_workflow`**: allow an agent to abort a stuck/hung session (e.g. the `SUPERPOWER-005` retry loop) without manually killing processes.
5. **Self-contained resume responses:** every workflow tool result should include `done: bool` and `next_step: <action>` so a stateless agent can tell at a glance whether to call another tool or stop.
6. **`run_workflow`/`implement` plan seeding:** accept a `plan_artifact` path and a `skip_brainstorming` flag so agents can hand an existing plan (e.g. `plan-review-fixes.md`) directly to `mcp0_run_workflow` instead of running `brainstorming` again.

### Step 7 — Cleanup redundant workflows, skills, and MCP tools

Based on the redundancy audit, the following items should be deprecated, merged, or removed.

#### Workflows

- **Delete `devin-support.manifest.yaml` / `devin-support.runbook.md`**
  - Already marked deprecated; it is a one-stage wrapper around `orchestrate-superpower`, which itself routes to `mcp0_run_workflow('superpower')`.
- **Merge `pr_review` into `code_review`**
  - Only stage 0 differs (`pr_url` fetch vs. local `code_diff`/`files_to_review`).
  - Add an optional `pr_url` input to `code_review.manifest.yaml`.
  - Stage 0 branches on `pr_url` presence: fetch PR details + diff, or load local diff.
  - Normalize stage 0 outputs to `code_context.md` + `diff.md` so stages 1-3 remain unchanged.
  - Keep `pr_review` as a thin deprecated alias (or remove it after a transition period).

#### Skills

- **Delete `orchestrate-superpower` skill** (or deprecate)
  - It duplicates the `superpower` workflow and the deprecated `devin-support` workflow.
- **Clarify `executing-plans` vs. `subagent-driven-development`**
  - `executing-plans` is for same-context execution; `subagent-driven-development` is for multi-subagent orchestration.
  - Document the split in `skills/README.md` and hide `executing-plans` from generic dispatch unless explicitly requested.
- **Review `requesting-code-review` / `receiving-code-review` / `swe-compliance` / `adversarial-review`**
  - These are all reviewer-oriented roles. Decide on one canonical reviewer skill (`swe-compliance`) and one receiver (`receiving-code-review`); merge or deprecate the others.

#### MCP tools

- **Deprecate/remove `implement`, `review`, `investigate`, `plan`**
  - They are aliases for `execute` with a fixed `intent` or for `run_workflow`/`run_skill`.
  - Keep `execute`, `run_workflow`, and `run_skill` as the canonical tools.
  - If aliases are needed, implement them as thin `execute` wrappers inside `mcp_server.py` without separate tool definitions.
- **Deprecate/remove `dispatch_skill`**
  - `dispatch_devin` covers focused single-shot Devin dispatch; `run_skill` covers process-skill execution in a fresh session.
- **Replace `gate_decision` + `continue_workflow` with `mcp0_resume`**
  - See Step 6.

#### Ordering

1. Merge `code_review`/`pr_review` and remove `devin-support` first (no MCP code changes).
2. Remove deprecated MCP tool definitions (`implement`, `review`, etc.) and consolidate aliases.
3. Remove `orchestrate-superpower` skill once `devin-support` is gone.
4. Replace `gate_decision`/`continue_workflow` with `mcp0_resume`.

## Files to Edit

- `mcp_server.py`
- `workflow-engine/stateless_orchestrator.py`
- `workflow-engine/orchestration_engine.py`
- `workflows/code_review.manifest.yaml`
- `workflows/code_review.runbook.md`
- `workflows/pr_review.manifest.yaml` (deprecate or delete)
- `workflows/pr_review.runbook.md` (deprecate or delete)
- `.devin/workflows/devin-support.manifest.yaml` (delete)
- `.devin/workflows/devin-support.runbook.md` (delete)
- `skills/orchestrate-superpower/` (deprecate or delete)
- `MCP-CLIENTS.md`
- (Optional) `mcp_server.py` for prompts capability

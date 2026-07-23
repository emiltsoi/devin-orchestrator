# Plan: Stateless MCP Agent Interface

## Goal
A stateless agent (or any MCP client) can perform the software work defined in the harness through high-level MCP tools without knowing about session IDs, prompt files, roles, workspaces, or internal harness paths.

## Background
The current MCP server exposes low-level building blocks:
- `dispatch_devin` — requires `role`, `prompt_file`, `work_dir`.
- `dispatch_skill` — requires `skill_name`, `session_id`, `workspace`.
- `list/get` skills and workflows — good for discovery, but still require the caller to interpret them.

This forces the caller to understand harness internals. The new tools hide that complexity.

## Capability inventory

| Intent | Workflow | Skill fallback |
|---|---|---|
| implement / build feature | `superpower` | `subagent-driven-development`, `test-driven-development` |
| review code | `code_review` | `code-review`, `swe-compliance` |
| review PR | `pr_review` | `requesting-code-review` |
| investigate / debug | `rca` | `systematic-debugging` |
| plan / design | - | `brainstorming`, `writing-plans` |
| finish branch | - | `finishing-a-development-branch`, `verification-before-completion` |
| route / meta | - | `using-devin-orchestrator` |

## Proposed MCP tools

1. **`execute(request, intent="auto")`**
   - If `intent` is `"auto"`, load the `using-devin-orchestrator` skill and route the request to the best workflow/skill.
   - Otherwise dispatch the matching workflow/skill directly.
   - Returns session ID, workspace path, and result/next-step prompt.

2. **`implement(request)`** — wrapper for `superpower` workflow (or `subagent-driven-development` skill as fallback).

3. **`review(request)`** — wrapper for `code_review` workflow (or `code-review` skill).

4. **`investigate(request)`** — wrapper for `rca` workflow (or `systematic-debugging` skill).

5. **`plan(request)`** — wrapper for `writing-plans` skill.

6. **`run_workflow(workflow, request)`** — generic. Auto-creates session workspace, builds prompt, runs the workflow orchestrator or matching skill.

7. **`run_skill(skill, request)`** — generic. Auto-creates session workspace, builds prompt, dispatches the skill.

8. **`read_artifact(path, session_id=None)`** — existing, but add optional `session_id` so the agent does not need to remember the full workspace path.

## Implementation phases

### Phase 1: Session manager
- New helper module `workflow-engine/session_manager.py`:
  - `create_session(workflow_or_skill_name) -> (session_id, workspace_path)`
  - Generates IDs from `session_id_format` in `use-cases.yaml` (e.g. `SUPERPOWER-NNN`).
  - Creates `~/.devin-orchestrator/work/<session_id>/`.
  - Avoids collisions by scanning existing directories.

### Phase 2: Prompt builder
- Helper to write `prompt.md` from the user request.
- Optionally prepend skill/workflow instructions from `get_skill` / `get_workflow`.

### Phase 3: MCP tool implementation
- Add new `_tool_*` methods in `mcp_server.py` (or a new `mcp_stateless.py` module imported by `mcp_server.py`).
- Register them in `tools/list`.
- Internally use existing `dispatch_devin` / `dispatch_skill` logic with auto-generated `work_dir`, `prompt_file`, `workspace`, `session_id`.

### Phase 4: Installer and docs
- Update `install.py` to copy new modules.
- Update `MCP-CLIENTS.md` with stateless examples.

### Phase 5: Verification
- `mcp0_implement("add a small feature...")` with no paths/roles.
- `mcp0_review("review the harness")`.
- Confirm artifacts under `~/.devin-orchestrator/work/<session_id>`.

## Trade-offs
- More abstraction means slightly less control. Advanced users still keep `dispatch_devin` / `dispatch_skill`.
- Adds one round-trip to generate session/prompt, but removes all caller-side setup.


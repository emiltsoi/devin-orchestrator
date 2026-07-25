# MCP Client Configuration

`mcp_server.py` exposes `devin-orchestrator` skills, workflows, and dispatch as an [MCP](https://modelcontextprotocol.io) server over stdio. Any MCP-compatible client can connect.

## Choosing the right tool

The `tools/list` response is ordered from highest-level to lowest-level. Pick the first tool that matches your task:

1. **General / unsure:** `execute` — auto-routes to the right workflow or skill.
2. **Implement a feature or fix:** `execute` with `intent: implement` (or `run_workflow` with `workflow: superpower`).
3. **Review code or a PR:** `execute` with `intent: review` (or `run_workflow` with `workflow: code_review`). Provide `pr_url` or `code_diff`/`files_to_review` in the request.
4. **Investigate a bug or incident:** `execute` with `intent: investigate` (or `run_workflow` with `workflow: rca`).
5. **Create an implementation plan:** `execute` with `intent: plan` (or `run_skill` with `skill: writing-plans`).
6. **Run a process skill only** (`brainstorming`, `writing-plans`, `systematic-debugging`): `run_skill`.
7. **Resume a gate or escalated workflow:** `resume` — pass the `resume` object from a previous result.
8. **Focused single-shot worker** with exact files and acceptance criteria: `dispatch_devin`.
9. **Inspect or cancel sessions:** `list_sessions`, `get_session_status`, `cancel_workflow`.

**Avoid `run_skill` for implementation, review, or investigation tasks.** `run_skill` is a low-level process-skill runner. For coding work, use `execute`, `run_workflow`, or `dispatch_devin`.

For gates and escalations, use `resume` instead of calling `gate_decision` and `continue_workflow` separately.

**Note for agents:** The `py -3.14 install.py` and `py -3.14 mcp_server.py` commands below are for configuring the *MCP client* (Claude Desktop, Cursor, etc.). If you are already connected to the devin-orchestrator MCP server, use the MCP tools in `tools/list` instead of running these commands.

## Server installation

Install the harness globally first:

```powershell
py -3.14 install.py
```

This copies `mcp_server.py` into `~/.devin-orchestrator/`.

## Client configuration examples

### Claude Desktop (stdio)

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "devin-orchestrator": {
      "command": "py",
      "args": [
        "-3.14",
        "C:/Users/<username>/.devin-orchestrator/mcp_server.py"
      ]
    }
  }
}
```

### Claude Desktop with a default workspace

```json
{
  "mcpServers": {
    "devin-orchestrator": {
      "command": "py",
      "args": [
        "-3.14",
        "C:/Users/<username>/.devin-orchestrator/mcp_server.py",
        "--workspace",
        "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a"
      ]
    }
  }
}
```

### Cursor / OpenClaw / generic stdio MCP

Most clients accept a command array:

```json
{
  "name": "devin-orchestrator",
  "command": ["py", "-3.14", "C:/Users/<username>/.devin-orchestrator/mcp_server.py"]
}
```

## Available tools

### High-level intent / workflow tools (preferred)
- `execute` — auto-route by intent (`auto`, `implement`, `review`, `investigate`, `plan`)
- `run_workflow` — run a named workflow explicitly (`superpower`, `code_review`, `rca`)
- `run_skill` — **process skills only** (`brainstorming`, `writing-plans`, `systematic-debugging`). Not for implementation/review/investigation; use `execute`, `run_workflow`, or `dispatch_devin`.
- `dispatch_devin` — focused single-shot Devin worker with role, prompt file, and optional `focused_context` / `output_file`

### Session introspection and control
- `list_sessions` — list all sessions and their current status
- `get_session_status` — inspect one session (manifest, stage, status, artifacts)
- `cancel_workflow` — mark a session as cancelled and terminate the running background workflow / Devin subprocess
- `resume` — resume a gate or escalated workflow using the `resume` object from a previous result

### Discovery / read-only
- `list_skills`
- `get_skill`
- `list_workflows`
- `get_workflow`
- `read_artifact`

### Low-level gate control (prefer `resume`)
- `gate_decision` — submit `approve` | `request_changes` | `block`
- `continue_workflow` — resume a workflow at a gate or after an escalation

## Tool usage examples

### Implement a feature or fix

```json
{
  "name": "execute",
  "arguments": {
    "request": "Add a thumbnail cache with on-disk persistence to the picture browser.",
    "intent": "implement",
    "gate_mode": "auto",
    "timeout": 1200
  }
}
```

### Focused follow-up fix

For small, focused changes, use `dispatch_devin` with a prompt file and `focused_context`:

```json
{
  "name": "dispatch_devin",
  "arguments": {
    "role": "coder",
    "prompt_file": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a/prompt-followup.md",
    "work_dir": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a",
    "focused_context": ["src/App.tsx", "src/zoom.ts", "tests/unit/zoom.test.ts"],
    "output_file": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a/result-followup.md",
    "model": "swe-1.6",
    "timeout": 900
  }
}
```

### Dispatch a process skill

```json
{
  "name": "run_skill",
  "arguments": {
    "skill": "brainstorming",
    "request": "Explore how to add lazy image dimension loading to the picture browser."
  }
}
```

### Review a change

```json
{
  "name": "execute",
  "arguments": {
    "request": "Review the changes in workflow-engine/mcp_server.py for MCP protocol compliance.",
    "intent": "review",
    "gate_mode": "signal",
    "demo_mode": false,
    "timeout": 600
  }
}
```

### Run a workflow

```json
{
  "name": "run_workflow",
  "arguments": {
    "workflow": "code_review",
    "request": "Review the changes in workflow-engine/mcp_server.py",
    "gate_mode": "auto",
    "timeout": 600
  }
}
```

### Resume a gate or escalated workflow

Use the `resume` tool with the `resume` block from a previous result. For a gate, supply `verdict` and optional `notes`:

```json
{
  "name": "resume",
  "arguments": {
    "resume": {
      "tool": "mcp0_gate_decision",
      "arguments": {
        "session_id": "CODEREVIEW-009",
        "gate_id": "g1_approval_decision",
        "verdict": "approve|request_changes|block",
        "notes": ""
      },
      "then": {
        "tool": "mcp0_continue_workflow",
        "arguments": {"session_id": "CODEREVIEW-009"}
      }
    },
    "verdict": "approve",
    "notes": "Looks good"
  }
}
```

For an escalation, supply `feedback`:

```json
{
  "name": "resume",
  "arguments": {
    "resume": {
      "tool": "mcp0_continue_workflow",
      "arguments": {
        "session_id": "SUPERPOWER-042",
        "feedback": "<Provide correction/feedback for the 'brainstorming' stage>"
      }
    },
    "feedback": "The plan is missing a test strategy; add unit tests for Cache.ts."
  }
}
```

### Auto-routed execution

```json
{
  "name": "execute",
  "arguments": {
    "request": "Implement a logging helper for the orchestrator.",
    "intent": "auto",
    "gate_mode": "signal",
    "timeout": 600
  }
}
```

## Message logging / replay

For troubleshooting and backtracing, the server can log every JSON-RPC request and response to an NDJSON file:

```json
{
  "mcpServers": {
    "devin-orchestrator": {
      "command": "py",
      "args": [
        "-3.14",
        "C:/Users/<username>/.devin-orchestrator/mcp_server.py",
        "--message-log",
        "C:/Users/<username>/.devin-orchestrator/logs/mcp-server.jsonl"
      ]
    }
  }
}
```

`--message-log` with no value defaults to `~/.devin-orchestrator/logs/mcp-server.jsonl`. Each line contains `timestamp`, `direction` (`in`/`out`), and the message payload.

## Stateless result contract

All MCP tools return **structured, self-contained JSON** results. A stateless agent does not need to remember context between calls because the result contains everything needed to continue:

- `session_id` — identifier for the session.
- `workspace` — absolute path to the session/work directory.
- `success` — `true` only when `final_status` is `completed`.
- `final_status` — `completed | waiting_for_input | escalated | blocked | failed`.
- `done` — `true` when the workflow has completed; `false` when it is waiting/escalated/blocked.
- `next_step` — the MCP tool to call next (usually `resume`, or `null` when `done`).
- `output` — human-readable text or a JSON summary.
- `error` — error message when `success` is `false`.
- `artifact_paths` — list of files produced during the run.
- `output_file` — path to the requested structured report, if any.
- `resume` — when the run is not `done`, a pre-filled ticket for the next MCP call:
  - `tool` — the MCP tool to call next.
  - `arguments` — exact argument object for that tool (fill in `verdict`/`notes`/`feedback`).
  - `then` — for gates, the follow-up call after `gate_decision`.

### Focused context and output file

High-level tools accept `focused_context` (list of file paths) and `output_file`:

```json
{
  "name": "run_workflow",
  "arguments": {
    "workflow": "superpower",
    "request": "Add a thumbnail cache with on-disk persistence to the picture browser.",
    "focused_context": ["src/App.tsx", "src/Cache.ts"],
    "output_file": "output/thumbnail-cache-report.md",
    "gate_mode": "auto",
    "timeout": 1200
  }
}
```

The files are copied into the session workspace so subagents can read them safely.

### Resuming after a gate

When `final_status` is `waiting_for_input`, the result contains a `resume` block. Copy it into the `resume` tool and fill in `verdict` and `notes`:

```json
{
  "name": "resume",
  "arguments": {
    "resume": {
      "tool": "mcp0_gate_decision",
      "arguments": {
        "session_id": "SUPERPOWER-042",
        "gate_id": "g2_plan_approval",
        "verdict": "approve|request_changes|block",
        "notes": ""
      },
      "then": {
        "tool": "mcp0_continue_workflow",
        "arguments": {"session_id": "SUPERPOWER-042"}
      }
    },
    "verdict": "approve",
    "notes": "Looks good"
  }
}
```

The `resume` tool submits the gate decision and automatically calls `continue_workflow`.

### Resuming after an escalation

When `final_status` is `escalated`, copy the `resume` block into the `resume` tool and supply correction `feedback`:

```json
{
  "name": "resume",
  "arguments": {
    "resume": {
      "tool": "mcp0_continue_workflow",
      "arguments": {
        "session_id": "SUPERPOWER-042",
        "feedback": "<Provide correction/feedback for the 'brainstorming' stage>"
      }
    },
    "feedback": "The plan is missing a test strategy; add unit tests for Cache.ts.",
    "focused_context": ["src/Cache.ts"]
  }
}
```

Calling `continue_workflow` with only `session_id` (no `feedback`, `correction_artifact`, or `gate_verdict`) returns the resume ticket without re-running the failing stage. Use this to check the current state before deciding how to proceed.

### Session introspection and cancellation

Discover sessions and inspect their status without reading files directly:

```json
{
  "name": "list_sessions"
}
```

```json
{
  "name": "get_session_status",
  "arguments": {
    "session_id": "SUPERPOWER-042"
  }
}
```

To terminate a running session, use `cancel_workflow`. It writes a cancel token to the session and kills the recorded Devin subprocess PID:

```json
{
  "name": "cancel_workflow",
  "arguments": {
    "session_id": "SUPERPOWER-042"
  }
}
```

## Deployment notes

- The MCP server uses the global `~/.devin-orchestrator/` skills and workflows by default.
- Per-workspace overrides are read from `<workspace>/.devin-orchestrator/config.yaml` when a `workspace` or `work_dir` argument is passed.
- `devin_cli_path` must be valid in `config.yaml` for the host running the server.
- Workflow/orchestration tools (`execute`, `run_workflow`) accept:
  - `focused_context`: list of file paths to copy into the session for each stage.
  - `output_file`: optional path (relative to the session) for a final summary report.
  - `gate_mode`: `interactive` (block and wait), `signal` (return immediately at gates), or `auto` (evaluate bypass conditions). Default is `auto`.
  - `demo_mode`: if `true`, simulate subagent dispatches instead of calling real Devin workers.
  - `timeout`: per-dispatch timeout in seconds.
- `continue_workflow` accepts `correction_artifact` (path) or `feedback` (inline text) to retry an escalated stage.

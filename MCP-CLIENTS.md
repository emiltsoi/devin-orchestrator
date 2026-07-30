# MCP Client Configuration

`mcp_server.py` exposes `devin-orchestrator` skills, workflows, and dispatch as an [MCP](https://modelcontextprotocol.io) server over stdio. Any MCP-compatible client can connect.

## Choosing the right tool

The `tools/list` response is ordered from highest-level to lowest-level. Pick the first tool that matches your task:

1. **General / unsure:** `execute` — auto-routes to the right workflow or skill.
2. **Implement a feature or fix:** `implement` — runs the full `superpower` workflow.
3. **Review code or a PR:** `review` — runs the `code_review` workflow.
4. **Investigate a bug or incident:** `investigate` — runs the `rca` workflow (read-only).
5. **Create an implementation plan:** `plan` — runs the `writing-plans` skill.
6. **Run a specific workflow:** `run_workflow` with a `workflow` name.
7. **Run a process skill only** (`brainstorming`, `writing-plans`, `systematic-debugging`): `run_skill`.
8. **Focused single-shot worker** with exact files and acceptance criteria: `dispatch_devin`.

**Avoid `run_skill` for implementation tasks.** `run_skill` is a low-level process-skill runner. For coding work, `implement`, `run_workflow`, or `dispatch_devin` carry the right context and produce focused results.

**Note for agents:** If you are already connected to the devin-orchestrator MCP server, use the MCP tools in `tools/list` instead of running the commands below.

## Server installation

Install with [pipx](https://pypa.github.io/pipx/) (recommended) or `pip`, then create the service and register the MCP server with your agents:

```bash
pipx install devin-orchestrator
devin-orchestrator install
```

On Windows:

```powershell
py -3.14 -m pip install devin-orchestrator
py -3.14 -m devin_orchestrator.cli install
```

`devin-orchestrator install` registers the server in Claude Desktop, Cursor, Windsurf, and other agent configs automatically. See [DEPLOY.md](DEPLOY.md) for dry-run mode, system installs, and uninstall/upgrade.

## Client configuration examples

The exact command that `devin-orchestrator install` writes depends on your system. You can see it with:

```bash
devin-orchestrator register --snippet
```

### Claude Desktop (stdio)

A typical pip/pipx install produces this in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "devin-orchestrator": {
      "command": "devin-orchestrator",
      "args": ["mcp"]
    }
  }
}
```

If the console script is not on the agent's PATH, use the full path:

```json
{
  "mcpServers": {
    "devin-orchestrator": {
      "command": "/home/<username>/.local/bin/devin-orchestrator",
      "args": ["mcp"]
    }
  }
}
```

### Claude Desktop with a default workspace

```json
{
  "mcpServers": {
    "devin-orchestrator": {
      "command": "devin-orchestrator",
      "args": [
        "mcp",
        "--workspace",
        "/home/<username>/work/hermes-agent-a2a"
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
  "command": ["devin-orchestrator", "mcp"]
}
```

If the console script is not on the agent's PATH, fall back to the module:

```json
{
  "name": "devin-orchestrator",
  "command": ["python3", "-m", "devin_orchestrator.mcp_server"]
}
```

## Available tools

### High-level intent / workflow tools (preferred)
- `execute` — auto-route by intent (`auto`, `implement`, `review`, `investigate`, `plan`)
- `implement` — implement a feature or fix using the `superpower` workflow
- `review` — review code using the `code_review` workflow
- `investigate` — investigate an incident/bug using the `rca` workflow (read-only)
- `plan` — create a `writing-plans` implementation plan
- `run_workflow` — run any named workflow explicitly

### Focused single-shot dispatch
- `dispatch_devin` — dispatch a focused Devin worker with a role, prompt file, and optional `focused_context` / `output_file`
- `dispatch_skill` — dispatch a Devin worker to execute a named skill in a workspace

### Discovery / read-only
- `list_skills`
- `get_skill`
- `list_workflows`
- `get_workflow`
- `read_artifact`

### Low-level skill / gate control
- `run_skill` — **process skills only** (`brainstorming`, `writing-plans`, `systematic-debugging`). Not for implementation; use `implement`, `run_workflow`, or `dispatch_devin` for coding tasks.
- `gate_decision` — submit `approve` | `request_changes` | `block`
- `continue_workflow` — resume a workflow paused at a gate

## Tool usage examples

### Implement a feature or fix

```json
{
  "name": "implement",
  "arguments": {
    "request": "Add a thumbnail cache with on-disk persistence to the picture browser.",
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
  "name": "review",
  "arguments": {
    "request": "Review the changes in devin_orchestrator/mcp_server.py for MCP protocol compliance.",
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
    "request": "Review the changes in devin_orchestrator/mcp_server.py",
    "gate_mode": "auto",
    "timeout": 600
  }
}
```

### Submit a gate decision and continue

```json
{
  "name": "gate_decision",
  "arguments": {
    "session_id": "CODEREVIEW-009",
    "gate_id": "g1_approval_decision",
    "verdict": "approve",
    "notes": "Looks good"
  }
}
```

```json
{
  "name": "continue_workflow",
  "arguments": {
    "session_id": "CODEREVIEW-009",
    "gate_verdict": "approve",
    "gate_id": "g1_approval_decision"
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
      "command": "devin-orchestrator",
      "args": [
        "mcp",
        "--message-log",
        "C:/Users/<username>/.devin-orchestrator/logs/mcp-server.jsonl"
      ]
    }
  }
}
```

You can also pass `--message-log` to `devin-orchestrator install` so every registered agent config includes it:

```bash
devin-orchestrator install --message-log
```

`--message-log` with no value defaults to `~/.devin-orchestrator/logs/mcp-server.jsonl`. Each line contains `timestamp`, `direction` (`in`/`out`), and the message payload.

## Deployment notes

- The MCP server uses the global `~/.devin-orchestrator/` skills and workflows by default.
- Per-workspace overrides are read from `<workspace>/.devin-orchestrator/config.yaml` when a `workspace` or `work_dir` argument is passed.
- `devin_cli_path` must be valid in `config.yaml` for the host running the server.
- Workflow/orchestration tools (`execute`, `implement`, `review`, `investigate`, `run_workflow`) accept:
  - `gate_mode`: `interactive` (block and wait), `signal` (return immediately at gates), or `auto` (evaluate bypass conditions). Default is `auto`.
  - `demo_mode`: if `true`, simulate subagent dispatches instead of calling real Devin workers.
  - `timeout`: per-dispatch timeout in seconds.

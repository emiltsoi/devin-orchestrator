# MCP Client Configuration

`mcp_server.py` exposes `devin-orchestrator` skills, workflows, and dispatch as an [MCP](https://modelcontextprotocol.io) server over stdio. Any MCP-compatible client can connect.

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

### Discovery / read-only
- `list_skills`
- `get_skill`
- `list_workflows`
- `get_workflow`
- `read_artifact`

### Low-level Devin dispatch
- `dispatch_devin`
- `dispatch_skill`

### High-level intent / workflow tools
- `execute` — auto-route by intent (`auto`, `implement`, `review`, `investigate`, `plan`)
- `implement` — `superpower` workflow
- `review` — `code_review` workflow
- `investigate` — `rca` workflow
- `plan` — `writing-plans` skill
- `run_workflow` — run any workflow by name
- `run_skill` — run any skill by name

### Gate control
- `gate_decision` — submit `approve` | `request_changes` | `block`
- `continue_workflow` — resume a workflow paused at a gate

## Tool usage examples

### Dispatch a skill

```json
{
  "name": "dispatch_skill",
  "arguments": {
    "skill_name": "brainstorming",
    "session_id": "SESSION-001",
    "workspace": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a"
  }
}
```

### Dispatch a generic Devin run

```json
{
  "name": "dispatch_devin",
  "arguments": {
    "role": "coder",
    "prompt_file": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a/prompt.md",
    "work_dir": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a",
    "output_file": "C:/Users/<username>/OneDrive/Documents/Work/hermes-agent-a2a/result.md",
    "timeout": 1200
  }
}
```

### Review a change

```json
{
  "name": "review",
  "arguments": {
    "request": "Review the changes in workflow-engine/mcp_server.py for MCP protocol compliance.",
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

## Deployment notes

- The MCP server uses the global `~/.devin-orchestrator/` skills and workflows by default.
- Per-workspace overrides are read from `<workspace>/.devin-orchestrator/config.yaml` when a `workspace` or `work_dir` argument is passed.
- `devin_cli_path` must be valid in `config.yaml` for the host running the server.
- Workflow/orchestration tools (`execute`, `implement`, `review`, `investigate`, `run_workflow`) accept:
  - `gate_mode`: `interactive` (block and wait), `signal` (return immediately at gates), or `auto` (evaluate bypass conditions). Default is `auto`.
  - `demo_mode`: if `true`, simulate subagent dispatches instead of calling real Devin workers.
  - `timeout`: per-dispatch timeout in seconds.

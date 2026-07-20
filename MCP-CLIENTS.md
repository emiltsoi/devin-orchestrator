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

- `list_skills`
- `get_skill`
- `list_workflows`
- `get_workflow`
- `dispatch_devin`
- `dispatch_skill`
- `read_artifact`

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

## Deployment notes

- The MCP server uses the global `~/.devin-orchestrator/` skills and workflows by default.
- Per-workspace overrides are read from `<workspace>/.devin-orchestrator/config.yaml` when a `workspace` or `work_dir` argument is passed.
- `devin_cli_path` must be valid in `config.yaml` for the host running the server.

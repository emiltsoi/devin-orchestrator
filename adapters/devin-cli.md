# Devin CLI Transport Adapter

## Overview

Transport adapter for Devin CLI using the Agent Client Protocol (ACP). This adapter provides automated session spawning, prompt dispatch, and structured output via JSON-RPC 2.0 over stdin/stdout.

## Capabilities

- **fresh_session_spawn**: Can spawn fresh Devin sessions via `session/new`
- **context_isolation**: Each dispatch gets isolated context
- **file_operations**: Can read/write files via Devin tools
- **terminal_commands**: Can execute terminal commands via Devin tools
- **native_subagent_dispatch**: Has native ACP sub-agent dispatch mechanism
- **structured_output**: Provides per-turn metadata via `session/update`

## Dispatch Contract

### Inputs

- `prompt_file` - Path to prompt file containing dispatch instructions
- `workspace_path` - Path to target workspace
- `model_config` - Model configuration (default: SWE-1.6)

### Outputs

- `stdout_file` - Path to file containing agent stdout
- `stderr_file` - Path to file containing agent stderr
- `session_metadata` - Session metadata (tokens, time, model, etc.)

### Quality Bar

- `exit_code_zero` - Process exited successfully
- `no_timeout` - Completed within time limit
- `artifact_exists` - Expected output artifact exists
- `acp_response_valid` - ACP response is valid JSON-RPC

## ACP Protocol

### How it works

Devin CLI runs as an ACP server speaking JSON-RPC 2.0 over stdin/stdout with LSP-style `Content-Length` framing.

### ACP Methods

**Client → Agent (requests):**

| Method | Purpose |
|---|---|
| `initialize` | Protocol handshake, capabilities exchange |
| `authenticate` | Supply credentials at runtime |
| `session/new` | Create a new agent session |
| `session/load` | Resume an existing session by ID |
| `session/set_mode` | Switch between Normal / Plan / Bypass |
| `session/set_config_option` | Update model, permissions, or config mid-session |
| `session/prompt` | Send a user prompt (one turn) |
| `session/cancel` | Cancel an in-flight turn |
| `session/list` | List sessions |

**Agent → Client (requests + notifications):**

| Method | Purpose |
|---|---|
| `session/update` | Streaming update — assistant text, tool calls, state transitions |
| `session/request_permission` | Ask the client to approve a tool call |
| `session/elicitation` | Agent asks a structured question of the user |
| `fs/read_text_file` | Read file through the client (for sandboxed clients) |
| `fs/write_text_file` | Write file through the client |
| `terminal/create`, `terminal/output`, `terminal/release`, `terminal/wait_for_exit`, `terminal/kill` | Terminal multiplexing via the client |

### Usage Pattern

```bash
# Invoke Devin as ACP server
devin acp

# Client sends JSON-RPC requests via stdin
{"jsonrpc": "2.0", "method": "session/new", "params": {...}, "id": 1}
{"jsonrpc": "2.0", "method": "session/prompt", "params": {...}, "id": 2}
```

### Structured Output

`session/update` carries per-turn metadata:
- `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`
- `committed_credit_cost`, `committed_acu_cost`
- `ttft_ms`, `total_time_ms`
- `generation_model`, `finish_reason`

## Limitations

- **max_prompt_tokens**: 1,000,000 tokens (Opus 4.7 family, 1M variants)
- **max_session_duration**: 3600 seconds (1 hour)
- **requires_devin_cli**: Must have `devin` CLI installed
- **acp_protocol_required**: Must use ACP protocol (not `-p` mode)

## Model Selection

**Default**: SWE-1.6

**Model aliases** (from devin-orchestrator-notes.md):
- `swe-1-6` - SWE-1.6 (200K context)
- `swe-1-6-fast` - SWE-1.6 Fast (200K context)
- `claude-opus-4-7-low` - Opus 4.7 low-effort (1M context)
- `gpt-5-4-mini-low` - GPT-5.4 Mini Low Thinking (400K context)
- `gemini-3-1-pro-low` - Gemini 3.1 Pro Low Thinking (1M context)

**Effort selection**: Effort is baked into model alias suffix (`-low`, `-medium`, `-high`, `-xhigh`, `-max`).

## Advantages

- **Automated dispatch**: No manual copy-paste required
- **Structured output**: Per-turn metadata available via ACP
- **Session management**: Programmatic session creation and control
- **Cross-platform**: Works on Windows, Linux, macOS
- **Fresh context**: Each dispatch gets isolated session

## Disadvantages

- **Devin CLI dependency**: Requires devin CLI installation
- **ACP complexity**: Need to implement ACP client or use existing library
- **Process management**: Need to manage subprocess lifecycle
- **JSON-RPC framing**: Need to handle `Content-Length` framing

## When to Use

- **Production automation**: When automated dispatch is required
- **High-volume sessions**: When manual copy-paste is impractical
- **Structured metadata**: When per-turn token/cost tracking is needed
- **Cross-platform deployment**: When running on Linux servers via SSH

## When NOT to Use

- **Prototype phase**: When manual copy-paste is acceptable
- **Simple scripts**: When `-p` mode is sufficient
- **No Devin CLI**: When devin CLI is not available

## Comparison with windsurf-cascade

| Feature | devin-cli (ACP) | windsurf-cascade |
|---------|-----------------|------------------|
| **Automated dispatch** | ✅ Yes | ❌ Manual copy-paste |
| **Structured output** | ✅ Yes | ❌ No |
| **Session spawning** | ✅ Yes | ❌ No |
| **Fresh context** | ✅ Yes | ✅ Yes |
| **Cross-platform** | ✅ Yes | ✅ Yes |
| **Complexity** | Higher (ACP protocol) | Lower (manual) |
| **Dependencies** | Devin CLI | None (Windsurf UI) |

## Implementation Notes

### ACP Client Library

Options for ACP client implementation:
1. Use existing `agent-client-protocol` Rust crate (v0.10.3)
2. Implement ACP in Python/Node.js (JSON-RPC with Content-Length framing)
3. Use Zed's ACP client code as reference implementation

### Permissions

For non-interactive runs, use:
- `--permission-mode dangerous` for fully-automated runs
- Carefully scoped `permissions.allow` list for least-privilege runs

### Workspace Trust

Default is `--respect-workspace-trust=false` (trust-free launch) for orchestrator use.

## Example Dispatch

```python
# Pseudocode for ACP dispatch
import subprocess
import json

# Start devin acp server
process = subprocess.Popen(['devin', 'acp'], 
                           stdin=subprocess.PIPE, 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)

# Send session/new request
request = {
    "jsonrpc": "2.0",
    "method": "session/new",
    "params": {"workspace": workspace_path},
    "id": 1
}
process.stdin.write(json.dumps(request) + "\n")

# Send session/prompt request
request = {
    "jsonrpc": "2.0",
    "method": "session/prompt",
    "params": {"prompt": prompt_content},
    "id": 2
}
process.stdin.write(json.dumps(request) + "\n")

# Read session/update responses
while True:
    line = process.stdout.readline()
    if not line: break
    response = json.loads(line)
    if response.get('method') == 'session/update':
        # Process streaming updates
        pass
```

## References

- [Agent Client Protocol Spec](https://agentclientprotocol.com/)
- `orchestrator/references/devin-orchestrator-notes.md` - Detailed Devin CLI investigation
- `agent-client-protocol` crate v0.10.3 on crates.io

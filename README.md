# devin-orchestrator

A generic, harness-agnostic framework for AI-assisted software development, built on top of Windsurf Cascade and inspired by [obra/superpowers](https://github.com/obra/superpowers).

**See Also:**
- [INSTALL.md](INSTALL.md) - Installation instructions
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment model and workflow updates
- [ARCHITECTURE.md](ARCHITECTURE.md) - Core abstractions and design
- [skills/README.md](skills/README.md) - Skills library documentation
- [ORCHESTRATION-RUNBOOK.md](ORCHESTRATION-RUNBOOK.md) - Agent-facing orchestration protocol
- [MCP-CLIENTS.md](MCP-CLIENTS.md) - MCP client configuration

## Vision

Separate **process disciplines** (skills, workflows, contracts) from **harness mechanisms** (transport adapters), enabling the same methodology to work across Windsurf Cascade, Claude Code, Devin CLI, and future platforms.

## Architecture

### Core Abstractions

1. **Skills** - Process disciplines with Iron Laws and checklists
2. **Workflows** - Step sequences with gates, artifacts, and skill assignments
3. **Dispatch Contracts** - Role-specific input/output contracts with quality bars
4. **Transport Adapters** - Harness-specific mechanisms (Windsurf, Claude Code, Devin CLI, etc.)
5. **MCP Server** - stdio JSON-RPC server exposing skills, workflows, and dispatch to any MCP-compatible client

### Layer Stack

```
MCP-Compatible Client (Claude, Cursor, Cascade, etc.)
       ↓
MCP Server Layer (stdio JSON-RPC)
       ↓
Workflow Orchestration Layer
       ↓
Skills Invocation Layer
       ↓
Dispatch Contract Layer
       ↓
Transport Adapter Layer
       ↓
Platform Layer (Windsurf, Claude Code, Devin CLI, etc.)
```

## Model Selection

- **Architect**: Cascade (SWE-1.6)
- **Sub-agents** (Coder, Test-Author, Reviewer): SWE-1.6 (default)
- **Rationale**: SWE-1.6 is free and allows parallelization up to 10 instances; target 8 parallel dispatches to leave headroom for Architect

## Status

Early prototype phase. Design documented in `ARCHITECTURE.md`.

## MCP Server

`mcp_server.py` runs a stateless stdio MCP server that exposes skills, workflows, and Devin dispatch as JSON-RPC tools. Any MCP-compatible client (Claude Desktop, Cursor, OpenClaw, etc.) can connect and run the orchestrator without learning bash paths or local file layouts.

Primary MCP tools include:

- `execute`, `implement`, `review`, `investigate`, `plan`, `run_workflow`, `run_skill` - high-level intent routing and workflow execution
- `dispatch_skill`, `dispatch_devin` - low-level Devin worker dispatch
- `list_skills`, `get_skill`, `list_workflows`, `get_workflow`, `read_artifact` - discovery and read-only helpers
- `gate_decision`, `continue_workflow` - gate control and resume

See [MCP-CLIENTS.md](MCP-CLIENTS.md) for client configuration examples.

## Directory Structure

```
devin-orchestrator/
├── mcp_server.py    # MCP server entry point (stdio JSON-RPC)
├── MCP-CLIENTS.md   # MCP client configuration
├── skills/          # Skill definitions (YAML + markdown)
├── workflows/       # Workflow definitions (YAML manifests + markdown)
├── workflow-engine/ # Orchestration engine and tools
├── adapters/        # Transport adapter implementations
├── contracts/       # Dispatch contract definitions
└── .windsurf/
    └── workflows/   # Windsurf slash command stubs
```

## Attribution

Portions adapted from [obra/superpowers](https://github.com/obra/superpowers), Copyright © 2025 Jesse Vincent, MIT License.

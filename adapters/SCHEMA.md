# Transport Adapter Schema (v1)

## Overview

This document defines the YAML schema for transport adapters. A transport adapter moves inputs to a sub-agent and returns outputs, implementing the dispatch contract.

## File Structure

Each adapter has two files:
- `<adapter-name>.yaml` - Structured definition (machine-readable)
- `<adapter-name>.md` - Narrative documentation (human-readable)

Both files must agree on the adapter definition. The YAML is the structured source of truth; the markdown provides narrative context, examples, and usage instructions.

## YAML Schema

```yaml
schema_version: 1
name: windsurf-cascade
platform: windsurf
description: Windsurf Cascade transport adapter via fresh session copy-paste
capabilities:
  - fresh_session_spawn
  - context_isolation
  - file_operations
  - terminal_commands
dispatch_contract:
  inputs:
    - prompt_file
    - workspace_path
    - model_config
  outputs:
    - stdout_file
    - stderr_file
    - session_metadata
  quality_bar:
    - exit_code_zero
    - no_timeout
    - artifact_exists
limitations:
  - max_prompt_tokens: 200000
  - max_session_duration: 3600
  - requires_user_copy_paste: true
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `schema_version` | int | yes | Schema version (currently 1) |
| `name` | string | yes | Adapter identifier (kebab-case) |
| `platform` | string | yes | Platform name (windsurf, claude-code, devin) |
| `description` | string | yes | One-sentence summary |
| `capabilities` | list[string] | yes | Supported capabilities |
| `dispatch_contract` | object | yes | Dispatch contract definition |
| `limitations` | list[string] | no | Known limitations |

### dispatch_contract

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `inputs` | list[string] | yes | Required input fields |
| `outputs` | list[string] | yes | Expected output fields |
| `quality_bar` | list[string] | yes | Quality criteria |

## Capability Values

- `fresh_session_spawn` - Can spawn fresh agent sessions
- `context_isolation` - Provides isolated context per session
- `file_operations` - Can read/write files
- `terminal_commands` - Can execute terminal commands
- `native_subagent_dispatch` - Has native sub-agent dispatch mechanism

## Platform Values

- `windsurf` - Windsurf Cascade
- `claude-code` - Claude Code CLI
- `devin` - Devin CLI
- `generic` - Generic/unknown platform

## Conventions

- **YAML is structured source**: When YAML and markdown disagree, YAML wins
- **Markdown is narrative source**: Usage instructions, examples, troubleshooting live here
- **Adapter names**: Use kebab-case (e.g., windsurf-cascade)
- **Capability enumeration**: Use predefined capability values

## Versioning

- Increment `schema_version` when breaking changes are introduced
- Document migration steps in this file when bumping version

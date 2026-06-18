# Windsurf Harness

A generic, harness-agnostic framework for AI-assisted software development, built on top of Windsurf Cascade and inspired by [obra/superpowers](https://github.com/obra/superpowers).

## Vision

Separate **process disciplines** (skills, workflows, contracts) from **harness mechanisms** (transport adapters), enabling the same methodology to work across Windsurf Cascade, Claude Code, Devin CLI, and future platforms.

## Architecture

### Core Abstractions

1. **Skills** - Process disciplines with Iron Laws and checklists
2. **Workflows** - Step sequences with gates, artifacts, and skill assignments
3. **Dispatch Contracts** - Role-specific input/output contracts with quality bars
4. **Transport Adapters** - Harness-specific mechanisms (Windsurf, Claude Code, etc.)

### Layer Stack

```
User Interface Layer
       ↓
Workflow Orchestration Layer
       ↓
Skills Invocation Layer
       ↓
Dispatch Contract Layer
       ↓
Transport Adapter Layer
       ↓
Platform Layer (Windsurf, Claude Code, etc.)
```

## Model Selection

- **Architect**: Cascade (SWE-1.6)
- **Sub-agents** (Coder, Test-Author, Reviewer): SWE-1.6 (default)
- **Rationale**: SWE-1.6 is free and allows parallelization up to 10 instances; target 8 parallel dispatches to leave headroom for Architect

## Status

Early prototype phase. Design documented in `ARCHITECTURE.md`.

## Directory Structure

```
devin-orchestrator/
├── skills/          # Skill definitions (YAML + markdown)
├── workflows/       # Workflow definitions (YAML manifests + markdown)
├── adapters/        # Transport adapter implementations
├── contracts/       # Dispatch contract definitions
├── templates/       # Prompt templates for dispatches
└── .windsurf/
    └── workflows/   # Windsurf slash command stubs
```

## Attribution

Portions adapted from [obra/superpowers](https://github.com/obra/superpowers), Copyright © 2025 Jesse Vincent, MIT License.

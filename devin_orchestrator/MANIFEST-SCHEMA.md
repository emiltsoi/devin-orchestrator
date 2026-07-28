# Workflow Manifest Schema (v1)

## Overview

This document defines the YAML schema for workflow manifests. Workflows are stage sequences with gates, artifacts, and skill assignments.

## Implementation

The schema is implemented by:
- `manifest_loader.py` - Loads and validates workflow manifests from YAML files
- `deterministic_tools.py` - Provides `load_manifest()` function for parsing manifests
- `orchestrate.py` - Uses manifests to orchestrate workflow execution

See `manifest_loader.py` for validation logic and field reference implementation.

## File Structure

Each workflow has a single file:
- `<workflow-name>.manifest.yaml` - Structured definition (machine-readable)

The YAML is the source of truth for workflow definition.

## YAML Schema

```yaml
name: superpower
description: "Superpowers workflow - complete software development methodology for coding agents"
version: 1.0.0
schema_version: 1
session_shape: superpower

# Optional: Skip brainstorming if spec is already clear
skip_brainstorming: false

stages:
  - step: 0
    name: brainstorming
    skill: brainstorming
    description: "Refines rough ideas through questions, explores alternatives, presents design in sections for validation"
    required_artifacts: []
    output_artifacts: [design.md]
    gate: none
    optional: true

  - step: 1
    name: using-git-worktrees
    skill: using-git-worktrees
    description: "Creates isolated workspace on new branch, runs project setup, verifies clean test baseline"
    required_artifacts: [design.md]
    output_artifacts: [worktree-info.md, baseline-test-results.md]
    gate: g1_design_approval

  - step: 2
    name: writing-plans
    skill: writing-plans
    description: "Breaks work into bite-sized tasks (2-5 minutes each) with exact file paths, complete code, verification steps"
    required_artifacts: [design.md]
    output_artifacts: [plan.md]
    gate: none

gates:
  - id: g1_design_approval
    name: Design Approval
    description: "Human approval of design document before creating worktree"
    type: human
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `name` | string | yes | Workflow name (kebab-case) |
| `description` | string | yes | One-sentence summary |
| `version` | string | yes | Semantic version (MAJOR.MINOR.PATCH) |
| `schema_version` | int | yes | Schema version (currently 1) |
| `session_shape` | string | yes | Workflow identifier (kebab-case) |
| `skip_brainstorming` | bool | no | Skip brainstorming stage if spec is clear (default: false) |
| `stages` | list[object] | yes | Stage definitions |
| `gates` | list[object] | no | Gate definitions |

### stages

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `step` | int | yes | Step number (0-indexed) |
| `name` | string | yes | Stage name (kebab-case) |
| `skill` | string | yes | Skill to dispatch (matches skill YAML) |
| `description` | string | yes | Stage description |
| `required_artifacts` | list[string] | no | Artifacts required before this stage |
| `output_artifacts` | list[string] | yes | Artifacts produced by this stage |
| `gate` | string | no | Gate ID after this stage (or "none") |
| `optional` | bool | no | Whether this stage can be skipped |

### gates

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `id` | string | yes | Gate identifier (kebab-case) |
| `name` | string | yes | Human-readable gate name |
| `description` | string | yes | What is being checked |
| `type` | enum | yes | `human` or `auto` |

## Conventions

- **YAML is source of truth**: Single source of truth for workflow definition
- **Stage identifiers**: Use `step` field (0-indexed integers)
- **Gate IDs**: Use `g<step>_<short>` format (e.g., g1_design_approval)
- **Skill names**: Must match corresponding skill YAML file names
- **Artifact names**: Use kebab-case with .md extension for markdown files
- **Field names**: Schema field names must match exactly with implementation in `manifest_loader.py`

## Versioning

- Increment `schema_version` when breaking changes are introduced
- Increment `version` for workflow-specific changes
- Document migration steps in this file when bumping schema version

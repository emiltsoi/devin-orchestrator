# Workflow Manifest Schema (v1)

## Overview

This document defines the YAML schema for workflow manifests. Workflows are step sequences with gates, artifacts, and skill assignments.

## File Structure

Each workflow has two files:
- `<workflow-name>.manifest.yaml` - Structured definition (machine-readable)
- `<workflow-name>.md` - Narrative documentation (human-readable)

Both files must agree on the workflow definition. The YAML is the structured source of truth; the markdown provides narrative context, examples, and step-by-step prose.

## YAML Schema

```yaml
schema_version: 1
session_shape: gated-change
description: Gated development workflow with design, implementation, and review
slash_command: /gated-change
canonical_workflow: workflows/gated-change.md
session_id_format: CHANGE-NNN
session_init:
  command: Invoke-SessionInit.ps1
  creates_workdir: work/<session_id>/
  initial_artefacts:
    - request.md
    - status.md
    - session-audit.md
auto_load:
  - path: skills/README.md
    always: true
    purpose: "Skill index"
required_artefacts:
  step_0: [request.md, status.md, session-audit.md]
  step_1: [requirement.md]
  step_2: [baseline.md]
  step_3: [design.md]
  step_4: [implementation/]
  step_5: [verification.md]
  step_6: [review/]
  step_7: [summary.md, retro.md]
gates:
  - id: g1_requirement_approval
    after_step: 1
    type: user_gate
    description: "User approves requirement.md"
    required_response: explicit_approval
  - id: g3_design_approval
    after_step: 3
    type: user_gate
    description: "User approves design.md"
    required_response: explicit_approval
skills:
  - name: brainstorming
    phases: [step_1]
    announcement: "Using the brainstorming skill to refine <topic>"
  - name: writing-plans
    phases: [step_3]
    announcement: "Using the writing-plans skill to produce design.md"
  - name: subagent-driven-development
    phases: [step_4]
    announcement: "Using the subagent-driven-development skill"
  - name: test-driven-development
    phases: [step_2, step_4]
    announcement: "Using the test-driven-development skill"
  - name: code-review
    phases: [step_6]
    announcement: "Using the code-review skill"
  - name: verification-before-completion
    phases: [step_5]
    announcement: "Using the verification-before-completion skill"
branch:
  default: "change/<session_id>"
  policy: implementation_branch_committable
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `schema_version` | int | yes | Schema version (currently 1) |
| `session_shape` | string | yes | Workflow identifier (kebab-case) |
| `description` | string | yes | One-sentence summary |
| `slash_command` | string | yes | Slash command for Windsurf |
| `canonical_workflow` | string | yes | Path to markdown workflow file |
| `session_id_format` | string | yes | Session ID pattern (e.g., CHANGE-NNN) |
| `session_init` | object | yes | Session initialization settings |
| `auto_load` | list[object] | yes | Files to auto-load at session start |
| `required_artefacts` | object | yes | Required artifacts per step |
| `gates` | list[object] | yes | Gate definitions |
| `skills` | list[object] | yes | Skill assignments per phase |
| `branch` | object | yes | Git branch policy |

### session_init

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `command` | string | yes | Initialization command |
| `creates_workdir` | string | yes | Work directory path template |
| `initial_artefacts` | list[string] | yes | Initial artifact files |

### auto_load

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `path` | string | yes | File path (may contain glob) |
| `always` | bool | yes | Always load or filter-based |
| `purpose` | string | yes | Why this file is loaded |

### required_artefacts

Map keyed by step identifier (`step_0`..`step_N`). Each step lists files that MUST exist in the work-dir at session-close.

### gates

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `id` | string | yes | Gate identifier |
| `after_step` / `before_step` | int / string | one of (yes) | When gate fires |
| `sub_step` | string | no | Letter suffix for mid-step gates |
| `type` | enum | yes | `user_gate`, `mid_step_check`, `artefact_check` |
| `description` | string | yes | What is being checked |
| `required_response` | enum | when `type=user_gate` | `explicit_approval` or `objection_window` |
| `artefact` | string | when `type=artefact_check` | Filename being checked |

### skills

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `name` | string | yes | Skill name (matches skill YAML) |
| `phases` | list[string] | yes | Which steps this skill applies to |
| `announcement` | string | yes | Announcement template |

### branch

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `default` | string | yes | Default branch pattern |
| `policy` | enum | yes | `implementation_branch_committable` or `investigation_branch_discardable` |

## Conventions

- **YAML is structured source**: When YAML and markdown disagree, YAML wins
- **Markdown is narrative source**: Step-by-step prose, examples, retry policy live here
- **Step identifiers**: Use `step_N` format (step_0, step_1, etc.)
- **Gate IDs**: Use `g<step><suffix>_<short>` format (e.g., g1_requirement_approval)
- **Skill names**: Must match corresponding skill YAML file names

## Versioning

- Increment `schema_version` when breaking changes are introduced
- Document migration steps in this file when bumping version

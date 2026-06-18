# Dispatch Contract Schema (v1)

## Overview

This document defines the YAML schema for dispatch contracts. A dispatch contract specifies inputs, outputs, quality bar, and failure response for a specialist role (Coder, Test-Author, Reviewer).

## File Structure

Each contract has two files:
- `<role>-dispatch.yaml` - Structured definition (machine-readable)
- `<role>-dispatch.md` - Narrative documentation (human-readable)

Both files must agree on the contract definition. The YAML is the structured source of truth; the markdown provides narrative context, examples, and usage instructions.

## YAML Schema

```yaml
schema_version: 1
role: coder
description: Implementation agent for coding tasks per design specification
model: swe-1.6
inputs:
  - name: design.md
    type: file
    required: true
    description: Full design document
  - name: FRAMEWORK_*.md
    type: file
    required: true
    description: Framework files including anti-patterns
  - name: target_files
    type: file_content
    required: true
    description: Current content of target files (paste-in)
  - name: acceptance_criteria
    type: list
    required: true
    description: AC-1..AC-N from design
  - name: cited_idioms
    type: list
    required: true
    description: Idioms from FRAMEWORK to use
outputs:
  - name: code_diff
    type: file
    required: true
    description: Code diff or full file content
  - name: rationale
    type: text
    required: true
    description: Rationale citing which idiom was used
  - name: assumptions
    type: list
    required: false
    description: Flagged assumptions not in design
  - name: test_expectations
    type: list
    required: true
    description: One sentence per AC for Test-Author
quality_bar:
  - compiles_mechanically
  - cites_at_least_one_idiom
  - no_novel_mechanisms
  - acs_addressed_1_to_1
  - no_test_weakening
failure_modes:
  invents_novel_mechanism:
    response: reject_with_anti_pattern_reference
  fails_to_cite_idiom:
    response: reject_ask_for_citation
  contradicts_design:
    response: update_design_or_redispatch
  ac_miss:
    response: reject_redispatch
  silent_scope_creep:
    response: reject_with_allowlist
retry_budget: 1
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `schema_version` | int | yes | Schema version (currently 1) |
| `role` | string | yes | Role identifier (coder, test-author, reviewer) |
| `description` | string | yes | One-sentence summary |
| `model` | string | yes | Default model for this role |
| `inputs` | list[object] | yes | Required input specifications |
| `outputs` | list[object] | yes | Expected output specifications |
| `quality_bar` | list[string] | yes | Quality criteria |
| `failure_modes` | object | yes | Failure mode responses |
| `retry_budget` | int | yes | Maximum retry attempts |

### inputs / outputs

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `name` | string | yes | Input/output identifier |
| `type` | enum | yes | `file`, `file_content`, `text`, `list` |
| `required` | bool | yes | Whether this is required |
| `description` | string | yes | Human-readable description |

### failure_modes

Map of failure mode identifier to response strategy.

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `<failure_mode>` | string | yes | Response strategy |

## Role Values

- `coder` - Implementation agent
- `test-author` - Test authoring agent
- `reviewer` - Code review agent (two-stage: spec, quality)

## Model Values

- `swe-1.6` - Default for all roles (free, parallelizable)
- Can be overridden per dispatch if specific capabilities needed

## Type Values

- `file` - File path reference
- `file_content` - File content pasted inline
- `text` - Free-form text
- `list` - List of items

## Conventions

- **YAML is structured source**: When YAML and markdown disagree, YAML wins
- **Markdown is narrative source**: Examples, usage instructions, troubleshooting live here
- **Role names**: Use kebab-case (coder, test-author, reviewer)
- **Failure mode keys**: Use snake_case (invents_novel_mechanism)

## Versioning

- Increment `schema_version` when breaking changes are introduced
- Document migration steps in this file when bumping version

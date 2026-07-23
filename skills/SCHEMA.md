# Skill Schema (v1)

## Overview

This document defines the YAML schema for skill definitions. Skills are process disciplines with Iron Laws, checklists, and explicit invocation protocols.

## File Structure

Each skill has two files:
- `<skill-name>.yaml` - Structured definition (machine-readable)
- `<skill-name>.md` - Narrative documentation (human-readable)

Both files must agree on the skill definition. The YAML is the structured source of truth; the markdown provides narrative context, examples, and rationale.

## YAML Schema

```yaml
schema_version: 1
name: brainstorming
description: Use before any non-trivial creative work
iron_law: "NO IMPLEMENTATION UNTIL DESIGN APPROVED"
triggers:
  - new_feature
  - behavior_change
  - refactor
checklist:
  - id: explore_context
    description: Explore project context
  - id: ask_questions_one_at_a_time
    description: Ask clarifying questions one at a time
  - id: propose_2_3_approaches
    description: Propose 2-3 approaches with trade-offs
  - id: present_design_sections
    description: Present design in sections
  - id: write_spec
    description: Write requirement.md / spec
  - id: spec_self_review
    description: Self-review spec for placeholders, contradictions, ambiguity
  - id: user_approval_gate
    description: Get user approval on written spec
  - id: invoke_next_skill
    description: Invoke writing-plans skill
terminal_state: writing-plans
announcement: "Using the brainstorming skill to refine <topic> before writing requirement.md."
red_flags:
  - Writing requirement.md before design approval
  - Jumping to writing-plans without approval gate
  - Asking batch questions instead of one at a time
  - Presenting only one approach
```

## Field Definitions

| Field | Type | Required | Description |
|-------|------|---------:|-------------|
| `schema_version` | int | yes | Schema version (currently 1) |
| `name` | string | yes | Skill identifier (kebab-case, letters/numbers/hyphens only, no special characters) |
| `description` | string | yes | One-sentence summary. Start with "Use when...". Describe triggering conditions, symptoms, or context. Do NOT summarize the skill's workflow or process. Keep under 500 characters when possible. |
| `iron_law` | string | yes | Non-negotiable rule in a code block |
| `triggers` | list[string] | yes | When this skill should be invoked |
| `checklist` | list[object] | yes | Ordered checklist items |
| `checklist[].id` | string | yes | Unique identifier for checklist item |
| `checklist[].description` | string | yes | Human-readable description |
| `terminal_state` | string | yes | Next skill to invoke (or "complete") |
| `announcement` | string | yes | Announcement template with `<topic>` placeholder |
| `red_flags` | list[string] | no | Anti-patterns to avoid |

## Markdown Content

The markdown file should contain:
- Overview and purpose
- When to use / when to skip
- Detailed process flow
- Key principles
- Red flags (expanded from YAML)
- Relation to workflows and other skills
- Attribution (if adapted from superpowers)

## Conventions

- **YAML is structured source**: When YAML and markdown disagree, YAML wins
- **Markdown is narrative source**: Examples, rationale, and expanded context live here
- **Checklist execution**: Walk checklist literally via todo_list
- **Announcement protocol**: Always announce skill before acting (Rule 38)
- **Terminal state**: Only invoke the specified next skill; don't jump to other skills

## Skill Discovery Optimization (SDO)

A skill that cannot be found will not be invoked. The discovery surface for a skill is
its `name` and `description` — those are what an agent scans when deciding which skill
applies to the current request. Optimize them as follows:

- **`name`**: kebab-case, letters/numbers/hyphens only, no special characters. Choose a
  name that names the activity, not the artifact (e.g. `writing-skills`, not
  `skill-docs`).
- **`description`**: must start with "Use when..." and describe the triggering
  conditions, symptoms, or context that should make an agent think of this skill. Do
  NOT summarize the skill's workflow or process — the checklist does that. Keep the
  description under 500 characters when possible; long descriptions get truncated and
  skimmed.

A good description answers "when should I reach for this skill?" A bad description
answers "what does this skill do?" The former aids discovery; the latter buries it.

See `skills/writing-skills/writing-skills.md` for the full authoring discipline,
including how to test that a description is discoverable.

## Versioning

- Increment `schema_version` when breaking changes are introduced
- Document migration steps in this file when bumping version

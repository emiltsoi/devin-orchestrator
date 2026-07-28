---
name: writing-skills
description: "Use when creating or editing a skill to ensure it is tested and discoverable."
---

# Writing Skills

**TL;DR:** Use when creating or editing a skill to ensure it is tested and discoverable.

## Overview

Writing skills is test-driven development applied to process documentation. A skill is
not a document you write — it is a discipline you *prove* an agent will follow. The proof
comes from a pressure scenario that fails without the skill and passes with it.

## When to Create a Skill

Create a skill when the technique is:

- A **reusable process** (a way of working that applies across projects).
- A **pattern** that agents reliably get wrong without explicit guidance.
- A **tool usage discipline** where the wrong invocation has real costs.

Do **not** create a skill for:

- One-off solutions to a single project's problem.
- Project-specific conventions (those belong in `AGENTS.md` or a rules file).
- Things enforceable by a regex or linter (use the linter instead).
- Generic best practices an agent already follows reliably.

## TDD Mapping for Skills

| TDD concept | Skill creation |
|-------------|----------------|
| Test case | Pressure scenario run with a subagent |
| Production code | The skill document (`.md` + `.yaml`) |
| RED | Agent violates the rule without the skill |
| GREEN | Agent complies with the skill |
| REFACTOR | Close loopholes while maintaining compliance |

## Skill Types and Test Approaches

- **Discipline-enforcing skills** (e.g. `test-driven-development`): the pressure scenario
  tempts the agent to skip the discipline; RED shows the skip, GREEN shows compliance.
- **Technique skills** (e.g. `using-git-worktrees`): the scenario requires the technique;
  RED shows a worse alternative, GREEN shows the technique applied.
- **Pattern skills** (e.g. `subagent-driven-development`): the scenario is a multi-step
  task; RED shows a muddled approach, GREEN shows the pattern.
- **Reference skills**: rarely need a pressure scenario; instead, verify the agent can
  find and apply the reference correctly.

## Skill Discovery Optimization (SDO)

A skill that cannot be found is useless. The `description` field is the discovery
surface. Optimize it as follows:

- **Start with "Use when..."** — this signals to the agent that the description is a
  trigger, not a summary.
- **Describe triggering conditions, symptoms, or context** — what about the current
  request should make the agent think of this skill?
- **Do NOT summarize the skill's workflow or process** — the checklist does that.
  Summaries bury the trigger.
- **Stay under 500 characters** — long descriptions get truncated and skimmed.
- **Name is kebab-case** — letters, numbers, and hyphens only, no special characters.

See `skills/SCHEMA.md` for the full SDO guidance.

## RED-GREEN-REFACTOR for Skills

1. **RED** — Run a pressure scenario with a subagent *without* the skill. Document every
   violation of the intended discipline. If the agent already complies, you do not need a
   skill.
2. **GREEN** — Write the minimal skill document that addresses the observed violations.
   Re-run the scenario and confirm the agent now complies.
3. **REFACTOR** — Look for new rationalizations the agent might use to bypass the skill.
   Tighten the wording, add red flags, and re-run the scenario. Keep compliance while
   closing loopholes.

## Directory and File Structure

Each skill lives in its own directory with two files:

- `skills/<name>/<name>.md` — narrative documentation with YAML frontmatter.
- `skills/<name>/<name>.yaml` — structured schema (source of truth).

Both files must agree on `name` and `description`. When they disagree, YAML wins per
`skills/SCHEMA.md`.

## Iron Law

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

## Skill Creation Checklist

You MUST create a `todo_list` entry for each item and complete them in order:

1. **run_baseline** — Run a pressure scenario without the skill and document violations.
2. **write_minimal_skill** — Write a minimal skill addressing the observed violations.
3. **verify_compliance** — Re-run the scenario with the skill and confirm compliance.
4. **close_loopholes** — Find new rationalizations and plug them.
5. **optimize_discovery** — Tune the description for Skill Discovery Optimization (SDO).
6. **create_yaml_and_md** — Produce both `<skill>.yaml` and `<skill>.md` per
   `skills/SCHEMA.md`.

---

Adapted from obra/superpowers (MIT license).

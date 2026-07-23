# Skills Library

This directory contains the skills library for devin-orchestrator. Skills are process disciplines that define how specific activities should be performed.

**See Also:**
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Core abstractions and skill layer
- [workflows/](../workflows/) - Workflow definitions that reference skills
- [workflow-engine/](../workflow-engine/) - Engine that loads and executes skills
- [skills/SCHEMA.md](SCHEMA.md) - Skill schema definition

## Skill Structure

Each skill is defined in a subdirectory with two files:
- `<skill>/<skill>.md` - Narrative documentation with process flow, iron law, and guidelines
- `<skill>/<skill>.yaml` - Structured schema with triggers, checklist, and metadata

## Available Skills

### Core Development Skills

- **brainstorming** - Refines rough ideas through questions, explores alternatives, presents design in sections for validation
- **writing-plans** - Breaks work into bite-sized tasks (2-5 minutes each) with exact file paths, complete code, verification steps
- **subagent-driven-development** - Dispatches fresh subagent per task with two-stage review (spec compliance, then code quality)
- **executing-plans** - Executes a pre-written plan task-by-task in the same context with human checkpoints

### Quality & Testing Skills

- **test-driven-development** - Enforces RED-GREEN-REFACTOR: write failing test, watch it fail, write minimal code, watch it pass, commit
- **verification-before-completion** - Verifies build and tests before claiming completion with fresh evidence
- **swe-compliance** - Reviews code for software engineering best practices, coding standards, and compliance

### Git & Workflow Skills

- **using-git-worktrees** - Creates isolated workspace on new branch, runs project setup, verifies clean test baseline
- **finishing-a-development-branch** - Verifies tests, presents options (merge/PR/keep/discard), cleans up worktree

### Review Skills

- **requesting-code-review** - Reviews against plan, reports issues by severity. Critical issues block progress
- **code-review** - Reviews code for spec compliance and code quality with objective, evidence-based findings before merging
- **adversarial-review** - Multi-perspective adversarial review using parallel Devin dispatch with different persona prompts
- **receiving-code-review** - Evaluates and addresses code review feedback: read, verify against codebase, push back or acknowledge, then implement one item at a time

### Skill Authoring

- **writing-skills** - Test-driven authoring of new skills: write a failing pressure scenario first, then a minimal skill that makes it pass, then close rationalization loopholes

### Investigation Skills

- **systematic-debugging** - Systematically investigates incidents, bugs, or failures through evidence gathering, analysis, root cause identification, and fix proposal

### Orchestration Skills

- **orchestrate-superpower** - Deprecated wrapper; use `mcp0_run_workflow('superpower')` directly for end-to-end automation
- **using-devin-orchestrator** - Meta-skill invoked at the start of any orchestrated task to decide whether a devin-orchestrator skill should be invoked before acting

## Skill Schema

Each skill YAML file follows this schema:

```yaml
schema_version: 1
name: <skill-name>
description: <brief description>
iron_law: "<non-negotiable rule>"
triggers:
  - <trigger-condition>
checklist:
  - id: <checklist-item-id>
    description: <checklist-item-description>
terminal_state: <next-skill-or-state>
announcement: "<announcement text>"
red_flags:
  - <red-flag-condition>
```

## Skill Usage

Skills are invoked by the workflow engine based on the workflow manifest. Each stage in a workflow specifies which skill to use.

Example from a workflow manifest:
```yaml
stages:
  - step: 0
    name: brainstorming
    skill: brainstorming
    description: "Refines rough ideas through questions"
    required_artifacts: []
    output_artifacts: [design.md]
    gate: none
```

## Skill Development

When creating a new skill:

1. Create a subdirectory: `skills/<skill-name>/`
2. Create the narrative documentation: `<skill-name>/<skill-name>.md`
3. Create the structured schema: `<skill-name>/<skill-name>.yaml`
4. Follow the skill schema defined in `SCHEMA.md`
5. Include iron law, triggers, checklist, terminal state, announcement, and red flags
6. Reference the skill in workflow manifests as needed

### Skill Discovery Optimization (SDO)

A skill that cannot be found will not be invoked. Optimize the `name` and `description`
fields for discovery: `name` is kebab-case with letters, numbers, and hyphens only;
`description` starts with "Use when..." and describes triggering conditions, symptoms,
or context — it does **not** summarize the skill's workflow and stays under 500
characters. See `SCHEMA.md` and `writing-skills/writing-skills.md` for the full SDO
guidance and the test-first authoring discipline.

## Skill Loading

The workflow engine loads skills from the global installation at `~/.devin-orchestrator/skills/`. Skills can be overridden per-workspace by placing them in `.devin/skills/` (optional).

## Cross-References

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Core abstractions and skill layer
- [workflows/](../workflows/) - Workflow definitions that reference skills
- [workflow-engine/](../workflow-engine/) - Engine that loads and executes skills

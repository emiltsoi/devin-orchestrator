---
title: Generic Windsurf-Based Harness Architecture
created: 2026-06-19
status: design-draft
author: Cascade
related:
  - https://github.com/obra/superpowers
  - workflows/superpower.manifest.yaml
  - workflows/superpower.runbook.md
  - workflows/use-cases.yaml
  - skills/README.md
  - DEPLOYMENT.md
---

# Generic Windsurf-Based Harness Architecture

## Executive Summary

This design implements the [obra/superpowers](https://github.com/obra/superpowers) methodology as the canonical workflow for AI-assisted software development. The architecture separates **skills** (process disciplines) from **harness mechanisms** (transport adapters), enabling the same methodology to work across Windsurf Cascade, Claude Code, Devin CLI, and future platforms.

**Use Case Taxonomy**: The orchestrator supports multiple use cases organized by type:
- **Investigation**: RCA (Root Cause Analysis) - read-only, no git write operations
- **Review**: PR Review, Code Review - read-only, no git write operations
- **Development**: Gated Change (Superpower) - full git operations, implementation

See `workflows/use-cases.yaml` for the complete use case registry.

**Cross-Platform Design**: The harness is designed to be platform-agnostic. Skills, workflows, and contracts are YAML/markdown-based and work on any platform. Platform-specific concerns (PowerShell vs Bash, file paths, etc.) are isolated in transport adapters and execution scripts.

**Deployment Model**: Hybrid deployment. Skills, workflows, and workflow engine are installed to a global location (`~/.devin-orchestrator/`) and referenced from any workspace. Per-workspace overrides are optional via `.devin/workflows/` for workflow customization. Canonical source is global; local overrides provide flexibility for workspace-specific needs.

**Installation**: Run `python install.py` to install devin-orchestrator to global location. Configuration is managed via `~/.devin-orchestrator/config.yaml` and environment variables.

## Core Abstractions

### 1. Skills (Process Layer)

**Definition**: A skill is a rigid checklist for a specific activity, with an "Iron Law" (non-negotiable rule) and explicit invocation protocol.

**Contract**:
```yaml
skill:
  name: brainstorming
  iron_law: "NO IMPLEMENTATION UNTIL DESIGN APPROVED"
  triggers: [new_feature, behavior_change, refactor]
  checklist:
    - explore_context
    - ask_questions_one_at_a_time
    - propose_2_3_approaches
    - present_design_sections
    - write_spec
    - spec_self_review
    - user_approval_gate
    - invoke_next_skill
  terminal_state: writing-plans
```

**Key properties**:
- **Composable**: Skills chain together (brainstorming → writing-plans → subagent-driven-development)
- **Transport-agnostic**: Same skill works across different harnesses
- **Rule-citation**: Skills cite architect rules by number, not restate them
- **Announcement protocol**: "Using the <skill> skill to <action>" (Rule 38)

### 2. Workflows (Orchestration Layer)

**Definition**: A workflow is a sequence of steps with gates, artifacts, and skill assignments.

**Contract** (manifest.yaml):
```yaml
name: superpower
description: "Superpowers workflow - complete software development methodology for coding agents"
version: 1.0.0
schema_version: 1
session_shape: superpower

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

  - step: 3
    name: subagent-driven-development
    skill: subagent-driven-development
    description: "Dispatches fresh subagent per task with two-stage review (spec compliance, then code quality)"
    required_artifacts: [plan.md, design.md]
    output_artifacts: [implementation.md, task-results.md]
    gate: g2_plan_approval

  - step: 4
    name: test-driven-development
    skill: test-driven-development
    description: "Enforces RED-GREEN-REFACTOR: write failing test, watch it fail, write minimal code, watch it pass, commit"
    required_artifacts: [implementation.md]
    output_artifacts: [test-results.md, implementation-final.md]
    gate: none

  - step: 5
    name: requesting-code-review
    skill: requesting-code-review
    description: "Reviews against plan, reports issues by severity. Critical issues block progress"
    required_artifacts: [plan.md, implementation-final.md]
    output_artifacts: [review-findings.md]
    gate: g3_review_approval

  - step: 6
    name: finishing-a-development-branch
    skill: finishing-a-development-branch
    description: "Verifies tests, presents options (merge/PR/keep/discard), cleans up worktree"
    required_artifacts: [test-results.md, review-findings.md]
    output_artifacts: [completion-summary.md, merge-decision.md]
    gate: g4_completion_approval

gates:
  - id: g1_design_approval
    name: Design Approval
    description: "Human approval of design document before creating worktree"
    type: human

  - id: g2_plan_approval
    name: Plan Approval
    description: "Human approval of implementation plan before execution"
    type: human

  - id: g3_review_approval
    description: "Human approval of code review findings before completion"
    name: Review Approval
    type: human

  - id: g4_completion_approval
    name: Completion Approval
    description: "Human approval of merge/PR/keep/discard decision"
    type: human
```

**Key properties**:
- **Structured stages**: Each stage has step number, name, skill, description, artifacts, and gate
- **Artifact contracts**: required_artifacts (inputs) and output_artifacts per stage
- **Gate definitions**: Gates with id, name, description, and type (human, automated, none)
- **Skill references**: Each stage references a skill by name that must exist in skills/
- **Optional stages**: Stages can be marked optional to skip when not needed

### 3. Transport Adapters (Mechanism Layer)

**Definition**: A transport adapter moves inputs to a sub-agent and returns outputs, implementing the dispatch contract.

**Contract**:
```yaml
adapter:
  name: windsurf-cascade
  platform: windsurf
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
```

**Adapter types**:
- **Fresh-Cascade via user copy-paste** (available today)
- **Architect self-impersonation** (always available, lowest fidelity)
- **Claude Code CLI** (installed but requires API endpoint/key configuration)
- **Devin CLI** (blocked)
- **Direct sub-Cascade spawn** (future)

### 4. Dispatch Contracts (Agent Layer)

**Definition**: A dispatch contract specifies inputs, outputs, quality bar, and failure response for a specialist role.

**Example: Coder dispatch**:
```yaml
coder_dispatch:
  inputs:
    - design.md (full text)
    - FRAMEWORK_*.md (including anti-patterns)
    - target_files (current content, paste-in)
    - acceptance_criteria (AC-1..AC-N)
    - cited_idioms (from FRAMEWORK)
  outputs:
    - code_diff_or_full_files
    - rationale_citing_idiom
    - flagged_assumptions
    - test_expectations
  quality_bar:
    - compiles_mechanically
    - cites_at_least_one_idiom
    - no_novel_mechanisms
    - acs_addressed_1_to_1
    - no_test_weakening
  failure_modes:
    invents_novel_mechanism: reject_with_anti_pattern_reference
    fails_to_cite_idiom: reject_ask_for_citation
    contradicts_design: update_design_or_redispatch
    ac_miss: reject_redispatch
    silent_scope_creep: reject_with_allowlist
  retry_budget: 1
```

**Roles**:
- **Architect**: Orchestrator (design, decompose, dispatch, integrate) - Cascade (SWE-1.6)
- **Coder**: Implementation per design + FRAMEWORK idioms - SWE-1.6 (default)
- **Test-Author**: Tests covering ACs with reality-check - SWE-1.6 (default)
- **Reviewer**: Two-stage (spec-compliance, code-quality) - SWE-1.6 (default)

**Model selection rationale**:
- SWE-1.6 is free and allows parallelization up to 10 instances
- Target 8 parallel dispatches to leave headroom for the Architect Cascade session
- All sub-agent roles default to SWE-1.6 for cost efficiency and parallelization capacity
- Model can be overridden per dispatch if specific capabilities are needed

## Harness Architecture

### Layer Stack

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                    │
│  (Slash commands, chat interface, workflow selection)       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Orchestrator–Worker Layer (NEW)                │
│  (Cascade orchestrates, Devin workers execute, tools audit) │
│  - ORCHESTRATION-RUNBOOK.md (agent-facing protocol)         │
│  - Cascade: reasoning executive, triage, decision           │
│  - Devin workers: stateless skill execution (neutral)        │
│  - Deterministic tools: floor_validator, audit_helpers      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Workflow Orchestration Layer              │
│  (Session management, step execution, gate enforcement)     │
│  [DEPRECATED: step_executor.py mechanical driver]           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Skills Invocation Layer                 │
│  (Skill selection, announcement, checklist execution)        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Dispatch Contract Layer                    │
│  (Role-specific input/output contracts, quality bars)       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Transport Adapter Layer                   │
│  (Harness-specific mechanisms: Windsurf, Claude Code, etc.)  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Platform Layer                          │
│  (Windsurf Cascade, Claude Code, Devin CLI, etc.)           │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Request
     │
     ▼
Workflow Selection (e.g., superpower)
     │
     ▼
Session Init (session_init)
     │
     ├─→ Create workdir: work/<session_id>/
     ├─→ Initialize artifacts: request.md, status.md, session-audit.md
     └─→ Emit ack: "Loaded: rules, skills, workflows"
     │
     ▼
Step 0: Brainstorming (optional)
     │
     ├─→ Skill: brainstorming
     ├─→ Context: user request
     ├─→ Output: design.md
     └─→ Gate: none
     │
     ▼
Step 1: Using Git Worktrees
     │
     ├─→ Skill: using-git-worktrees
     ├─→ Context: design.md
     ├─→ Output: worktree-info.md, baseline-test-results.md
     └─→ Gate: g1_design_approval
     │
     ▼
Step 2: Writing Plans
     │
     ├─→ Skill: writing-plans
     ├─→ Context: design.md
     ├─→ Output: plan.md
     └─→ Gate: none
     │
     ▼
Step 3: Subagent-Driven Development
     │
     ├─→ Skill: subagent-driven-development
     ├─→ Context: plan.md, design.md
     ├─→ Output: implementation.md, task-results.md
     └─→ Gate: g2_plan_approval
     │
     ▼
Step 4: Test-Driven Development
     │
     ├─→ Skill: test-driven-development
     ├─→ Context: implementation.md
     ├─→ Output: test-results.md, implementation-final.md
     └─→ Gate: none
     │
     ▼
Step 5: Requesting Code Review
     │
     ├─→ Skill: requesting-code-review
     ├─→ Context: plan.md, implementation-final.md
     ├─→ Output: review-findings.md
     └─→ Gate: g3_review_approval
     │
     ▼
Step 6: Finishing a Development Branch
     │
     ├─→ Skill: finishing-a-development-branch
     ├─→ Context: test-results.md, review-findings.md
     ├─→ Output: completion-summary.md, merge-decision.md
     └─→ Gate: g4_completion_approval
```

## Generic Harness Interface

### Required Harness Capabilities

For a harness to support this architecture, it must provide:

1. **Session management**: Create isolated work directories with structured artifacts
2. **Skill invocation**: Load and execute skill checklists with announcement protocol
3. **Dispatch mechanism**: Transport inputs to sub-agents and return outputs
4. **Gate enforcement**: Halt at user gates, mid-step checks, artifact checks
5. **Artifact validation**: Verify required artifacts exist at session close
6. **Knowledge integration**: Load KB files (MAP/CAT/FRAMEWORK) with scope filtering
7. **Rule enforcement**: Load architect-rules with version tracking
8. **Metrics capture**: Track time, tokens, retries per session

### Harness-Specific Adaptations

**Windsurf Cascade**:
- Use `.windsurf/workflows/*.md` for slash commands
- Use Cascade's file operations for artifact creation
- Use Cascade's todo_list for skill checklists
- Use Cascade's memory system for KB integration
- Transport adapter: fresh Cascade session via user copy-paste

**Claude Code**:
- Use Claude Code's `Skill` tool for skill invocation
- Use Claude Code's `Task` tool for sub-agent dispatch
- Use Claude Code's `TodoWrite` tool for checklists
- Transport adapter: native sub-agent spawn

**Devin CLI**:
- Use `devin -p` for single-turn prompts
- Use `devin acp` for structured metadata
- Transport adapter: ACP (Agent Client Protocol)

## Implementation Strategy

### Phase 1: Core Abstractions (Foundation)

1. **Skill schema**: Define YAML schema for skills (iron_law, checklist, terminal_state)
2. **Workflow manifest schema**: Already exists (MANIFEST-SCHEMA.md)
3. **Dispatch contract schema**: Define YAML schema for role-specific contracts
4. **Transport adapter interface**: Define generic interface for harness adapters

### Phase 2: Windsurf-Specific Implementation

1. **Skill loader**: Parse skill YAML, execute checklists via todo_list
2. **Workflow engine**: Execute steps per manifest, enforce gates
3. **Adapter implementation**: Implement Windsurf-Cascade transport adapter
4. **Slash command integration**: Wire workflows to `.windsurf/workflows/*.md`

### Phase 3: Cross-Harness Validation

1. **Claude Code adapter**: Implement Claude Code transport adapter
2. **Devin CLI adapter**: Implement Devin CLI transport adapter
3. **Harness tests**: Validate same skills/workflows work across harnesses
4. **Documentation**: Harness-specific setup guides

### Phase 4: Knowledge Integration

1. **KB loader**: Scope-aware loading of MAP/CAT/FRAMEWORK files
2. **KB-delta emitter**: Rule 61 implementation
3. **Rule enforcement**: Architect-rules loading with version tracking
4. **Lesson promotion**: Automated lesson → rule promotion

## Migration Path from Current Orchestrator

### Current State

- Skills exist as markdown files with manual checklist execution
- Workflows exist as markdown + YAML manifests
- Multi-agent orchestration exists as contract definitions
- Transport adapters are partially defined (fresh-Cascade, self-impersonation)

### Migration Steps

1. **Formalize skill schemas**: Convert skill markdown to YAML + markdown dual-source
2. **Implement skill engine**: Parse skill YAML, execute via todo_list
3. **Implement workflow engine**: Execute steps per manifest, enforce gates
4. **Implement transport adapters**: Formalize adapter interface
5. **Add harness-agnostic tests**: Validate skills/workflows independent of harness
6. **Document harness setup**: Per-harness installation guides

## Benefits

1. **Harness portability**: Same methodology works across Windsurf, Claude Code, Devin CLI
2. **Skill reusability**: Skills written once, used across harnesses
3. **Workflow composability**: Workflows assemble skills in different sequences
4. **Contract clarity**: Dispatch contracts specify exact input/output expectations
5. **Mechanism swap**: Change transport adapter without changing skills/workflows
6. **Testing**: Test skills/workflows independently of harness implementation

## Cross-Platform Strategy

The harness is designed to work across Windows, Linux, and macOS:

**Platform-Agnostic Layer**:
- Skills: YAML + markdown (no platform-specific code)
- Workflows: YAML manifests + markdown (no platform-specific code)
- Contracts: YAML definitions (no platform-specific code)
- Templates: Markdown prompt templates (no platform-specific code)

**Platform-Specific Layer**:
- Transport adapters: Platform-specific dispatch mechanisms
- Execution scripts: PowerShell (Windows) / Bash (Linux/macOS)
- File paths: OS-specific path handling in adapters
- Session init: Platform-specific initialization scripts

**Migration Path**:
- Skills/workflows/contracts: No changes needed (already platform-agnostic)
- Add Bash equivalents for PowerShell scripts in `actions/` directory
- Transport adapters detect platform and use appropriate mechanism
- File path normalization in adapters (forward slash vs backslash)

**Deployment Strategy**:
- Canonical harness published as reusable library (git, npm, etc.)
- Each workspace installs harness as dependency/submodule
- Project-specific config in `.orchestrator-config.yaml`
- Project-specific logs and work directories in workspace
- Harness updates pulled from canonical source

## Orchestrator–Worker Model (NEW)

### Overview

The orchestrator–worker pattern replaces the mechanical driver loop with an intelligent reasoning executive. Cascade acts as the orchestrator, while stateless Devin workers execute skills as neutral actors.

### Key Components

**Cascade (Orchestrator):**
- Follows ORCHESTRATION-RUNBOOK.md literally as the protocol
- Performs triage decisions after each stage (HIGH/MEDIUM/LOW confidence)
- Dispatches to Devin workers with focused context (per-skill context manifest)
- Dispatches to neutral reviewer for every artifact evaluation (swe-1-6 free)
- Handles correction loop with bounded retries
- Escalates to human or tiered model (claude-code) when needed

**Devin Workers (Stateless Neutral Actors):**
- Execute skills with focused context only (not Cascade's full context)
- Produce required artifacts per skill definition
- No stake in outcome → more neutral, often better results
- On failure, re-dispatch with (previous output + Cascade correction)

**Deterministic Tools (Audit Rails):**
- `floor_validator.validate_structural()` - checks existence, non-emptiness, no placeholders
- `floor_validator.validate_iron_law()` - checks Iron Law compliance
- `floor_validator.validate_format()` - checks YAML/JSON format
- `audit_helpers.append_audit()` - records to session-audit.md (markdown)
- `audit_helpers.record_gate()` - records gate verdicts
- `audit_helpers.write_run_jsonl()` - records to run.jsonl (machine-readable)

### Protocol

For each stage in the workflow:
1. Dispatch to Devin worker with focused context
2. Validate structural floor (deterministic tool)
3. Dispatch neutral reviewer (always, separate worker)
4. Cascade synthesizes verdict + assigns confidence
5. If LOW confidence → correction loop (bounded retries)
6. If gate defined → HARD STOP, await human approval
7. Record to audit ledger + run.jsonl

### Resumability

State is reconstructed from:
- `run.jsonl` - machine-readable run transcript (timestamp, stage, skill, confidence, etc.)
- Artifacts - all produced artifacts (requirement.md, design.md, etc.)
- Correction artifacts - `correction-{stage}-{attempt}.md`
- Review artifacts - `review-{stage}-{attempt}.md`
- Gate artifacts - `gate-{gate_id}.md`

No reliance on volatile context.

### Deployment

Canonical source: `devin-orchestrator` repository
- `workflows/*.manifest.yaml` - structured workflow manifests
- `workflows/*.runbook.md` - agent-facing orchestration runbooks
- `skills/*` - skill definitions
- `workflow-engine/*` - deterministic tools and dispatch mechanics

Deployed to workspace per DEPLOYMENT.md protocol.

## Open Questions

1. **Skill schema granularity**: How much structure in skill YAML vs. prose?
2. **Workflow engine implementation**: PowerShell script vs. Windsurf tool vs cross-platform script?
3. **Transport adapter discovery**: How does the system know which adapter to use?
4. **Cross-harness session state**: How to share session state across harnesses?
5. **Knowledge base portability**: How to make KB files harness-agnostic?
6. **Rule enforcement mechanism**: How to enforce architect rules across harnesses?
7. **Cross-platform execution**: Should we provide both PowerShell and Bash scripts, or use a cross-platform language like Python?

## Next Steps

1. **Validate design with user**: Review this architecture for alignment with goals
2. **Prototype skill schema**: Convert one skill (e.g., brainstorming) to YAML + markdown
3. **Prototype workflow engine**: Implement basic step execution with gate enforcement
4. **Prototype transport adapter**: Implement Windsurf-Cascade adapter with one dispatch
5. **Test end-to-end**: Run a simple /gated-change session through the new architecture
6. **Iterate based on findings**: Refine schemas, contracts, and interfaces

## References

- [obra/superpowers](https://github.com/obra/superpowers) - Original skills framework
- [skills/README.md](skills/README.md) - Current skills library
- [workflow-engine/MANIFEST-SCHEMA.md](workflow-engine/MANIFEST-SCHEMA.md) - Workflow manifest schema
- [ORCHESTRATION-RUNBOOK.md](ORCHESTRATION-RUNBOOK.md) - Multi-agent dispatch runbook
- [workflows/superpower.runbook.md](workflows/superpower.runbook.md) - Example workflow implementation

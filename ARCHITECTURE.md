---
title: Generic Windsurf-Based Harness Architecture
created: 2026-06-19
status: design-draft
author: Cascade
related:
  - https://github.com/obra/superpowers
  - orchestrator/workflows/gated-change.md
  - orchestrator/skills/README.md
  - orchestrator/multi-agent-orchestration.md
---

# Generic Windsurf-Based Harness Architecture

## Executive Summary

This design synthesizes patterns from [obra/superpowers](https://github.com/obra/superpowers) with the ci-docs orchestrator workflow to create a generic, harness-agnostic framework for AI-assisted software development. The architecture separates **skills** (process disciplines) from **harness mechanisms** (transport adapters), enabling the same methodology to work across Windsurf Cascade, Claude Code, Devin CLI, and future platforms.

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
workflow:
  session_shape: gated-change
  session_id_format: CHANGE-NNN
  session_init:
    command: Invoke-SessionInit.ps1
    creates_workdir: orchestrator/work/<session_id>/
  auto_load:
    - path: orchestrator/agents/rules/architect-rules.md
      always: true
    - path: orchestrator/lessons/lessons.yaml
      always: true
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
    - id: g1_design_approval
      after_step: 1
      type: user_gate
    - id: g3_design_approval
      after_step: 3
      type: user_gate
  skills:
    - name: brainstorming
      phases: [step_1]
    - name: writing-plans
      phases: [step_3]
    - name: subagent-driven-development
      phases: [step_4]
    - name: test-driven-development
      phases: [step_2, step_4]
    - name: code-review
      phases: [step_6]
    - name: verification-before-completion
      phases: [step_5]
```

**Key properties**:
- **Dual source of truth**: Markdown (narrative) + YAML (structured)
- **Artifact contracts**: Required files per step, validated at close
- **Gate definitions**: User gates, mid-step checks, artifact checks
- **Skill scoping**: Which skills apply to which phases

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
│                   Workflow Orchestration Layer              │
│  (Session management, step execution, gate enforcement)     │
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
Workflow Selection (e.g., /gated-change)
     │
     ▼
Session Init (Invoke-SessionInit.ps1)
     │
     ├─→ Create workdir: orchestrator/work/<session_id>/
     ├─→ Auto-load: architect-rules.md, lessons.yaml, skills/README.md
     ├─→ Initialize artifacts: request.md, status.md, session-audit.md
     └─→ Emit ack: "Loaded: architect-rules v<N>, <M> lessons, <S> skills"
     │
     ▼
Step 1: UNDERSTAND
     │
     ├─→ Skill: brainstorming (announce per Rule 38)
     ├─→ KB retrieval (per scope)
     ├─→ Context exploration
     ├─→ Design dialogue with user
     ├─→ Write requirement.md
     └─→ User gate: approve requirement
     │
     ▼
Step 2: BASELINE
     │
     ├─→ Skill: test-driven-development
     ├─→ Identify existing tests
     ├─→ Run tests → green baseline
     ├─→ Write test specification
     ├─→ Dispatch Test-Author (via adapter)
     └─→ Verify tests FAIL (TDD red)
     │
     ▼
Step 3: DESIGN
     │
     ├─→ Skill: writing-plans
     ├─→ Produce design.md (approach, files, risks, KB impact)
     └─→ User gate: approve design
     │
     ▼
Step 4: IMPLEMENT
     │
     ├─→ Skill: subagent-driven-development
     ├─→ Assemble coder prompt (design.md + FRAMEWORK + ACs)
     ├─→ Dispatch Coder (via adapter)
     ├─→ Validate output (quality bar)
     └─→ Retry or escalate (Rule 17 budget)
     │
     ▼
Step 5: VERIFY
     │
     ├─→ Skill: verification-before-completion
     ├─→ Build (per actions/build.md)
     ├─→ Run tests (per actions/test.md)
     └─→ TDD green: new tests PASS, existing tests PASS
     │
     ▼
Step 6: REVIEW (three-stage)
     │
     ├─→ Stage 1: Spec-Reviewer (design-intent, AC coverage, scope)
     │   ├─→ Dispatch Spec-Reviewer (via adapter)
     │   └─→ Verdict: PASS/FAIL
     │
     ├─→ Stage 2: Quality-Reviewer (idioms, anti-patterns, edge cases)
     │   ├─→ Dispatch Quality-Reviewer (via adapter)
     │   └─→ Verdict: APPROVED/FAIL-CRITICAL/FAIL-IMPORTANT
     │
     └─→ Stage 3: Human Verdict (merge gate per Rule 52)
         ├─→ Invoke Invoke-HumanVerdict.ps1
         ├─→ Rate findings (A/D/P/C/S)
         ├─→ Capture KB candidates
         └─→ Decision: APPROVE/APPROVE-WITH-FOLLOWUP/REJECT/DEFER
     │
     ▼
Step 7: REPORT
     │
     ├─→ Write summary.md
     ├─→ Write metrics.json
     ├─→ Write retro.md (interruptions, rule violations, new lessons)
     ├─→ KB-delta emission (Rule 61)
     ├─→ Update orchestrator/metrics/
     ├─→ Promote lessons (≥3 triggers → Architect Rule)
     ├─→ Pin repo-specific facts
     └─→ User gate: approve final product + rule/lesson/KB updates
     │
     ▼
Step 8: FINALIZE
     │
     ├─→ Commit session work-dir
     ├─→ Merge or discard branch
     └─→ Close session (session-registry.md)
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

## Open Questions

1. **Skill schema granularity**: How much structure in skill YAML vs. prose?
2. **Workflow engine implementation**: PowerShell script vs. Windsurf tool?
3. **Transport adapter discovery**: How does the system know which adapter to use?
4. **Cross-harness session state**: How to share session state across harnesses?
5. **Knowledge base portability**: How to make KB files harness-agnostic?
6. **Rule enforcement mechanism**: How to enforce architect rules across harnesses?

## Next Steps

1. **Validate design with user**: Review this architecture for alignment with goals
2. **Prototype skill schema**: Convert one skill (e.g., brainstorming) to YAML + markdown
3. **Prototype workflow engine**: Implement basic step execution with gate enforcement
4. **Prototype transport adapter**: Implement Windsurf-Cascade adapter with one dispatch
5. **Test end-to-end**: Run a simple /gated-change session through the new architecture
6. **Iterate based on findings**: Refine schemas, contracts, and interfaces

## References

- [obra/superpowers](https://github.com/obra/superpowers) - Original skills framework
- `orchestrator/skills/README.md` - Current skills library
- `orchestrator/workflows/MANIFEST-SCHEMA.md` - Workflow manifest schema
- `orchestrator/multi-agent-orchestration.md` - Multi-agent dispatch contracts
- `orchestrator/workflows/gated-change.md` - Example workflow implementation

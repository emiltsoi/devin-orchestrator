# Phase 1 Implementation Plan

## Objective

Implement basic workflow engine with manual skill invocation and step execution, following progressive disclosure principles for skills.

## Phase 1 Scope

**In Scope:**
- Manifest loader (YAML parsing, validation)
- Session manager (directory creation, state tracking)
- Basic step executor (step iteration, status updates)
- Manual skill invocation (Architect executes skills in Cascade)
- Minimal skill set with progressive disclosure

**Out of Scope:**
- Automated skill dispatch via transport adapters
- Gate enforcement (manual approval only)
- Artifact validation (basic existence check only)
- Transport adapter integration
- Error handling and recovery
- Config schema validation

## Implementation Order

### 1. Manifest Loader
**File**: `workflow-engine/manifest_loader.py`

**Responsibilities:**
- Load YAML manifest from file
- Parse schema version
- Validate required fields
- Validate skill references
- Validate gate references
- Return parsed manifest object

**Validation Rules:**
- schema_version must be 1
- session_shape, description, slash_command required
- session_id_format required
- session_init required
- auto_load required
- required_artifacts required
- gates required
- skills required
- branch required

### 2. Session Manager
**File**: `workflow-engine/session_manager.py`

**Responsibilities:**
- Create session directory
- Initialize artifacts (request.md, status.md, session-audit.md)
- Track current step and phase
- Update status.md on phase transitions
- Handle session completion/failure

**Session State Structure:**
```yaml
session_id: FEATURE-001
current_step: step_0
current_phase: context
status: in_progress
retries: 0
start_time: 2026-06-19T04:42:00Z
end_time: null
```

**Status.md Format:**
```
phase=step-0  skill=context  retries=0/0
phase=step-1  skill=brainstorming  retries=0/0
...
```

### 3. Basic Step Executor
**File**: `workflow-engine/step_executor.py`

**Responsibilities:**
- Load manifest
- Execute step_0 (session init)
- For each step:
  - Load required skills
  - Announce skill invocation
  - Wait for manual skill execution
  - Validate required artifacts exist
  - Update status.md
  - Proceed to next step

**Process Flow:**
```
Load manifest → Initialize session → Execute step_0
Loop through steps:
  - Announce skill
  - Wait for manual execution
  - Check artifacts exist
  - Update status
  - Next step
```

### 4. Skills (Progressive Disclosure)

**Principle**: Add skills only when needed for testing, with minimal content initially.

#### 4.1 test-driven-development
**When**: After step executor can execute step_2
**Initial Content**: YAML skeleton + basic narrative
**Progressive**: Add detailed TDD process after basic flow works

#### 4.2 verification-before-completion
**When**: After step executor can execute step_5
**Initial Content**: YAML skeleton + basic narrative
**Progressive**: Add detailed verification steps after basic flow works

#### 4.3 code-review
**When**: After step executor can execute step_6
**Initial Content**: YAML skeleton + basic narrative
**Progressive**: Add detailed review stages after basic flow works

## Progressive Disclosure Strategy

**Skill YAML Structure (Initial):**
```yaml
schema_version: 1
name: <skill-name>
description: <one-line description>
iron_law: "<core principle>"
triggers: [<trigger>]
checklist:
  - id: step_1
    description: "<first step>"
terminal_state: <next-skill>
announcement: "Using the <skill-name> skill for <purpose>"
red_flags: []
```

**Skill Markdown Structure (Initial):**
```markdown
# <Skill Name>

## Overview
<brief description>

## The Iron Law
<core principle>

## When to Use
<conditions>

## Relation to Workflows
<workflow context>
```

**Progressive Expansion:**
- Start with skeleton
- Add detailed process after basic flow works
- Add examples after process works
- Add edge cases after examples work

## Testing Strategy

### Unit Tests
- Manifest loader: valid/invalid manifests
- Session manager: directory creation, state updates
- Step executor: step iteration, status updates

### Integration Tests
- End-to-end execution of feature workflow
- Manual skill invocation simulation
- Artifact validation

### Test Order
1. Test manifest loader with valid manifest
2. Test session manager with session creation
3. Test step executor with single step
4. Test step executor with multiple steps
5. Test end-to-end with feature workflow

## Success Criteria

- [ ] Manifest loader loads and validates feature.manifest.yaml
- [ ] Session manager creates session directory and artifacts
- [ ] Step executor iterates through steps
- [ ] Status.md updated on each phase transition
- [ ] Required skills exist (even if minimal)
- [ ] End-to-end test executes step_0 through step_7
- [ ] Skills follow progressive disclosure (minimal initial content)

## Dependencies

- Python 3.8+
- PyYAML for YAML parsing
- pathlib for cross-platform paths

## Next Steps After Phase 1

- Phase 2: Gate enforcement and artifact validation
- Phase 3: Transport adapter integration
- Phase 4: Automated skill dispatch
- Phase 5: Error handling and recovery

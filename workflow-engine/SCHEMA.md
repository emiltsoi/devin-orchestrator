# Workflow Engine Schema

## Overview

The workflow engine executes workflow manifests by coordinating skills, gates, and transport adapters. It manages session state, enforces gates, and validates artifacts.

## Core Components

### 1. Manifest Loader

**Purpose**: Load and validate workflow manifests

**Input**: `workflows/<workflow>.manifest.yaml`

**Output**: Parsed manifest object

**Validation**:
- Schema version compatibility
- Required fields present
- Skill references valid
- Gate references valid
- Artifact paths valid

### 2. Session Manager

**Purpose**: Manage session lifecycle and state

**Responsibilities**:
- Create session directory
- Initialize artifacts (request.md, status.md, session-audit.md)
- Track current step and phase
- Update status.md on phase transitions
- Handle session completion/failure

**Session State**:
```yaml
session_id: FEATURE-NNN
current_step: step_0
current_phase: context
status: in_progress
retries: 0
start_time: ISO8601
end_time: null
```

### 3. Step Executor

**Purpose**: Execute workflow steps in order

**Process**:
1. Load manifest
2. Execute step_0 (session init)
3. For each step:
   - Load required skills
   - Execute skill
   - Validate required artifacts
   - Check for gates
   - Update status.md
   - Proceed to next step or handle gate

### 4. Skill Invoker

**Purpose**: Invoke skills at appropriate phases

**Process**:
1. Load skill YAML definition
2. Load skill markdown narrative
3. Check skill triggers
4. Execute skill checklist
5. Track skill completion

**Skill Execution**:
- Manual (Architect executes skill in Cascade)
- Automated (future: dispatch via transport adapter)

### 5. Gate Manager

**Purpose**: Enforce user gates

**Gate Types**:
- `user_gate`: Requires explicit user approval
- `auto_gate`: Automatic based on conditions

**Gate Process**:
1. Check if gate exists after current step
2. If user_gate: prompt user for approval
3. If approved: proceed to next step
4. If rejected: handle rejection (retry, defer, abort)

### 6. Artifact Validator

**Purpose**: Validate required artifacts exist

**Process**:
1. Check manifest required_artifacts for current step
2. Verify each artifact exists in session directory
3. Validate artifact schema if applicable
4. Report missing artifacts

### 7. Transport Adapter Manager

**Purpose**: Manage transport adapter dispatch

**Process**:
1. Load transport adapter configuration
2. Select adapter based on platform/config
3. Dispatch via adapter (manual or automated)
4. Capture output
5. Validate quality bar

**Adapters**:
- `windsurf-cascade`: Manual copy-paste
- `devin-cli`: Automated via ACP

## Data Flow

```
Manifest Loader → Session Manager → Step Executor
                                      ↓
                              Skill Invoker ← Gate Manager
                                      ↓
                              Artifact Validator
                                      ↓
                              Transport Adapter Manager
```

## Error Handling

**Manifest Errors**:
- Invalid schema: Abort with clear error
- Missing skill: Abort with clear error
- Invalid gate: Abort with clear error

**Execution Errors**:
- Skill failure: Retry (up to limit) or escalate
- Artifact missing: Abort with clear error
- Gate rejected: Handle per gate type
- Transport failure: Retry (up to limit) or escalate

**Session Errors**:
- Directory creation failure: Abort
- File write failure: Abort
- State corruption: Abort

## Configuration

**Workflow Engine Config** (`workflow-engine.yaml`):
```yaml
default_adapter: windsurf-cascade
max_retries: 2
timeout_seconds: 3600
auto_approve_gates: false
```

**Session Config** (`.orchestrator-config.yaml`):
```yaml
workflow:
  adapter: devin-cli
  auto_approve_gates: false
  max_retries: 2
```

## API Design

```python
from workflow_engine import WorkflowEngine

engine = WorkflowEngine()
engine.load_manifest('workflows/feature.manifest.yaml')
engine.initialize_session('FEATURE-001')
engine.execute_step('step_0')
engine.execute_step('step_1')
# ... continue through steps
engine.finalize_session()
```

## Implementation Priority

1. **Phase 1**: Basic step execution with manual skill invocation
2. **Phase 2**: Gate enforcement and artifact validation
3. **Phase 3**: Transport adapter integration
4. **Phase 4**: Automated skill dispatch
5. **Phase 5**: Error handling and recovery

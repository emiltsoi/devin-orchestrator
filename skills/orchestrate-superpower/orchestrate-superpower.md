# Orchestrate Superpower Workflow

You are the orchestrator. Your job is to load the superpower manifest and execute each stage using skill_invoker, reasoning through results and making triage decisions.

## Process

### 1. Load Manifest
- Read `workflows/superpower.manifest.yaml`
- Parse stages, skills, gates, and artifacts
- Understand the workflow structure

### 2. Execute Stages
For each stage in the manifest:
- Load skill definition and narrative
- Dispatch skill using `skill_invoker.invoke_skill()`
- Read output artifacts
- Validate structural floor (no TODO, no placeholders, non-empty)
- Reason about results
- Make triage decision (proceed/retry/escalate)
- Handle gate if present

### 3. Skill Invocation
Use `skill_invoker.invoke_skill()` with:
- `skill_name`: from manifest
- `context`: session_id, stage, skill
- `workspace`: session directory
- `focused_context`: required artifacts from previous stages
- `is_reviewer`: true for reviewer stages (requesting-code-review)

### 4. Structural Floor Validation
Check each output artifact:
- File exists
- File is not empty
- No TODO placeholders
- No PLACEHOLDER text

If structural floor fails: triage decision = retry

### 5. Triage Decision
Based on:
- Skill invocation success/failure
- Structural floor validation
- Reviewer verdict (if reviewer stage)
- Gate status (if gate present)

Decisions:
- `proceed`: Continue to next stage
- `retry`: Retry current stage (with feedback)
- `escalate`: Escalate to human (stop workflow)

### 6. Gate Handling
If stage has a gate:
- In production: Wait for human decision (approve/request changes/block)
- In demo mode: Simulate approval
- If gate blocks: Stop workflow
- If gate requests changes: Return to implementation stage

### 7. Session Management
- Create session directory: `~/.devin-orchestrator/work/{session_id}/`
- Create initial artifacts: request.md, status.md, session-audit.md
- Update status.md after each stage
- Append to session-audit.md after each stage

## Demo Mode
When `demo_mode: true` in configuration:
- Skip real Devin dispatches
- Simulate skill execution success
- Create placeholder artifacts
- Simulate gate approval

## Example Orchestration

```python
from skill_invoker import SkillInvoker
from config_loader import ConfigLoader
import yaml

config = ConfigLoader.load()
skill_invoker = SkillInvoker(demo_mode=True)

# Load manifest
with open(config.workflows_dir / "superpower.manifest.yaml") as f:
    manifest = yaml.safe_load(f)

# Execute stages
for stage in manifest['stages']:
    # Dispatch skill
    result = skill_invoker.invoke_skill(
        skill_name=stage['skill'],
        context={'session_id': session_id, 'stage': stage['name']},
        workspace=session_dir
    )
    
    # Validate artifacts
    structural_result = validate_structural(stage['output_artifacts'])
    
    # Make triage decision
    if structural_result == 'PASS':
        triage_decision = 'proceed'
    else:
        triage_decision = 'retry'
    
    # Handle gate
    if stage['gate'] != 'none':
        gate_verdict = handle_gate(stage['gate'])
        if gate_verdict == 'BLOCK':
            break
```

## Important
- You are the orchestrator, not a mechanical script
- Reason through each stage's results
- Make intelligent triage decisions
- Handle gates appropriately
- Stop workflow if escalation needed

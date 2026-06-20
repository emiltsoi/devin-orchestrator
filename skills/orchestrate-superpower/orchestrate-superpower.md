# Orchestrate Superpower Workflow

You are the orchestrator. Your job is to load the superpower manifest and execute each stage directly, reasoning through results and making triage decisions.

## Process

### 1. Load Manifest
- Read `workflows/superpower.manifest.yaml`
- Parse stages, skills, gates, and artifacts
- Understand the workflow structure

### 2. Execute Stages
For each stage in the manifest:
- Load skill definition and narrative from `~/.devin-orchestrator/skills/{skill_name}/`
- **Execute the skill logic directly** (you are the worker, not a dispatcher)
- Read output artifacts
- Validate structural floor (no TODO, no placeholders, non-empty)
- Reason about results
- Make triage decision (proceed/retry/escalate)
- Handle gate if present

### 3. Skill Execution (IMPORTANT)
You MUST execute the skill logic directly. Do NOT dispatch to external processes - you are the worker.

Load the skill definition and narrative:
```python
from pathlib import Path
import yaml

skill_dir = Path.home() / ".devin-orchestrator" / "skills" / stage['skill']
skill_def = yaml.safe_load((skill_dir / f"{stage['skill']}.yaml").read_text())
skill_narrative = (skill_dir / f"{stage['skill']}.md").read_text()
```

Execute the skill by following the skill narrative:
- Read the skill narrative (markdown file)
- Follow the checklist and instructions
- Use your available tools to execute the skill logic
- Produce the required artifacts
- Follow the iron_law constraints

### 4. Structural Floor Validation
Check each output artifact:
- File exists
- File is not empty
- No TODO placeholders
- No PLACEHOLDER text

If structural floor fails: triage decision = retry

### 5. Triage Decision
Based on:
- Skill execution success/failure
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

## Important
- You are the orchestrator AND the worker
- **You MUST execute skill logic directly using your available tools**
- Do NOT dispatch to external processes - you are the worker
- Load skill definitions and narratives from global location
- Follow skill checklists and instructions
- Produce required artifacts
- Reason through each stage's results
- Make intelligent triage decisions
- Handle gates appropriately
- Stop workflow if escalation needed

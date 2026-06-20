# Devin Dispatch Pattern

## Overview

The orchestrator–worker pattern uses SWE-1.6 (free tier) via Devin CLI with skill loading via description matching. This document codifies the dispatch pattern for coder and reviewer workers.

## Skill Loading Mechanism

Skills are loaded from `workflow-engine/skills/` and injected into prompts when their description matches prompt content. The matching is done via specific trigger phrases to avoid false positives.

### Installed Skills

1. **ponytail** - YAGNI/laziness discipline
   - Description: "Triggers on coding dispatches and implementation tasks. Forces the laziest solution that actually works — standard library first, one line before fifty, deletion over addition."
   - Trigger phrases: "coding dispatch" or "implementation task"

2. **swe-compliance** - Ruthless compliance reviewer
   - Description: "Triggers on compliance review tasks, code verification, artifact audits, and quality checks. Ruthless mechanical reviewer — find what's wrong, don't be polite about it."
   - Trigger phrases: "compliance review" or "code verification" or "artifact audit"

## Coder Dispatch Pattern

```python
from skill_invoker import SkillInvoker
from devin_cli_adapter import DevinCliAdapter

# Initialize skill invoker with SWE-1.6 model
devin_cli_path = "C:\\Users\\<username>\\AppData\\Local\\devin\\cli\\bin\\devin.exe"
skill_invoker = SkillInvoker(
    harness_root=harness_root,
    devin_cli_path=devin_cli_path,
    model="swe-1.6"
)

# Prepare context
context = {
    "session_id": session_id,
    "stage": "step_1",
    "skill": skill_name
}

# Dispatch coder with ponytail skill (is_reviewer=False)
result = skill_invoker.invoke_skill(
    skill_name=skill_name,
    context=context,
    workspace=str(session_dir),
    focused_context=injected_context,
    is_reviewer=False  # Triggers ponytail skill
)
```

**What happens:**
1. `skill_invoker.invoke_skill()` builds prompt with trigger phrase: "This is a coding dispatch and implementation task."
2. `devin_cli_adapter._inject_skills()` detects trigger phrase and injects ponytail skill content
3. Devin CLI executes with ponytail discipline active
4. Worker produces artifact with YAGNI/laziness constraints

## Reviewer Dispatch Pattern

```python
from skill_invoker import SkillInvoker
from devin_cli_adapter import DevinCliAdapter

# Initialize skill invoker with SWE-1.6 model
devin_cli_path = "C:\\Users\\<username>\\AppData\\Local\\devin\\cli\\bin\\devin.exe"
skill_invoker = SkillInvoker(
    harness_root=harness_root,
    devin_cli_path=devin_cli_path,
    model="swe-1.6"
)

# Prepare context
context = {
    "session_id": session_id,
    "stage": "step_1",
    "skill": skill_name
}

# Dispatch reviewer with swe-compliance skill (is_reviewer=True)
result = skill_invoker.invoke_skill(
    skill_name=skill_name,
    context=context,
    workspace=str(session_dir),
    focused_context=injected_context,
    is_reviewer=True  # Triggers swe-compliance skill
)
```

**What happens:**
1. `skill_invoker.invoke_skill()` builds prompt with trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check."
2. `devin_cli_adapter._inject_skills()` detects trigger phrase and injects swe-compliance skill content
3. Devin CLI executes with compliance reviewer discipline active
4. Reviewer produces PASS/BLOCK verdict with findings

## Guardrails

Before dispatching coder:
```python
from guardrails import Guardrails

# Check leaf module boundary
boundary_check = Guardrails.check_leaf_module_boundary(target_module, workspace)
if not boundary_check["is_leaf"]:
    # ESCALATE to human - SWE-1.6 lacks reasoning depth for cross-cutting work
    escalate_to_human("Target module exceeds leaf module boundary (coupling > 2)")
```

After reviewer BLOCK verdict:
```python
from guardrails import Guardrails

# Independently verify compliance BLOCK verdict
verification = Guardrails.verify_compliance_block(block_verdict, file_path)
if not verification["verified"]:
    # Compliance reviewer hallucinated - escalate to human
    escalate_to_human(f"Compliance BLOCK could not be verified: {verification['notes']}")
```

## Complete Dispatch Flow

```python
# 1. Check leaf module boundary (guardrail)
boundary_check = Guardrails.check_leaf_module_boundary(target_module, workspace)
if not boundary_check["is_leaf"]:
    escalate_to_human("Target module exceeds leaf module boundary")

# 2. Dispatch coder with ponytail skill
coder_result = skill_invoker.invoke_skill(
    skill_name=skill_name,
    context=context,
    workspace=str(session_dir),
    focused_context=injected_context,
    is_reviewer=False
)

# 3. Validate structural floor
structural_result = validate_structural([artifact_path])
if structural_result["result"] == "FAIL":
    # Enter correction loop
    retry_with_feedback(correction_artifact)

# 4. Dispatch reviewer with swe-compliance skill
reviewer_result = skill_invoker.invoke_skill(
    skill_name=skill_name,
    context=context,
    workspace=str(session_dir),
    focused_context=injected_context,
    is_reviewer=True
)

# 5. If reviewer BLOCK, independently verify
if reviewer_result.verdict == "BLOCK":
    verification = Guardrails.verify_compliance_block(reviewer_result.output, artifact_path)
    if not verification["verified"]:
        escalate_to_human("Compliance BLOCK could not be verified")

# 6. Cascade triage decision
# (Based on structural_result + reviewer_verdict + verification)
```

## Implementation in Demo

See `demo_orchestrator_worker.py` for the demonstration of this pattern:
- Stage 1 (brainstorming) shows coder dispatch pattern with `is_reviewer=False`
- Stage 1 also shows reviewer dispatch pattern with `is_reviewer=True`
- Comments indicate where real dispatches would occur in production

## References

- `workflow-engine/devin_cli_adapter.py` - Skill loading implementation
- `workflow-engine/skill_invoker.py` - Skill invocation with trigger phrases
- `workflow-engine/guardrails.py` - Guardrail implementations
- `workflow-engine/skills/ponytail/SKILL.md` - Ponytail skill definition
- `workflow-engine/skills/swe-compliance/SKILL.md` - SWE compliance skill definition
- `ORCHESTRATION-RUNBOOK.md` - Section 6: Devin Dispatch Protocol

---
name: subagent-driven-development
description: "Use when executing an implementation plan with independent tasks by dispatching a fresh implementer subagent per task with reviews."
---

# Subagent-Driven Development

Execute plan by dispatching a fresh implementer subagent per task, a task review (spec compliance + code quality) after each, and a broad whole-branch review at the end.

**Why subagents:** You delegate tasks to specialized agents with isolated context. By precisely crafting their instructions and context, you construct exactly what they need. They should never inherit your session's context or history — you preserve your own context for coordination work.

**Core principle:** Fresh subagent per task + task review (spec + quality) + broad final review = high quality, fast iteration

**Narration:** Between tool calls, narrate at most one short line — the ledger and the tool results carry the record.

**Continuous execution:** Do not pause to check in with your human partner between tasks. Execute all tasks from the plan without stopping. The only reasons to stop are: BLOCKED status you cannot resolve, ambiguity that genuinely prevents progress, or all tasks complete.

## When to Use

Use this skill when:
- You have a complete implementation plan with independent tasks
- Tasks can be executed by fresh subagents with isolated context
- You want two-stage review (spec compliance + code quality) per task
- You want fast iteration with quality gates

## The Process

### Pre-Flight Plan Review

Before dispatching any subagent, verify the plan is complete and unambiguous:
- All tasks have exact file paths
- All tasks have complete code (no placeholders)
- All tasks have verification steps
- Task dependencies are clear
- Global constraints are included

If the plan has issues, address them before proceeding.

### Model Selection

Choose the appropriate model for each task:
- **SWE-1.6 (free tier):** Leaf modules, mechanical tasks, tight specs
- **Higher-quality model:** Architecture, cross-cutting work, judgment tasks

Use the decision matrix encoded in `dispatch_devin.py` / `dispatch_skill.py` and the model routing configured in `config.yaml` (`model_overrides` → `models` → `model_profile` → `default_model`, resolved by `resolve_model(agent, phase, config)`).

### Handling Implementer Status

When the implementer subagent reports:
- **SUCCESS:** Proceed to task review
- **BLOCKED:** If you can resolve, resolve and retry. If not, ESCALATE to human
- **PARTIAL:** If partial progress is useful, proceed to review. If not, retry or ESCALATE

### Handling Reviewer ⚠️ Items

When the reviewer subagent reports ⚠️ items:
- **Spec compliance issues:** Must be fixed before proceeding
- **Code quality issues:** Fix if critical, note if minor
- **Ambiguity:** Clarify and fix if needed
- **Style:** Note but don't block unless specified in plan

### Constructing Reviewer Prompts

For task review, construct prompts that check:
1. **Spec compliance:** Does the implementation match the plan exactly?
2. **Code quality:** Is the code well-structured, tested, documented?
3. **Edge cases:** Are edge cases handled?
4. **Error handling:** Is error handling appropriate?

### File Handoffs

When tasks depend on files from previous tasks:
- Pass the exact file paths to the next subagent
- Include context about what the file does
- Ensure the subagent has the right version

### Durable Progress

Track completed tasks:
- Mark tasks as complete in the plan
- Record which files were created/modified
- Note any deviations from the plan
- Keep a summary of all changes

### Broad Final Review

After all tasks complete, do a broad whole-branch review:
- Review all changes together
- Check for consistency across tasks
- Verify the overall implementation matches the spec
- Look for integration issues

## Prompt Templates

### Implementer Subagent Prompt

```
You are implementing a specific task from an implementation plan.

TASK: [task description]
FILES TO TOUCH: [exact file paths]
CODE TO WRITE: [complete code]
TESTING: [how to test]
VERIFICATION: [how to verify]

Context: [relevant context from previous tasks]

Execute this task exactly as specified. Do not deviate from the plan.
```

### Reviewer Subagent Prompt

```
You are reviewing a task implementation against the plan.

PLAN TASK: [task description]
IMPLEMENTATION: [implementation details]
FILES MODIFIED: [file paths]

Check:
1. Spec compliance: Does it match the plan exactly?
2. Code quality: Is it well-structured, tested, documented?
3. Edge cases: Are edge cases handled?
4. Error handling: Is error handling appropriate?

Report: PASS/BLOCK with findings.
```

## Example Workflow

1. Load plan from `plan.md`
2. For each task in plan:
   a. Dispatch implementer subagent
   b. If SUCCESS, dispatch reviewer subagent
   c. If reviewer BLOCK, fix and retry
   d. Mark task complete
3. After all tasks, do broad final review
4. Report completion

## Advantages

- **Isolation:** Each subagent has focused context
- **Quality:** Two-stage review per task
- **Speed:** Parallel execution where possible
- **Coordination:** You preserve context for coordination

## Red Flags

- Reusing the same subagent for multiple tasks
- Skipping task review
- Not fixing spec compliance issues
- Proceeding with ambiguous plan
- Not tracking completed tasks

## Integration

After completing all tasks with reviews, invoke the `test-driven-development` skill to enforce RED-GREEN-REFACTOR cycle.

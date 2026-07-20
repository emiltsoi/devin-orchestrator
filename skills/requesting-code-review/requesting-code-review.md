---
name: requesting-code-review
description: "Use when completing tasks, implementing major features, or before merging to verify work meets requirements via a dispatched code reviewer subagent."
---

# Requesting Code Review

Dispatch a code reviewer subagent to catch issues before they cascade. The reviewer gets precisely crafted context for evaluation — never your session's history. This keeps the reviewer focused on the work product, not your thought process, and preserves your own context for continued work.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Dispatch code reviewer subagent:**

Dispatch a reviewer subagent with the following context:

```
DESCRIPTION: [Brief summary of what you built]
PLAN_OR_REQUIREMENTS: [What it should do - from plan.md or design.md]
BASE_SHA: [Starting commit]
HEAD_SHA: [Ending commit]
FILES_MODIFIED: [List of files changed]
```

**3. Act on feedback:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if reviewer is wrong (with reasoning)

## Reviewer Prompt Template

```
You are reviewing code changes against a plan or requirements.

DESCRIPTION: {DESCRIPTION}
PLAN_OR_REQUIREMENTS: {PLAN_OR_REQUIREMENTS}
BASE_SHA: {BASE_SHA}
HEAD_SHA: {HEAD_SHA}
FILES_MODIFIED: {FILES_MODIFIED}

Review the changes and report:
- Strengths: What's good about this implementation
- Issues: List by severity (Critical, Important, Minor)
- Assessment: Ready to proceed / needs fixes / blocked

Critical issues block progress. Important issues should be fixed before proceeding. Minor issues can be noted for later.
```

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request code review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[Dispatch code reviewer subagent]
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types
  PLAN_OR_REQUIREMENTS: Task 2 from plan.md
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661

[Subagent returns]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators
    Minor: Magic number (100) for reporting interval
  Assessment: Ready to proceed

You: [Fix progress indicators]
[Continue to Task 3]
```

## Integration with Workflows

**Subagent-Driven Development:**
- Review after EACH task
- Catch issues before they compound
- Fix before moving to next task

**Executing Plans:**
- Review after each task or at natural checkpoints
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Review before merge
- Review when stuck

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

## Severity Levels

**Critical:**
- Security vulnerabilities
- Data loss risk
- Breaking changes
- Incorrect behavior

**Important:**
- Performance issues
- Error handling gaps
- Missing edge cases
- Test coverage gaps

**Minor:**
- Style issues
- Naming inconsistencies
- Documentation gaps
- Code organization

## After Review

**If ready to proceed:**
- Continue to next task
- Or proceed to next workflow stage

**If needs fixes:**
- Fix the issues
- Re-request review if Critical/Important
- Note Minor issues for later

**If blocked:**
- Fix Critical issues
- Re-request review
- Don't proceed until unblocked

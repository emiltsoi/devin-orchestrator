---
name: executing-plans
description: "Use when executing an approved plan task-by-task in the current context with human checkpoints between tasks."
---

# Executing Plans

## Overview

Execute a pre-written plan task-by-task in the same context, with human checkpoints between tasks. This skill is for inline execution when you are running the plan yourself, as opposed to subagent-driven-development which orchestrates multiple subagents.

**Announce at start:** `Using the executing-plans skill to execute the plan task-by-task.`

## The Iron Law

```
EXECUTE TASKS IN ORDER WITH VERIFICATION AFTER EACH
```

Never skip tasks or execute out of order. Always verify each task completion before proceeding to the next.

## When to Use

Use `executing-plans` when:
- You are executing an already-approved plan yourself
- You want inline same-context execution
- You need human checkpoints between tasks
- The plan is well-defined and ready for execution
- You prefer single-context execution over subagent orchestration

Use `subagent-driven-development` instead when:
- The Architect is orchestrating multiple tasks with review between each
- You want fresh subagent contexts for each task
- You need parallel execution of independent tasks

## Process Flow

```
Read and understand the plan
    │
    ▼
Execute first task
    │
    ▼
Verify task completion
    │
    ▼
Request human checkpoint (if configured)
    │
    ▼
Proceed to next task
    │
    ▼
Repeat until all tasks complete
    │
    ▼
Document execution results
    │
    ▼
Terminal state: plan execution complete
```

## The Process

**1. Read and understand the plan**

- Read the plan.md file
- Understand the overall goal
- Review task dependencies
- Check for required artifacts
- Verify the plan is approved and ready for execution

**2. Execute first task**

- Read the task description
- Understand the acceptance criteria
- Implement the task
- Follow the exact steps specified
- Use the specified file paths and code
- Create the required artifacts

**3. Verify task completion**

- Check that acceptance criteria are met
- Verify the implementation matches the plan
- Run any specified verification steps
- Test the changes if applicable
- Document any deviations from the plan

**4. Request human checkpoint (if configured)**

- Present task completion status
- Show any issues or deviations
- Request approval to proceed
- Wait for human feedback
- Adjust based on feedback if needed

**5. Proceed to next task**

- Move to the next task in the plan
- Repeat the execute-verify-checkpoint cycle
- Track progress with checkboxes
- Update task status in the plan

**6. Document execution results**

Create `execution-results.md` with:
- Summary of execution
- Tasks completed
- Tasks skipped or modified
- Issues encountered
- Deviations from the plan
- Final state
- Recommendations for plan improvements

## Required Artifacts

- **execution-results.md**: Documentation of plan execution with task status and any deviations

## Red Flags

- Skipping tasks without approval
- Executing tasks out of order
- Not verifying task completion
- Ignoring acceptance criteria
- Deviating from the plan without documentation
- Not requesting checkpoints when configured

## Done Means

You are done when:
- All tasks in the plan are executed (or documented as skipped)
- execution-results.md is created with complete execution summary
- All acceptance criteria are verified
- All checkpoints are completed
- The final state matches the plan goals
- Any deviations are documented with rationale

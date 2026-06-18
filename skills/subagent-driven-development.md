# Subagent-Driven Development

## Overview

Execute a plan by dispatching a fresh Coder context per task, with two-stage review after each: spec compliance review first, then code quality review.

**Why fresh contexts per task:** You delegate tasks to specialized roles. By precisely crafting their prompts and context, you ensure they stay focused and succeed. They should not inherit your Architect session's history — you construct exactly what each role needs. This also preserves the Architect's context for coordination work.

**Core principle:** Fresh context per task + two-stage review (spec then quality) = high quality, fast iteration.

**Announce at start:** `Using the subagent-driven-development skill to execute <session_id> task-by-task.`

## The Iron Law

```
FRESH CONTEXT PER TASK. TWO-STAGE REVIEW. NO SKIPPING REVIEWS.
```

Never reuse a Coder context across tasks. Never skip the spec-compliance or code-quality review. Never proceed with unfixed issues.

## When to Use

Use `subagent-driven-development` when:
- You have a plan (design.md) with multiple tasks
- Tasks are mostly independent (some ordering is fine)
- You will stay in this Architect session to orchestrate
- Review-per-task is worth the iteration cost

Use `executing-plans` instead when:
- Inline execution in a single context is preferred
- Plan is small enough that per-task review is overhead
- You're picking up partial work manually

## The Process

```
READ plan once ──▶ EXTRACT all tasks + context ──▶ TODO_LIST (one per task) ──▶ LOOP:
                                                                                    │
    ┌───────────────────────────────────────────────────────────────────────────────┘
    ▼
  Per task:
    1. Dispatch Coder (fresh prompt built from template + task-specific context)
    2. Coder asks questions?
         yes → answer & re-dispatch with augmented context
         no  → Coder implements, tests, commits, self-reviews
    3. Dispatch Spec-Reviewer (does code match the task's spec?)
         issues → Coder fixes → re-dispatch Spec-Reviewer
         ok     → proceed
    4. Dispatch Quality-Reviewer (is the code well-built?)
         issues → Coder fixes → re-dispatch Quality-Reviewer
         ok     → task complete
    5. Mark task complete in todo_list
    6. Next task or (all tasks done?) → Final full-scope review
```

## Dispatching a Coder (per task)

The Coder prompt is assembled from:
- `templates/coder-prompt.md` (role, constraints, output format)
- Task text **verbatim** from design.md (not a reference — the full text)
- Relevant context from `requirement.md`, knowledge files for the affected subsystem
- Architect Rules applicable to the Coder (subset — the Coder doesn't need the Architect's orchestration rules)

**Do NOT** have the Coder read the plan file itself — provide the full task text. This keeps the Coder focused on one task and prevents them from peeking ahead.

Dispatch via transport adapter (e.g., windsurf-cascade adapter with manual copy-paste or automated dispatch).

## Handling Coder Status

The Coder reports one of four statuses:

**`COMPLETED:`** — proceed to Spec-Reviewer.

**`COMPLETED_WITH_CONCERNS:`** — read the concerns. If about correctness or scope, address before review. If observations (e.g. "this file is getting large"), note and proceed.

**`NEEDS_CONTEXT:`** — the Coder needs info that wasn't in the prompt. Provide it and re-dispatch.

**`BLOCKED:`** — the Coder cannot complete the task. Assess:
1. Context problem → provide more context, re-dispatch with the same model
2. Task requires more reasoning → re-dispatch with a more capable model
3. Task is too large → break it into smaller pieces (back to `writing-plans`)
4. Plan is wrong → escalate to your human partner

**Never** ignore a BLOCKED or force a retry with the same input. If the Coder says stuck, something must change.

## Two-Stage Review

### Stage 1: Spec-Compliance Review

**Question:** Does the code do exactly what the task specified? No more, no less.

- Required behaviour present? ✅ / ❌
- Extra behaviour not in the spec? ❌ (remove or justify)
- Required files created / modified per the Files manifest? ✅ / ❌
- Required tests present and passing? ✅ / ❌

**Why this exists:** Catches "built the wrong thing" early — the Coder may have misread the task or added scope creep.

### Stage 2: Code-Quality Review

**Only after Stage 1 is ✅.** Question: Is the code well-built for *this codebase's conventions*?

- Correctness: edge cases, error paths, thread safety
- Style: matches surrounding code patterns
- Naming: consistent with existing symbols
- Tests: realistic, no mock-the-mock anti-patterns
- No "while I'm here" refactors bundled in
- No magic numbers (extract named constants)

**Why this exists:** Catches "built it badly" — the code works but is hard to maintain.

### Dispatching Reviewers

Use transport adapter with prompt built from reviewer template + task spec + git SHA range.

Create two prompt variants:
- `spec-reviewer-prompt.md` — focused on spec compliance only
- `quality-reviewer-prompt.md` — focused on code quality only

## Model Selection

Use the least powerful model that can handle each role:
- **Mechanical tasks** (isolated function, clear spec, 1-2 files) → cheap/fast model for Coder
- **Integration tasks** (multi-file coordination, pattern matching) → standard model
- **Architecture / review** → most capable model

Task complexity signals:
- Touches 1-2 files with a complete spec → cheap model
- Touches multiple files with integration concerns → standard model
- Requires design judgment or broad codebase understanding → most capable model

Default: SWE-1.6 for all roles (free, parallelizable up to 10 instances, target 8 parallel dispatches)

## Red Flags — STOP

**Never:**
- Start implementation on main/master without explicit user consent
- Skip the Spec-Reviewer or Quality-Reviewer
- Proceed with unfixed issues
- Dispatch multiple Coders in parallel on the SAME file set (conflicts)
- Make the Coder read design.md directly (provide full task text)
- Skip scene-setting context (the Coder needs to understand where the task fits)
- Ignore Coder questions (answer before letting them proceed)
- Accept "close enough" on spec compliance (Spec-Reviewer found issues = not done)
- Skip review loops (Reviewer found issues = Coder fixes = review again)
- **Start Quality-Review before Spec-Review is ✅** (wrong order)
- Move to the next task while either review has open issues

**If Coder asks questions:**
- Answer clearly and completely
- Provide additional context if needed
- Don't rush them into implementation

**If Reviewer finds issues:**
- Coder (dispatched freshly per fix iteration) fixes them
- Reviewer reviews again
- Repeat until approved (bounded by retry budget)
- Don't skip the re-review

**If Coder fails a task:**
- Dispatch a fix Coder with specific instructions
- Don't try to fix manually in the Architect session (context pollution)

## Advantages

**vs. manual execution in the Architect session:**
- Fresh context per task (no confusion, no peek-ahead)
- Architect context stays clean for coordination
- Coder can ask questions (before AND during work)
- TDD / skills are enforced per-task, not diluted

**vs. `executing-plans` (inline):**
- Review checkpoints automatic
- Issues caught early (cheaper than debugging later)
- Better for longer / riskier changes

**Cost:**
- More agent invocations (1 Coder + 2 Reviewers per task in the two-stage model)
- Architect does more prep work (extracting all tasks upfront)
- Review loops add iterations

## Integration

**Required predecessor skills:**
- `writing-plans` produces the plan this skill executes
- `brainstorming` produces the spec that `writing-plans` consumes

**Required sub-skills per task:**
- `test-driven-development` inside each Coder dispatch
- `verification-before-completion` at each review and at the final check
- `code-review` for the Reviewer dispatches

**Alternative:**
- `executing-plans` for inline same-context execution

## Relation to Workflows

- This skill is the pattern; workflow Step 4 (IMPLEMENT) is the concrete implementation
- Architect rules govern invocation (branch discipline, diff size, retries)
- Two-stage Reviewer is implemented via spec-reviewer and quality-reviewer prompts

## Attribution

Portions adapted from [obra/superpowers](https://github.com/obra/superpowers), Copyright © 2025 Jesse Vincent, MIT License.

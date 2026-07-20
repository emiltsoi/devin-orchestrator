---
name: receiving-code-review
description: "Use when receiving code review feedback that must be evaluated and addressed."
---

# Receiving Code Review

## Overview

Code review is technical evaluation, not emotional performance. Your job when receiving
feedback is to determine what is true, what is actionable, and what should be pushed
back on — then implement the verified items one at a time. Sycophantic agreement is a
red flag; so is reflexive defensiveness.

## The Response Pattern

Work through every piece of feedback in this order:

1. **READ** — Read all feedback completely before reacting to any of it.
2. **UNDERSTAND** — Restate each item in your own words. If you cannot restate it
   clearly, ask for clarification.
3. **VERIFY** — Check each claimed issue against the actual codebase. Reviewers can be
   wrong, out of date, or working from a stale diff.
4. **EVALUATE** — Assess technical soundness *for this codebase*. A correct general
   point may not apply here.
5. **RESPOND** — Reply with reasoned pushback or a technical acknowledgment. No
   performative language.
6. **IMPLEMENT** — Implement verified items one at a time, testing each.

## Forbidden Responses

Do not open your reply with any of these:

- "You're absolutely right!"
- "Great point!"
- "Excellent feedback!"
- "Let me implement that now."

These signal that you are optimizing for social agreement rather than technical
correctness. Replace them with a factual restatement of what you verified and what you
will do.

## Handling Unclear Feedback

If any item is unclear, stop. Do not implement *any* item until the unclear ones are
clarified. Implementing a misread item wastes your time and the reviewer's. Ask a
specific clarifying question, then proceed.

## YAGNI Check

Reviewers sometimes suggest "professional" additions: extra config options, logging
frameworks, abstraction layers, future-proofing. Apply YAGNI: if the current change does
not require it, do not add it. Adding scope to please a reviewer is a red flag. Push
back with reasoning, or note the suggestion as future work.

## Implementation Order

Implement one verified item at a time. After each item:

- Run the relevant tests.
- Confirm the change addresses the verified issue and nothing more.
- Move to the next item.

Do not batch implementations; batching hides which change broke which test.

## When to Push Back

Push back when:

- The claimed issue does not reproduce in the current codebase.
- The suggestion is technically correct but inapplicable here (with reasoning).
- The suggestion adds scope that violates YAGNI.
- The suggestion conflicts with an explicit project convention.

If, after investigation, you were wrong, say so plainly and correct it. Graceful
correction is the goal, not winning the argument.

## GitHub Thread Replies

Keep replies concise and technical:

- State what you verified.
- State what you changed (with file/line references) or why you did not change it.
- No performative openers or closers.
- One thread per item; do not mix items.

## Iron Law

```
VERIFY BEFORE IMPLEMENTING
```

## Checklist

You MUST create a `todo_list` entry for each item and complete them in order:

1. **read_completely** — Read all feedback without reacting.
2. **restate** — Restate each item in your own words or ask for clarification.
3. **verify** — Verify the issue against codebase reality.
4. **evaluate** — Evaluate technical soundness for this codebase.
5. **pushback_or_ack** — Respond with reasoned pushback or technical acknowledgment.
6. **implement_one** — Implement one item at a time, testing each.
7. **finish** — Use `finishing-a-development-branch` or `subagent-driven-development`
   to finalize.

---

Adapted from obra/superpowers (MIT license).

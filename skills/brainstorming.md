# Brainstorming Ideas Into Designs

## Overview

Help turn a user request into a fully formed design/spec through natural collaborative dialogue. This is the discovery half of workflow Step 1 (UNDERSTAND) — what happens *before* `requirement.md` is written and approved.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what is being built, present the design and get your human partner's approval before writing anything down.

**Announce at start:** `Using the brainstorming skill to refine <topic> before writing requirement.md.`

## The Iron Law

```
NO IMPLEMENTATION — AND NO WRITTEN REQUIREMENT OR PLAN —
UNTIL A DESIGN HAS BEEN PRESENTED AND YOUR HUMAN PARTNER HAS APPROVED IT.
```

This applies to EVERY project regardless of perceived simplicity. The design can be short (a few sentences for truly simple projects), but you MUST present it and get explicit approval before moving on.

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A config change, a single-function helper, a new workflow slash-command — all of them. "Simple" projects are where unexamined assumptions cause the most wasted work.

## When to Use

**Always use `brainstorming` when:**
- A new feature is being requested
- A new workflow, skill, or template is being authored
- A behaviour change in production code is being discussed
- A significant refactor is being proposed
- The user's request contains ambiguity about *what* is being built (as opposed to *how*)

**Skip `brainstorming` when:**
- You are in RCA mode — the deliverable is knowledge, not code
- You are executing an already-approved plan (use `executing-plans` or `subagent-driven-development`)
- Your human partner explicitly says "just fix it" for a well-specified bug with clear scope — but log the skip in the session retrospective

## Process Flow

```
Explore project context
    │
    ▼
Ask clarifying questions (one at a time)
    │
    ▼
Propose 2-3 approaches with trade-offs
    │
    ▼
Present design sections
    │
    ▼
User approves design? ── no ──▶ revise ──▶ (back to Present design)
    │ yes
    ▼
Write requirement.md / spec
    │
    ▼
Spec self-review (fix inline)
    │
    ▼
User reviews written spec? ── changes ──▶ (back to Write spec)
    │ approved
    ▼
Invoke writing-plans skill
```

**The terminal state is invoking `writing-plans`.** Do NOT jump to `subagent-driven-development` or start editing code. The only skill to invoke after `brainstorming` is `writing-plans`.

## The Process

**Understanding the idea:**

- Check the current project state first — files in the affected area, recent commits, any existing documentation
- Before drilling into details, assess scope: if the request describes multiple independent subsystems, flag this immediately
- For appropriately-scoped projects, ask questions one at a time to refine the idea
- Prefer multiple-choice questions when possible, but open-ended is fine too
- **Only one question per message** — if a topic needs more exploration, break it into multiple messages
- Focus on understanding: purpose, constraints, success criteria — not yet on implementation

**Exploring approaches:**

- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**Presenting the design:**

- Once you believe you understand what is being built, present the design
- Scale each section to its complexity: a few sentences if straightforward, up to 200-300 words if nuanced
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing strategy
- Be ready to go back and clarify if something doesn't make sense

**Design for isolation and clarity:**

- Break the system into smaller units that each have one clear purpose, communicate through well-defined interfaces, and can be understood and tested independently
- For each unit, you should be able to answer: what does it do, how do you use it, and what does it depend on?
- Smaller, well-bounded units are also easier to work with

**Working in existing codebases:**

- Explore the current structure before proposing changes. Follow existing patterns.
- Where existing code has problems that affect the work, include targeted improvements as part of the design
- Don't propose unrelated refactoring. Stay focused on what serves the current goal.

## After the Design

**Documentation:**

- Write the validated design (spec) to the appropriate location
- Commit the design document to git

**Spec Self-Review:**

After writing the spec, look at it with fresh eyes:

1. **Placeholder scan:** Any "TBD", "TODO", incomplete sections, or vague requirements? Fix them.
2. **Internal consistency:** Do any sections contradict each other?
3. **Scope check:** Is this focused enough for a single implementation plan, or does it need decomposition?
4. **Ambiguity check:** Could any requirement be interpreted two different ways?
5. **Cross-layer check:** Are all layers that this change touches enumerated?

Fix any issues inline. No need to re-review — just fix and move on.

**Your Human Partner Review Gate:**

After the self-review passes, present the written spec:

> *"Spec written and committed to `<path>`. Please review it and let me know if you want to make any changes before I move on to writing the implementation plan."*

Wait for the response. If changes requested, make them and re-run the self-review. Only proceed once your human partner approves.

**Implementation hand-off:**

- Invoke `writing-plans` to create the detailed implementation plan
- Do NOT invoke `subagent-driven-development` or any code-editing skill directly

## Key Principles

- **One question at a time** — don't overwhelm with multiple questions
- **Multiple choice preferred** — easier to answer than open-ended when possible
- **YAGNI ruthlessly** — remove unnecessary features from every design
- **Explore alternatives** — always propose 2-3 approaches before settling
- **Incremental validation** — present design, get approval section-by-section before writing the spec
- **Be flexible** — go back and clarify when something doesn't make sense
- **No preamble** — when your human partner asks a direct question, answer it

## Red Flags — STOP

- Writing `requirement.md` before presenting and getting approval on the design
- Jumping from "here's what I think we want" directly into `writing-plans` without the approval gate
- Asking a batch of 5 questions at once instead of one at a time
- Assuming the user has already thought about the design — they haven't, that's why they're asking you
- Skipping the scope check and launching into details on a sub-system of an over-broad request
- Presenting only one approach — "there's only one reasonable way" usually means you haven't thought about alternatives

## Relation to Workflows

- `brainstorming` is the discovery half of workflow Step 1 (UNDERSTAND) and precedes writing `requirement.md`
- For RCA mode, there is no `brainstorming` phase — the deliverable is knowledge
- The terminal state of this skill is invoking `writing-plans`, which produces the design document consumed by workflow Step 3 (DESIGN)

## Attribution

Portions adapted from [obra/superpowers](https://github.com/obra/superpowers), Copyright © 2025 Jesse Vincent, MIT License.

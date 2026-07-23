---
name: using-devin-orchestrator
description: "Use when starting any orchestrated conversation or task to decide whether a devin-orchestrator skill should be invoked before acting."
---

# Using devin-orchestrator Skills

This meta-skill governs how an agent in the devin-orchestrator harness decides what to do
*before* doing it. Its purpose is to make skill invocation the default first step of every
response, rather than an afterthought.

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific stage skill (for example,
`brainstorming`, `writing-plans`, or `test-driven-development`), follow that assigned
skill only. Do not invoke this meta-skill, and do not branch into other skills. The
orchestrator has already chosen the appropriate discipline for you; your job is to
execute it literally.
</SUBAGENT-STOP>

<EXTREMELY-IMPORTANT>
If a skill might apply to the current request, you MUST invoke it. This is not
negotiable, not optional, and not a matter of judgment. "Might apply" is a low bar —
when in doubt, invoke. The cost of an unnecessary invocation is small; the cost of
skipping a relevant discipline is large.
</EXTREMELY-IMPORTANT>

## The Rule

**Invoke relevant skills before any response or action.** "Before any response" includes:

- Answering clarifying questions
- Exploring the codebase
- Reading files
- Running commands
- Proposing approaches
- Writing code

Skill selection is the first action of every turn, not something you do after gathering
context. The discipline of checking for skills *first* is what makes the orchestrator
reliable.

## Skill Priority

When multiple skills could apply, process skills take precedence over implementation
skills:

1. **Process skills first** — `brainstorming`, `systematic-debugging`,
   `using-devin-orchestrator`, `writing-skills`. These shape *how* you will work.
2. **Implementation skills second** — `writing-plans`, `test-driven-development`,
   `subagent-driven-development`, `executing-plans`. These shape *what* you produce.

If a process skill applies, invoke it and let it direct you to the appropriate
implementation skill. Do not jump straight to an implementation skill because the task
"obviously" requires code.

## Red Flags

| Rationalizing thought | Reality |
|---|---|
| "This is just a simple question." | Simple questions still benefit from the right skill; check first. |
| "I need more context before I can pick a skill." | Skill selection *is* the first context-gathering step. |
| "The skill is overkill for this." | "Overkill" is a rationalization; if it might apply, invoke it. |
| "I'll check for skills after I look around." | Looking around is an action; skills come before actions. |
| "The user wants a quick answer." | Quick answers are still better when the right skill shapes them. |
| "I already know which skill to use." | Then announce it and follow its checklist literally. |

## Role Adaptation

**If you are the orchestrator** (the top-level agent in an orchestrated session):

- Consult `workflows/use-cases.yaml` to identify the use case type and its skill list.
- Scan `skills/` for any skill whose triggers match the request.
- Pick the most specific applicable skill. Prefer process skills first.
- Announce the selected skill, then follow its checklist via `todo_list`.

**If you are a dispatched subagent** (a fresh agent assigned one stage of a workflow):

- You were dispatched with a specific skill already chosen. Follow it.
- Do not invoke other skills, including this one.
- Do not re-evaluate skill selection; the orchestrator already did that.
- If the assigned skill's `terminal_state` names a next skill, that handoff is handled by
  the orchestrator, not by you.

## Announcement Protocol

Before following a selected skill, announce it using the skill's `announcement` field
(or a paraphrase). The announcement makes the discipline visible to the user and to
downstream logs. Skipping the announcement is a red flag.

## Checklist

You MUST create a `todo_list` entry for each item and complete them in order:

1. **identify_role** — Determine whether you are the orchestrator or a dispatched subagent.
2. **subagent_stop** — If you are a subagent executing a specific stage skill, follow that
   skill only and stop here.
3. **check_skills** — Check `skills/` and `workflows/use-cases.yaml` for applicable skills.
4. **announce_skill** — Announce the selected skill before following it.
5. **follow_checklist** — Create todos for the selected skill's checklist and follow them
   literally.

## Iron Law

```
INVOKE RELEVANT SKILLS BEFORE ANY RESPONSE OR ACTION
```

---

Adapted from obra/superpowers (MIT license).

---
name: brainstorming
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

**IMPORTANT:** Check the `interactive_mode` configuration flag before starting.

- **If interactive_mode is true:** Ask questions one at a time to refine the idea. Wait for user responses before proceeding.
- **If interactive_mode is false (default):** Make reasonable assumptions based on the request content and project context. Do NOT ask questions that require human input. Proceed autonomously to produce a design.

Start by understanding the current project context, then either ask questions (interactive) or make assumptions (non-interactive) to refine the idea. Once you understand what you're building, present the design.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design and the user has approved it. This applies to EVERY project regardless of perceived simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility, a config change — all of them. "Simple" projects are where unexamined assumptions cause the most wasted work. The design can be short (a few sentences for truly simple projects), but you MUST present it and get approval.

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** — check files, docs, recent commits
2. **Check interactive_mode configuration** — determine if you should ask questions or make assumptions
3. **If interactive_mode is true:** Ask clarifying questions — one at a time, understand purpose/constraints/success criteria
4. **If interactive_mode is false:** Make reasonable assumptions based on request content and project context
5. **Propose 2-3 approaches** — with trade-offs and your recommendation
6. **Present design** — in sections scaled to their complexity
7. **Optional: Adversarial review** — if enabled, conduct multi-perspective review before final approval
8. **Write design doc** — save to `design.md` (include adversarial review findings if conducted)
9. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope
10. **Note:** Human review happens via gate after brainstorming stage, not during skill execution

## The Process

1. **Explore project context**
   - Check existing files, documentation, recent commits
   - Understand the codebase structure and patterns
   - Identify relevant dependencies and constraints

2. **Determine interaction mode**
   - Check `interactive_mode` configuration
   - If true: Proceed with interactive question-asking
   - If false: Proceed with autonomous assumption-making

3. **If interactive_mode is true: Ask clarifying questions**
   - Ask one question at a time
   - Understand purpose, constraints, success criteria
   - Confirm understanding before proceeding

4. **If interactive_mode is false: Make reasonable assumptions**
   - Analyze request content for explicit requirements
   - Infer constraints from project context
   - Document assumptions in the design
   - Proceed without asking questions

5. **Propose 2-3 approaches**
   - Present multiple options with trade-offs
   - Provide your recommendation with rationale
   - In non-interactive mode: Select the best approach and proceed

6. **Present design in sections**
   - Break design into sections scaled to complexity
   - In interactive mode: Get user approval after each section
   - In non-interactive mode: Present complete design without waiting for approval

7. **Conditional: Adversarial review** (if policy is conditional and triggers met)
   - Check if adversarial review should be triggered based on policy
   - **Policy modes:**
     - `always`: Always trigger adversarial review
     - `never`: Never trigger adversarial review
     - `conditional`: Trigger only if complexity/risk thresholds met
   - **Complexity triggers:**
     - Design has > 10 sections
     - Design affects > 5 files
     - Design document > 500 lines
   - **Risk triggers:**
     - Design contains risk keywords (security, data_loss, breaking, performance, critical, production, deployment)
   - **User override:** Manual flag can force enable/disable regardless of policy
   - If triggered, invoke adversarial-review skill with the design proposal
   - Dispatch 4 personas: Advocate, Skeptic, Oracle, Contrarian
   - Synthesize results into structured verdict (allow/allow_with_conditions/deny)
   - Include top_risks, required_checks, missing_evidence in design document
   - Use adversarial review findings to inform final approval

8. **Write design document**
   - Save to `design.md`
   - Include all approved sections
   - Document decisions and trade-offs
   - Include adversarial review findings if conducted

9. **Spec self-review**
   - Check for placeholders
   - Check for contradictions
   - Check for ambiguity
   - Check scope boundaries

10. **Note:** Human review happens via gate after brainstorming stage, not during skill execution

## After the Design

Once the design is approved and saved to `design.md`, invoke the `writing-plans` skill to create the implementation plan. Do NOT invoke any other implementation skill directly.

## Key Principles

- **Design first, code second** — Never skip design regardless of perceived simplicity
- **Check interaction mode** — Respect `interactive_mode` configuration
- **Non-interactive mode** — Make reasonable assumptions, don't ask questions
- **Interactive mode** — Ask questions one at a time, don't assume
- **Multiple approaches** — Present options with trade-offs
- **Document everything** — Save design to `design.md`
- **Self-review** — Check your own spec for issues
- **Human review via gate** — Human review happens after brainstorming stage, not during skill execution

---
name: brainstorming
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design and get user approval.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design and the user has approved it. This applies to EVERY project regardless of perceived simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility, a config change — all of them. "Simple" projects are where unexamined assumptions cause the most wasted work. The design can be short (a few sentences for truly simple projects), but you MUST present it and get approval.

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** — check files, docs, recent commits
2. **Ask clarifying questions** — one at a time, understand purpose/constraints/success criteria
3. **Propose 2-3 approaches** — with trade-offs and your recommendation
4. **Present design** — in sections scaled to their complexity, get user approval after each section
5. **Optional: Adversarial review** — if enabled, conduct multi-perspective review before final approval
6. **Write design doc** — save to `design.md` (include adversarial review findings if conducted)
7. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope
8. **User reviews written spec** — ask user to review the spec file before proceeding
9. **Transition to implementation** — invoke writing-plans skill to create implementation plan

## The Process

1. **Explore project context**
   - Check existing files, documentation, recent commits
   - Understand the codebase structure and patterns
   - Identify relevant dependencies and constraints

2. **Ask clarifying questions**
   - Ask one question at a time
   - Understand purpose, constraints, success criteria
   - Confirm understanding before proceeding

3. **Propose 2-3 approaches**
   - Present multiple options with trade-offs
   - Provide your recommendation with rationale
   - Get user input on approach selection

4. **Present design in sections**
   - Break design into sections scaled to complexity
   - Get user approval after each section
   - Revise based on feedback

5. **Conditional: Adversarial review** (if policy is conditional and triggers met)
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

6. **Write design document**
   - Save to `design.md`
   - Include all approved sections
   - Document decisions and trade-offs
   - Include adversarial review findings if conducted

7. **Spec self-review**
   - Check for placeholders
   - Check for contradictions
   - Check for ambiguity
   - Check scope boundaries

8. **User review**
   - Ask user to review the spec file
   - Address any feedback
   - Get final approval

9. **Transition to implementation**
   - Invoke writing-plans skill
   - Do NOT invoke any other implementation skill

## After the Design

Once the design is approved and saved to `design.md`, invoke the `writing-plans` skill to create the implementation plan. Do NOT invoke any other implementation skill directly.

## Key Principles

- **Design first, code second** — Never skip design regardless of perceived simplicity
- **Collaborative dialogue** — Ask questions one at a time, don't assume
- **Multiple approaches** — Present options with trade-offs
- **Section approval** — Get approval for each design section
- **Document everything** — Save design to `design.md`
- **Self-review** — Check your own spec for issues
- **User review** — Get user to review the spec before proceeding

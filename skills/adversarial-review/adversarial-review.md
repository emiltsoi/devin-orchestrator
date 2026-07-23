---
name: adversarial-review
description: "Use when a proposal or design needs multi-perspective adversarial review before proceeding."
---

# Adversarial Review

Conduct adversarial multi-perspective review by dispatching 4 Devin workers with different persona prompts, then synthesize results into a structured verdict.

**Core principle:** Multiple perspectives must be synthesized into a structured verdict before proceeding.

**Announce at start:** "I'm using the adversarial-review skill to conduct multi-perspective review."

## When to Use

Use `adversarial-review` when one of the following triggers fires (mirrors `adversarial-review.yaml`):

- `proposal_review` — a proposal needs multi-perspective scrutiny before proceeding.
- `design_review` — a design decision carries enough risk or ambiguity to warrant adversarial synthesis.
- `risk_assessment` — a change requires structured identification of failure modes, missing evidence, and required checks before approval.

Dispatch one Advocate, Skeptic, Oracle, and Contrarian per proposal, then synthesize their outputs into a structured verdict (`allow` / `allow_with_conditions` / `deny`).

## Persona Prompts

### Advocate Persona

**Role:** Steel-man the proposal. Find the strongest arguments in favor.

**Prompt:**
```
You are the Advocate. Your role is to steel-man the proposal and find the strongest arguments in favor.

PROPOSAL: {proposal}

Your task:
1. Identify the strongest arguments supporting this proposal
2. Find evidence or reasoning that validates the approach
3. Highlight benefits and positive outcomes
4. Note any assumptions that, if true, strengthen the case

Output format:
- Strongest arguments: [list]
- Supporting evidence: [list]
- Benefits: [list]
- Key assumptions: [list]
```

### Skeptic Persona

**Role:** Find falsifiers and failure modes. Challenge assumptions.

**Prompt:**
```
You are the Skeptic. Your role is to find falsifiers and failure modes and challenge assumptions.

PROPOSAL: {proposal}

Your task:
1. Identify ways this proposal could fail
2. Find falsifying evidence or counterexamples
3. Challenge underlying assumptions
4. Identify edge cases and failure modes

Output format:
- Failure modes: [list]
- Falsifying evidence: [list]
- Challenged assumptions: [list]
- Edge cases: [list]
```

### Oracle Persona

**Role:** Base rates and empirical grounding. Historical context.

**Prompt:**
```
You are the Oracle. Your role is to provide base rates and empirical grounding from historical context.

PROPOSAL: {proposal}

Your task:
1. Provide historical context for similar approaches
2. Give base rates for success/failure
3. Cite empirical evidence or studies
4. Ground the proposal in established knowledge

Output format:
- Historical context: [summary]
- Base rates: [success/failure rates]
- Empirical evidence: [studies/data]
- Established knowledge: [relevant principles]
```

### Contrarian Persona

**Role:** Challenge the framing. Alternative perspectives.

**Prompt:**
```
You are the Contrarian. Your role is to challenge the framing and provide alternative perspectives.

PROPOSAL: {proposal}

Your task:
1. Challenge the problem framing
2. Propose alternative approaches
3. Question whether this is the right problem to solve
4. Suggest reframing or different priorities

Output format:
- Framing challenges: [list]
- Alternative approaches: [list]
- Problem reframing: [suggestions]
- Priority questions: [list]
```

## Multi-Dispatch Process

### Step 1: Dispatch All Personas

Dispatch 4 Devin workers in parallel (or sequentially if parallel not available).

The example below assumes the caller has already resolved `skills_dir` (the directory containing this skill), `session_dir` (the workspace to dispatch into), and `proposal` (the text under review). The `devin_cli_path` and `model` are pulled from `ConfigLoader` so the example is portable — set `DEVIN_CLI_PATH` / `DEVIN_DEFAULT_MODEL` in the environment or `config.yaml` rather than hardcoding them.

```python
from pathlib import Path

from config_loader import ConfigLoader
from skill_invoker import SkillInvoker

config = ConfigLoader.load()

# SkillInvoker(skills_dir, devin_cli_path, model, permission_mode, demo_mode)
# — see workflow-engine/skill_invoker.py. skills_dir is the directory that
# contains adversarial-review/ (and sibling skill subdirs).
skill_invoker = SkillInvoker(
    Path("skills"),
    devin_cli_path=config.devin_cli_path,  # from ${DEVIN_CLI_PATH} or config.yaml
    model=config.default_model,            # from ${DEVIN_DEFAULT_MODEL} or config.yaml
    permission_mode=config.default_permission_mode,
)

# Dispatch Advocate
advocate_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "advocate", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False,
)

# Dispatch Skeptic
skeptic_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "skeptic", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False,
)

# Dispatch Oracle
oracle_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "oracle", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False,
)

# Dispatch Contrarian
contrarian_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "contrarian", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False,
)
```

### Step 2: Synthesize Results

Arbiter synthesizes the 4 persona outputs into a structured verdict.

The following is an **illustrative pseudocode sketch** — not a runnable implementation — showing how persona outputs map onto the verdict schema (`top_risks`, `required_checks`, `missing_evidence`, `verified_sources`, `next_actions`). A real implementation parses each persona's structured output and projects the relevant fields into the verdict.

```python
def synthesize_verdict(advocate_result, skeptic_result, oracle_result, contrarian_result):
    """Pseudocode sketch — maps persona outputs onto the verdict schema.

    The verdict schema (see Step 3) is:
      verdict:            "allow" | "allow_with_conditions" | "deny"
      top_risks:          list[str]   # from Skeptic failure modes + Oracle base rates
      required_checks:    list[str]   # from Skeptic/Contrarian framing challenges
      missing_evidence:   list[str]   # from Oracle/Skeptic unverified claims
      verified_sources:   list[str]   # from Oracle empirical evidence
      next_actions:       list[str]   # from Contrarian alternatives + Advocate next steps
    """

    verdict = {
        "verdict": "allow",  # allow, allow_with_conditions, deny
        "top_risks": [],
        "required_checks": [],
        "missing_evidence": [],
        "verified_sources": [],
        "next_actions": [],
    }

    # Analyze Advocate output
    # Extract strongest arguments, supporting evidence
    # Analyze Skeptic output
    # Extract failure modes, falsifying evidence → top_risks
    # Analyze Oracle output
    # Extract empirical evidence → verified_sources
    # Extract base rates → risk assessment
    # Analyze Contrarian output
    # Extract framing challenges → required_checks
    # Extract alternative approaches → next_actions

    # Determine verdict based on synthesis
    # If critical failure modes → deny
    # If significant risks → allow_with_conditions
    # If minimal risks → allow

    return verdict
```

### Step 3: Generate Structured Verdict

Output the structured verdict:

```markdown
# Adversarial Review Verdict

## Verdict: {allow/allow_with_conditions/deny}

## Top Risks
- [List of top risks from Skeptic and Oracle]

## Required Checks
- [List of required checks from Skeptic and Contrarian]

## Missing Evidence
- [List of missing evidence from Oracle and Skeptic]

## Verified Sources
- [List of verified sources from Oracle]

## Next Actions
- [List of next actions from Contrarian and Advocate]

## Persona Summaries
### Advocate
- Strongest arguments: [...]
- Supporting evidence: [...]

### Skeptic
- Failure modes: [...]
- Falsifying evidence: [...]

### Oracle
- Historical context: [...]
- Base rates: [...]

### Contrarian
- Framing challenges: [...]
- Alternative approaches: [...]
```

## Verdict Criteria

**Allow:**
- Minimal risks identified
- Strong supporting evidence
- No critical failure modes
- Empirical grounding supports approach

**Allow with Conditions:**
- Moderate risks identified
- Some missing evidence
- Failure modes can be mitigated
- Requires additional checks or conditions

**Deny:**
- Critical failure modes identified
- Strong falsifying evidence
- Base rates indicate high failure probability
- Fundamental framing challenges

## Integration with Brainstorming

When adversarial review is enabled in brainstorming:

1. After design presentation, dispatch adversarial review
2. Use structured verdict as input to human gate
3. Include top_risks, required_checks, missing_evidence in design document
4. Human makes approval decision based on adversarial review

## Configuration

Enable adversarial review in brainstorming:

```yaml
brainstorming:
  use_adversarial_review: true
  adversarial_review_mode: standard  # fast, standard, deep
```

**Modes:**
- **fast:** Single pass through personas, quick synthesis
- **standard:** Full multi-dispatch, structured synthesis
- **deep:** Multi-dispatch with iterative refinement

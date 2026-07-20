---
name: adversarial-review
description: "Use when a proposal or design needs multi-perspective adversarial review before proceeding."
---

# Adversarial Review

Conduct adversarial multi-perspective review by dispatching 4 Devin workers with different persona prompts, then synthesize results into a structured verdict.

**Core principle:** Multiple perspectives must be synthesized into a structured verdict before proceeding.

**Announce at start:** "I'm using the adversarial-review skill to conduct multi-perspective review."

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

Dispatch 4 Devin workers in parallel (or sequentially if parallel not available):

```python
from skill_invoker import SkillInvoker

devin_cli_path = "C:\\Users\\<username>\\AppData\\Local\\devin\\cli\\bin\\devin.exe"
skill_invoker = SkillInvoker(harness_root, devin_cli_path=devin_cli_path, model="swe-1.6")

# Dispatch Advocate
advocate_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "advocate", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False
)

# Dispatch Skeptic
skeptic_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "skeptic", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False
)

# Dispatch Oracle
oracle_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "oracle", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False
)

# Dispatch Contrarian
contrarian_result = skill_invoker.invoke_skill(
    skill_name="adversarial-review",
    context={"persona": "contrarian", "proposal": proposal},
    workspace=str(session_dir),
    focused_context=[],
    is_reviewer=False
)
```

### Step 2: Synthesize Results

Arbiter synthesizes the 4 persona outputs into a structured verdict:

```python
def synthesize_verdict(advocate_result, skeptic_result, oracle_result, contrarian_result):
    """Synthesize persona outputs into structured verdict"""
    
    verdict = {
        "verdict": "allow",  # allow, allow_with_conditions, deny
        "top_risks": [],
        "required_checks": [],
        "missing_evidence": [],
        "verified_sources": [],
        "next_actions": []
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

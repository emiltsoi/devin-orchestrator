# Root Cause Analysis Workflow Runbook

**Source manifest:** `workflows/rca.manifest.yaml`
**Schema version:** 1
**Session shape:** rca

## 1. Overview

The root cause analysis workflow is an investigation-only workflow for analyzing incidents, bugs, or failures. It follows a structured sequence from gathering evidence through analysis, root cause identification, fix proposal, and verification. Key invariants:

- Every stage produces a persistent artifact that survives across sessions
- User gates (g1, g2) are hard stops requiring explicit approval
- All skill execution is performed by stateless Devin workers to preserve neutrality
- All artifact evaluation is performed by a separate neutral reviewer worker
- The reasoning train is preserved in artifacts, not volatile context
- **Canonical source deployment:** The canonical source of truth for workflow definitions is the `manifest.yaml` file. Runbooks are agent-facing companions that must maintain parity with the manifest. When deploying workflow changes, update the manifest first, then update the corresponding runbook to match.

## 2. Stage Sequence

### Stage 0: Gather Evidence

**Skill:** `systematic-debugging`
**Phase:** `step_0`
**Required artifacts (output):** [evidence.md]
**Gate:** `none`
**Injected context (worker dispatch):** [incident_report, logs]

#### Dispatch Protocol
1. Call deterministic tool: `session_init(session_id)` if first stage
2. Build focused dispatch context:
   - Load artifacts from: [incident_report, logs]
   - Include correction artifact if retry: `correction-step_0-{attempt}.md`
3. Dispatch to stateless Devin worker:
   - Skill: `systematic-debugging`
   - Context: incident_report, logs (focused only)
   - Output: evidence.md
4. Call deterministic tool: `validate_structural([evidence.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: evidence.md + acceptance criteria
   - Output: `review-step_0-{attempt}.md`
2. Cascade synthesizes verdict:
   - Reviewer verdict + deterministic floor result
   - Cross-step coherence check against prior artifacts
3. Assign confidence + rationale:
   - HIGH → proceed to next stage
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → proceed to correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (if any)
   - Analyze reviewer feedback
   - Analyze cross-step coherence issues
2. Persist correction artifact: `correction-step_0-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(stage, skill, injected_context, structural_result, reviewer_verdict, confidence, rationale, triage_decision, retry_count, gate_verdict)`
2. Write `run.jsonl` entry:
   ```json
   {
     "timestamp": "<ISO8601>",
     "session_id": "<session_id>",
     "stage": "step_0",
     "skill": "systematic-debugging",
     "injected_context": ["incident_report", "logs"],
     "structural_result": "PASS|FAIL",
     "reviewer_verdict": "PASS|FAIL|<details>",
     "confidence": "HIGH|MEDIUM|LOW",
     "rationale": "<Cascade reasoning>",
     "triage_decision": "proceed|correct|escalate",
     "retry_count": <N>,
     "gate_verdict": "none"
   }
   ```
3. Proceed to next stage

---

### Stage 1: Analyze Evidence

**Skill:** `systematic-debugging`
**Phase:** `step_1`
**Required artifacts (output):** [analysis.md]
**Gate:** `none`
**Injected context (worker dispatch):** [evidence.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [evidence.md]
   - Include correction artifact if retry: `correction-step_1-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `systematic-debugging`
   - Context: evidence.md (focused only)
   - Output: analysis.md
3. Call deterministic tool: `validate_structural([analysis.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: analysis.md + evidence.md
   - Output: `review-step_1-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does analysis.md identify potential causes from evidence?
   - Is it thorough and well-structured?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to next stage
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → proceed to correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (if any)
   - Analyze reviewer feedback
   - Analyze cross-step coherence issues
2. Persist correction artifact: `correction-step_1-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Proceed to next stage

---

### Stage 2: Identify Root Cause

**Skill:** `systematic-debugging`
**Phase:** `step_2`
**Required artifacts (output):** [root_cause.md]
**Gate:** `g1_root_cause_approval`
**Injected context (worker dispatch):** [analysis.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [analysis.md]
   - Include correction artifact if retry: `correction-step_2-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `systematic-debugging`
   - Context: analysis.md (focused only)
   - Output: root_cause.md
3. Call deterministic tool: `validate_structural([root_cause.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: root_cause.md + analysis.md
   - Output: `review-step_2-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does root_cause.md identify the root cause?
   - Is it well-supported by evidence and analysis?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to gate
   - MEDIUM → proceed to gate with logged caveat
   - LOW → proceed to correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (if any)
   - Analyze reviewer feedback
   - Analyze cross-step coherence issues
2. Persist correction artifact: `correction-step_2-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g1_root_cause_approval:
   - Surface summary: root_cause.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g1_root_cause_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g1_root_cause_approval, verdict)`
3. If approved → proceed to Stage 3
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Proceed to next stage

---

### Stage 3: Propose Fixes

**Skill:** `systematic-debugging`
**Phase:** `step_3`
**Required artifacts (output):** [fix_recommendations.md]
**Gate:** `none`
**Injected context (worker dispatch):** [root_cause.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [root_cause.md]
   - Include correction artifact if retry: `correction-step_3-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `systematic-debugging`
   - Context: root_cause.md (focused only)
   - Output: fix_recommendations.md
3. Call deterministic tool: `validate_structural([fix_recommendations.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: fix_recommendations.md + root_cause.md
   - Output: `review-step_3-{attempt}.md`
2. Cascade synthesizes verdict:
   - Do fix_recommendations.md address the root cause?
   - Are they comprehensive and actionable?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to next stage
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → proceed to correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (if any)
   - Analyze reviewer feedback
   - Analyze cross-step coherence issues
2. Persist correction artifact: `correction-step_3-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Proceed to next stage

---

### Stage 4: Verify Fixes

**Skill:** `verification-before-completion`
**Phase:** `step_4`
**Required artifacts (output):** [verification.md]
**Gate:** `g2_fix_approval`
**Injected context (worker dispatch):** [fix_recommendations.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [fix_recommendations.md]
   - Include correction artifact if retry: `correction-step_4-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `verification-before-completion`
   - Context: fix_recommendations.md (focused only)
   - Output: verification.md
3. Call deterministic tool: `validate_structural([verification.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: verification.md + fix_recommendations.md
   - Output: `review-step_4-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does verification.md confirm fixes address root cause?
   - Are verification steps comprehensive?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to gate
   - MEDIUM → proceed to gate with logged caveat
   - LOW → proceed to correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (if any)
   - Analyze reviewer feedback
   - Analyze cross-step coherence issues
2. Persist correction artifact: `correction-step_4-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g2_fix_approval:
   - Surface summary: verification.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g2_fix_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g2_fix_approval, verdict)`
3. If approved → workflow complete
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Workflow complete

---

## 3. Triage Protocol

Applied after every stage dispatch:

```
1. Validate structural floor (deterministic tool)
   └─ FAIL → correction loop (bounded) → still FAIL → ESCALATE

2. Dispatch neutral reviewer (always, separate worker)
   └─ Reviewer verdict persisted to `review-{stage}-{attempt}.md`

3. Cascade synthesizes verdict:
   - Does artifact satisfy acceptance criteria?
   - Does artifact cohere with prior artifacts (cross-step context)?
   - Reviewer verdict + floor result

4. Assign confidence + rationale:
   - HIGH   → proceed (all criteria met, no concerns)
   - MEDIUM → proceed with logged caveat (non-gated stages only)
   - LOW    → correction loop (bounded) → still FAIL → ESCALATE

5. If stage has user gate → HARD STOP, surface summary, await human

6. Record decision to audit ledger + run.jsonl before advancing
```

**Confidence guidelines:**
- **HIGH:** All acceptance criteria met; reviewer passes; structural floor passes; cross-step coherence verified; no concerns.
- **MEDIUM:** Acceptance criteria met but with minor concerns; reviewer passes with caveats; structural floor passes; cross-step coherence acceptable. Proceed with logged caveat.
- **LOW:** Acceptance criteria not met; reviewer fails; structural floor fails; cross-step coherence broken; major concerns. Do not proceed — correct or escalate.

---

## 4. Escalation Policy

When to stop and ask the human:

1. **Structural floor FAIL after bounded retries** (max 3 attempts per stage)
   - Cannot proceed without meeting objective floor
   - ESCALATE to human for guidance

2. **Confidence LOW after bounded retries** (max 3 attempts per stage)
   - Cascade cannot reason to a satisfactory outcome
   - ESCALATE to human for guidance

3. **User gate rejection** (g1, g2)
   - Human explicitly rejects the artifact
   - ESCALATE to human for correction direction

4. **Tiered model escalation** (later phase):
   - If producer + reviewer fail > 1 attempt on the same stage
   - Escalate to higher-quality model (claude-code) as third independent worker
   - If tiered escalation also fails → ESCALATE to human

**Escalation format:**
```markdown
### ESCALATION: Stage N (<Stage Name>)

**Reason:** <why escalation is required>
**Attempts:** <N> dispatches performed
**Last structural result:** <PASS|FAIL>
**Last reviewer verdict:** <details>
**Last confidence:** <HIGH|MEDIUM|LOW>
**Last rationale:** <Cascade reasoning>

**Recommendation:** <what the human should do>

Awaiting human guidance...
```

---

## 5. Deterministic Tool Calls

When the harness is consumed through the MCP server, the orchestrator invokes these operations as MCP tools such as `run_workflow`, `dispatch_skill`, `dispatch_devin`, `gate_decision`, and `continue_workflow`. The server internally runs `session_init`, `validate_structural`, `record_gate`, `append_audit`, and `write_run_jsonl`.

Cascade must call these deterministic tools at specific points to ensure reproducibility and auditability:

| Tool | When to Call | Purpose |
|------|--------------|---------|
| `session_init(session_id)` | First stage only | Scaffolds workdir, creates initial artifacts (request.md, status.md, session-audit.md) |
| `validate_structural(artifacts)` | After every worker dispatch | Checks existence, non-emptiness, no placeholders, Iron-Law rules |
| `record_gate(gate_id, verdict)` | After every user gate decision | Records gate verdict to audit ledger |
| `append_audit(...)` | After every stage decision | Appends structured entry to session-audit.md |
| `write_run_jsonl(entry)` | After every stage decision | Appends machine-readable entry to run.jsonl for resumability |

**Tool signatures (for reference):**
```python
# session_init(session_id)
# Creates: work/<session_id>/request.md, status.md, session-audit.md
# Returns: workdir path

# validate_structural(artifacts)
# Input: list of artifact paths
# Returns: { "result": "PASS|FAIL", "failures": [...] }

# record_gate(gate_id, verdict)
# Input: gate_id (str), verdict (str: "approved"|"rejected")
# Appends to: session-audit.md

# append_audit(stage, skill, injected_context, structural_result, reviewer_verdict, confidence, rationale, triage_decision, retry_count, gate_verdict)
# Appends to: session-audit.md

# write_run_jsonl(entry)
# Input: dict with keys: timestamp, session_id, stage, skill, injected_context, structural_result, reviewer_verdict, confidence, rationale, triage_decision, retry_count, gate_verdict
# Appends to: run.jsonl
```

---

## 6. Per-Skill Context Manifest

Each skill declares exactly which artifacts are injected into its worker dispatch. This preserves worker neutrality by limiting context to only what's needed.

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| systematic-debugging | [stage-specific artifacts] |
| verification-before-completion | [fix_recommendations.md] |

**Correction-loop augmentation:**
- On retry (attempt > 1), injected context becomes: `[original_context, previous_output, correction-{stage}-{attempt-1}.md]`
- This ensures the worker sees what it produced before and why it needs correction

---

## 7. Resumability Protocol

A fresh Cascade session can resume from a previous session using:

1. **Load `run.jsonl`** to reconstruct state:
   - Parse last completed stage
   - Load retry counts, gate verdicts, confidence history

2. **Load present artifacts** to reconstruct reasoning train:
   - All produced artifacts (evidence.md, analysis.md, root_cause.md, fix_recommendations.md, verification.md)
   - All correction artifacts (correction-{stage}-{attempt}.md)
   - All review artifacts (review-{stage}-{attempt}.md)
   - All gate decision artifacts (gate-{gate_id}.md)

3. **Resume from last completed stage:**
   - If last stage completed with confidence HIGH/MEDIUM and gate approved → proceed to next stage
   - If last stage in correction loop → resume correction loop with remaining retries
   - If last stage at gate awaiting human → re-surface gate summary

4. **Cross-check against manifest:**
   - Verify current stage matches manifest phase sequence
   - Verify required artifacts exist (structural floor)
   - If mismatch → ESCALATE to human (corrupted state)

**Resumability invariant:** The combination of `run.jsonl` + present artifacts must be sufficient to reconstruct the complete reasoning train and continue execution without relying on volatile context.

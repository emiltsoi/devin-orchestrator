# Pull Request Review Workflow Runbook

**Source manifest:** `workflows/pr_review.manifest.yaml`
**Schema version:** 1
**Session shape:** pr_review

## 1. Overview

The pull request review workflow is a review-only workflow for evaluating pull requests. It follows a structured sequence from fetching PR details through spec compliance review, code quality review, and final approval decision. Key invariants:

- Every stage produces a persistent artifact that survives across sessions
- User gate (g1) is a hard stop requiring explicit approval
- All skill execution is performed by stateless Devin workers to preserve neutrality
- All artifact evaluation is performed by a separate neutral reviewer worker
- The reasoning train is preserved in artifacts, not volatile context
- **Canonical source deployment:** The canonical source of truth for workflow definitions is the `manifest.yaml` file. Runbooks are agent-facing companions that must maintain parity with the manifest. When deploying workflow changes, update the manifest first, then update the corresponding runbook to match.

## 2. Stage Sequence

### Stage 0: Fetch PR

**Skill:** `requesting-code-review`
**Phase:** `step_0`
**Required artifacts (output):** [pr_details.md, diff.md]
**Gate:** `none`
**Injected context (worker dispatch):** [pr_url]

#### Dispatch Protocol
1. Call deterministic tool: `session_init(session_id)` if first stage
2. Build focused dispatch context:
   - Load artifacts from: [pr_url]
   - Include correction artifact if retry: `correction-step_0-{attempt}.md`
3. Dispatch to stateless Devin worker:
   - Skill: `requesting-code-review`
   - Context: pr_url (focused only)
   - Output: pr_details.md, diff.md
4. Call deterministic tool: `validate_structural([pr_details.md, diff.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: pr_details.md, diff.md + acceptance criteria
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
     "skill": "requesting-code-review",
     "injected_context": ["pr_url"],
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

### Stage 1: Review Spec Compliance

**Skill:** `requesting-code-review`
**Phase:** `step_1`
**Required artifacts (output):** [spec_review.md]
**Gate:** `none`
**Injected context (worker dispatch):** [pr_details.md, diff.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [pr_details.md, diff.md]
   - Include correction artifact if retry: `correction-step_1-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `requesting-code-review`
   - Context: pr_details.md, diff.md (focused only)
   - Output: spec_review.md
3. Call deterministic tool: `validate_structural([spec_review.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: spec_review.md + pr_details.md + diff.md
   - Output: `review-step_1-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does spec_review.md capture compliance with PR requirements?
   - Is it clear, complete, and actionable?
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

### Stage 2: Review Code Quality

**Skill:** `swe-compliance`
**Phase:** `step_2`
**Required artifacts (output):** [quality_review.md]
**Gate:** `none`
**Injected context (worker dispatch):** [diff.md, spec_review.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [diff.md, spec_review.md]
   - Include correction artifact if retry: `correction-step_2-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `swe-compliance`
   - Context: diff.md, spec_review.md (focused only)
   - Output: quality_review.md
3. Call deterministic tool: `validate_structural([quality_review.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: quality_review.md + diff.md + spec_review.md
   - Output: `review-step_2-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does quality_review.md capture code quality issues?
   - Is it comprehensive and well-structured?
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
2. Persist correction artifact: `correction-step_2-{attempt}.md`
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

### Stage 3: Compile Findings

**Skill:** `requesting-code-review`
**Phase:** `step_3`
**Required artifacts (output):** [review_findings.md]
**Gate:** `g1_approval_decision`
**Injected context (worker dispatch):** [spec_review.md, quality_review.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [spec_review.md, quality_review.md]
   - Include correction artifact if retry: `correction-step_3-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `requesting-code-review`
   - Context: spec_review.md, quality_review.md (focused only)
   - Output: review_findings.md
3. Call deterministic tool: `validate_structural([review_findings.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: review_findings.md + spec_review.md + quality_review.md
   - Output: `review-step_3-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does review_findings.md compile findings by severity?
   - Is it clear, complete, and actionable?
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
2. Persist correction artifact: `correction-step_3-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g1_approval_decision:
   - Surface summary: review_findings.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g1_approval_decision.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g1_approval_decision, verdict)`
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

3. **User gate rejection** (g1)
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
| `verify_compliance_block(block_verdict, file_path)` | After reviewer BLOCK verdict | Independently verifies compliance reviewer BLOCK verdicts (hallucination guard) |

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

# verify_compliance_block(block_verdict, file_path)
# Input: block_verdict (str), file_path (Path)
# Returns: { "verified": bool, "notes": list[str] }
# Purpose: Independently verify compliance reviewer BLOCK verdicts (hallucination guard)
# Note: Compliance reviewers hallucinate ~70% of syntax claims on async code
```

---

## 6. Per-Skill Context Manifest

Each skill declares exactly which artifacts are injected into its worker dispatch. This preserves worker neutrality by limiting context to only what's needed.

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| requesting-code-review | [stage-specific artifacts] |
| swe-compliance | [diff.md, spec_review.md] |

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
   - All produced artifacts (pr_details.md, diff.md, spec_review.md, quality_review.md, review_findings.md)
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

# Superpower Workflow Runbook

**Source manifest:** `workflows/superpower.manifest.yaml`
**Schema version:** 1
**Session shape:** superpower

## 1. Overview

The superpower workflow is a complete software development methodology for coding agents. It follows a structured sequence from brainstorming through worktree setup, planning, implementation, testing, code review, and completion. Key invariants:

- Every stage produces a persistent artifact that survives across sessions
- User gates (g1, g2, g3, g4) are hard stops requiring explicit approval
- Brainstorming stage is optional (skip_brainstorming flag)
- All skill execution is performed by stateless Devin workers to preserve neutrality
- All artifact evaluation is performed by a separate neutral reviewer worker
- The reasoning train is preserved in artifacts, not volatile context
- **Canonical source deployment:** The canonical source of truth for workflow definitions is the `manifest.yaml` file. Runbooks are agent-facing companions that must maintain parity with the manifest. When deploying workflow changes, update the manifest first, then update the corresponding runbook to match.

## 2. Stage Sequence

### Stage 0: Brainstorming (Optional)

**Skill:** `brainstorming`
**Phase:** `step_0`
**Required artifacts (output):** [design.md]
**Gate:** `none`
**Injected context (worker dispatch):** []
**Optional:** true (skip if skip_brainstorming is true)

#### Dispatch Protocol
1. Check skip_brainstorming flag:
   - If true → skip to Stage 1
   - If false → proceed with dispatch
2. Call deterministic tool: `session_init(session_id)` if first stage
3. Build focused dispatch context:
   - Load artifacts from: [] (user request provided directly)
   - Include correction artifact if retry: `correction-step_0-{attempt}.md`
4. Dispatch to stateless Devin worker:
   - Skill: `brainstorming`
   - Context: user request (focused only)
   - Output: design.md
5. Call deterministic tool: `validate_structural([design.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: design.md + acceptance criteria
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
     "skill": "brainstorming",
     "injected_context": [],
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

### Stage 1: Using Git Worktrees

**Skill:** `using-git-worktrees`
**Phase:** `step_1`
**Required artifacts (output):** [worktree-info.md, baseline-test-results.md]
**Gate:** `g1_design_approval`
**Injected context (worker dispatch):** [design.md]

#### Dispatch Protocol
1. Call deterministic tool: `session_init(session_id)` if first stage (if brainstorming skipped)
2. Build focused dispatch context:
   - Load artifacts from: [design.md]
   - Include correction artifact if retry: `correction-step_1-{attempt}.md`
3. Dispatch to stateless Devin worker:
   - Skill: `using-git-worktrees`
   - Context: design.md (focused only)
   - Output: worktree-info.md, baseline-test-results.md
4. Call deterministic tool: `validate_structural([worktree-info.md, baseline-test-results.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: worktree-info.md, baseline-test-results.md + design.md
   - Output: `review-step_1-{attempt}.md`
2. Cascade synthesizes verdict:
   - Was worktree created successfully?
   - Are baseline tests passing?
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
2. Persist correction artifact: `correction-step_1-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g1_design_approval:
   - Surface summary: worktree-info.md, baseline-test-results.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g1_design_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g1_design_approval, verdict)`
3. If approved → proceed to Stage 2
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Proceed to next stage

---

### Stage 2: Writing Plans

**Skill:** `writing-plans`
**Phase:** `step_2`
**Required artifacts (output):** [plan.md]
**Gate:** `none`
**Injected context (worker dispatch):** [design.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [design.md]
   - Include correction artifact if retry: `correction-step_2-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `writing-plans`
   - Context: design.md (focused only)
   - Output: plan.md
3. Call deterministic tool: `validate_structural([plan.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: plan.md + design.md
   - Output: `review-step_2-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does plan.md break work into bite-sized tasks?
   - Are tasks specific with exact file paths and verification steps?
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

### Stage 3: Subagent-Driven Development

**Skill:** `subagent-driven-development`
**Phase:** `step_3`
**Required artifacts (output):** [implementation.md, task-results.md]
**Gate:** `g2_plan_approval`
**Injected context (worker dispatch):** [plan.md, design.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [plan.md, design.md]
   - Include correction artifact if retry: `correction-step_3-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `subagent-driven-development`
   - Context: plan.md, design.md (focused only)
   - Output: implementation.md, task-results.md
3. Call deterministic tool: `validate_structural([implementation.md, task-results.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: implementation.md, task-results.md + plan.md + design.md
   - Output: `review-step_3-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does implementation.md follow the plan?
   - Are all tasks completed with two-stage review?
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
1. HARD STOP at g2_plan_approval:
   - Surface summary: implementation.md, task-results.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g2_plan_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g2_plan_approval, verdict)`
3. If approved → proceed to Stage 4
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Proceed to next stage

---

### Stage 4: Test-Driven Development

**Skill:** `test-driven-development`
**Phase:** `step_4`
**Required artifacts (output):** [test-results.md, implementation-final.md]
**Gate:** `none`
**Injected context (worker dispatch):** [implementation.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [implementation.md]
   - Include correction artifact if retry: `correction-step_4-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `test-driven-development`
   - Context: implementation.md (focused only)
   - Output: test-results.md, implementation-final.md
3. Call deterministic tool: `validate_structural([test-results.md, implementation-final.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: test-results.md, implementation-final.md + implementation.md
   - Output: `review-step_4-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does test-results.md show RED-GREEN-REFACTOR cycle?
   - Are all tests passing?
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
2. Persist correction artifact: `correction-step_4-{attempt}.md`
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

### Stage 5: Requesting Code Review

**Skill:** `requesting-code-review`
**Phase:** `step_5`
**Required artifacts (output):** [review-findings.md]
**Gate:** `g3_review_approval`
**Injected context (worker dispatch):** [plan.md, implementation-final.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [plan.md, implementation-final.md]
   - Include correction artifact if retry: `correction-step_5-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `requesting-code-review`
   - Context: plan.md, implementation-final.md (focused only)
   - Output: review-findings.md
3. Call deterministic tool: `validate_structural([review-findings.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: review-findings.md + plan.md + implementation-final.md
   - Output: `review-step_5-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does review-findings.md report issues by severity?
   - Are critical issues blocking progress?
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
2. Persist correction artifact: `correction-step_5-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g3_review_approval:
   - Surface summary: review-findings.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g3_review_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g3_review_approval, verdict)`
3. If approved → proceed to Stage 6
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Proceed to next stage

---

### Stage 6: Finishing a Development Branch

**Skill:** `finishing-a-development-branch`
**Phase:** `step_6`
**Required artifacts (output):** [completion-summary.md, merge-decision.md]
**Gate:** `g4_completion_approval`
**Injected context (worker dispatch):** [test-results.md, review-findings.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load artifacts from: [test-results.md, review-findings.md]
   - Include correction artifact if retry: `correction-step_6-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `finishing-a-development-branch`
   - Context: test-results.md, review-findings.md (focused only)
   - Output: completion-summary.md, merge-decision.md
3. Call deterministic tool: `validate_structural([completion-summary.md, merge-decision.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: completion-summary.md, merge-decision.md + test-results.md + review-findings.md
   - Output: `review-step_6-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does completion-summary.md present options (merge/PR/keep/discard)?
   - Is worktree cleanup documented?
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
2. Persist correction artifact: `correction-step_6-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g4_completion_approval:
   - Surface summary: completion-summary.md, merge-decision.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g4_completion_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g4_completion_approval, verdict)`
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

3. **User gate rejection** (g1, g2, g3, g4)
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

Cascade must call these deterministic tools at specific points to ensure reproducibility and auditability:

| Tool | When to Call | Purpose |
|------|--------------|---------|
| `session_init(session_id)` | First stage only | Scaffolds workdir, creates initial artifacts (request.md, status.md, session-audit.md) |
| `validate_structural(artifacts)` | After every worker dispatch | Checks existence, non-emptiness, no placeholders, Iron-Law rules |
| `record_gate(gate_id, verdict)` | After every user gate decision | Records gate verdict to audit ledger |
| `append_audit(...)` | After every stage decision | Appends structured entry to session-audit.md |
| `write_run_jsonl(entry)` | After every stage decision | Appends machine-readable entry to run.jsonl for resumability |
| `git_ops(branch, commit_message)` | After gated stages (optional) | Commits to implementation branch if policy requires |
| `verify_compliance_block(block_verdict, file_path)` | After reviewer BLOCK verdict | Independently verifies compliance reviewer BLOCK verdicts (hallucination guard) |
| `check_leaf_module_boundary(target_module, workspace)` | Before coder dispatch | Verifies target module respects leaf module boundary (coupling ≤2) |

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

# git_ops(branch, commit_message)
# Input: branch (str), commit_message (str)
# Performs: git checkout -b <branch>, git add, git commit

# verify_compliance_block(block_verdict, file_path)
# Input: block_verdict (str), file_path (Path)
# Returns: { "verified": bool, "notes": list[str] }
# Purpose: Independently verify compliance reviewer BLOCK verdicts (hallucination guard)
# Note: Compliance reviewers hallucinate ~70% of syntax claims on async code

# check_leaf_module_boundary(target_module, workspace)
# Input: target_module (Path), workspace (Path)
# Returns: { "is_leaf": bool, "coupling_count": int }
# Purpose: Verify target module respects leaf module boundary (coupling ≤2)
# Note: SWE-1.6 excels at leaf modules but lacks reasoning depth for cross-cutting work
```

---

## 6. Per-Skill Context Manifest

Each skill declares exactly which artifacts are injected into its worker dispatch. This preserves worker neutrality by limiting context to only what's needed.

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| brainstorming | [] (user request provided directly) |
| using-git-worktrees | [design.md] |
| writing-plans | [design.md] |
| subagent-driven-development | [plan.md, design.md] |
| test-driven-development | [implementation.md] |
| requesting-code-review | [plan.md, implementation-final.md] |
| finishing-a-development-branch | [test-results.md, review-findings.md] |

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
   - All produced artifacts (design.md, worktree-info.md, baseline-test-results.md, plan.md, implementation.md, task-results.md, test-results.md, implementation-final.md, review-findings.md, completion-summary.md, merge-decision.md)
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

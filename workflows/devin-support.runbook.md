# Devin Support Workflow Runbook

> **DEPRECATED** — `devin-support` is a legacy one-stage wrapper around `orchestrate-superpower`. The `orchestrate-superpower` skill now routes to `mcp0_run_workflow('superpower')`, so you should call `mcp0_run_workflow('superpower')` directly for end-to-end superpower automation.

**Source manifest:** `workflows/devin-support.manifest.yaml`
**Schema version:** 1
**Session shape:** devin-support

## 1. Overview

This runbook is retained for reference only. The preferred way to run the superpower workflow is `mcp0_run_workflow` with `workflow: "superpower"`. The engine runs all 7 stages, handles gates, and returns structured results. Only use per-stage dispatch when a `resume` ticket explicitly requires a manual stage dispatch.

- `mcp0_run_workflow('superpower')` is the canonical path
- No persistent artifacts are produced by `devin-support` itself (all outputs come from the superpower workflow)
- No gates are present on the wrapper stage (superpower workflow gates are handled by the engine)
- **Canonical source deployment:** The canonical source of truth for workflow definitions is the `manifest.yaml` file. Runbooks are agent-facing companions that must maintain parity with the manifest. When deploying workflow changes, update the manifest first, then update the corresponding runbook to match.

## 2. Stage Sequence

### Stage 0: Orchestrate Superpower

**Skill:** `orchestrate-superpower`
**Phase:** `step_0`
**Required artifacts (output):** []
**Gate:** `none`
**Injected context (worker dispatch):** []

#### Dispatch Protocol
1. Call deterministic tool: `session_init(session_id)` if first stage
2. Build focused dispatch context:
   - No artifacts to load (empty context)
   - Include correction artifact if retry: `correction-step_0-{attempt}.md`
3. Dispatch to stateless Devin worker:
   - Skill: `orchestrate-superpower`
   - Context: empty (focused only)
   - Output: none (delegates to superpower workflow)
4. Call deterministic tool: `validate_structural([])`
   - No artifacts to validate → auto-PASS
   - Proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: orchestration result + acceptance criteria
   - Output: `review-step_0-{attempt}.md`
2. Cascade synthesizes verdict:
   - Did orchestrate-superpower successfully delegate to superpower workflow?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → workflow complete
   - MEDIUM → workflow complete with logged caveat
   - LOW → proceed to correction loop

#### Correction Loop (if confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze reviewer feedback
   - Analyze orchestration failures
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
     "skill": "orchestrate-superpower",
     "injected_context": [],
     "structural_result": "PASS",
     "reviewer_verdict": "PASS|FAIL|<details>",
     "confidence": "HIGH|MEDIUM|LOW",
     "rationale": "<Cascade reasoning>",
     "triage_decision": "proceed|correct|escalate",
     "retry_count": <N>,
     "gate_verdict": "none"
   }
   ```
3. Workflow complete

---

## 3. Triage Protocol

Applied after every stage dispatch:

```
1. Validate structural floor (deterministic tool)
   └─ No artifacts to validate → auto-PASS

2. Dispatch neutral reviewer (always, separate worker)
   └─ Reviewer verdict persisted to `review-{stage}-{attempt}.md`

3. Cascade synthesizes verdict:
   - Did orchestrate-superpower successfully delegate?
   - Reviewer verdict + floor result

4. Assign confidence + rationale:
   - HIGH   → proceed (successful delegation)
   - MEDIUM → proceed with logged caveat (delegation with concerns)
   - LOW    → correction loop (bounded) → still FAIL → ESCALATE

5. No user gates → auto-proceed on HIGH/MEDIUM, correct on LOW

6. Record decision to audit ledger + run.jsonl before advancing
```

**Confidence guidelines:**
- **HIGH:** Orchestrate-superpower successfully delegated to superpower workflow; reviewer passes; no concerns.
- **MEDIUM:** Orchestrate-superpower delegated but with minor concerns; reviewer passes with caveats. Proceed with logged caveat.
- **LOW:** Orchestrate-superpower failed to delegate; reviewer fails; major concerns. Do not proceed — correct or escalate.

---

## 4. Escalation Policy

When to stop and ask the human:

1. **Confidence LOW after bounded retries** (max 3 attempts per stage)
   - Cascade cannot reason to a satisfactory outcome
   - ESCALATE to human for guidance

2. **Tiered model escalation** (later phase):
   - If producer + reviewer fail > 1 attempt on the same stage
   - Escalate to higher-quality model (claude-code) as third independent worker
   - If tiered escalation also fails → ESCALATE to human

**Escalation format:**
```markdown
### ESCALATION: Stage 0 (Orchestrate Superpower)

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
| orchestrate-superpower | [] (empty context) |

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
   - All correction artifacts (correction-{stage}-{attempt}.md)
   - All review artifacts (review-{stage}-{attempt}.md)

3. **Resume from last completed stage:**
   - If last stage completed with confidence HIGH/MEDIUM → workflow complete
   - If last stage in correction loop → resume correction loop with remaining retries

4. **Cross-check against manifest:**
   - Verify current stage matches manifest phase sequence
   - If mismatch → ESCALATE to human (corrupted state)

**Resumability invariant:** The combination of `run.jsonl` + present artifacts must be sufficient to reconstruct the complete reasoning train and continue execution without relying on volatile context.

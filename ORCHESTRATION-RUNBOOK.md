# ORCHESTRATION-RUNBOOK.md Format Specification

**Purpose:** Agent-facing companion to `manifest.yaml` that Cascade follows to orchestrate a workflow. Written for Cascade to read and follow literally — not parsed by scripts.

**Relationship to manifest.yaml:** The runbook and manifest are dual sources of truth that must agree:
- `manifest.yaml` = structured, machine-readable source (stages, artifacts, gates, skill mappings)
- `*.runbook.md` = agent-facing, prose-encoded orchestration protocol (triage, escalation, tool calls)

**Discipline:** Same as skill `.yaml` vs `.md` — parity must be maintained; changes to one require updates to the other.

---

## 1. Runbook Structure

A runbook is a markdown document with the following sections:

```markdown
# <Workflow Name> Runbook

**Source manifest:** `workflows/<workflow>.manifest.yaml`
**Schema version:** <matches manifest schema_version>
**Session shape:** <matches manifest session_shape>

## 1. Overview
[Prose description of the workflow, its purpose, and key invariants]

## 2. Stage Sequence
[Ordered list of stages, each with skill, artifacts, gate, and triage protocol]

## 3. Triage Protocol
[General triage rules applied after each stage]

## 4. Escalation Policy
[When to stop and ask the human]

## 5. Deterministic Tool Calls
[Which tools to call and when]

## 6. Per-Skill Context Manifest
[Which artifacts each worker dispatch receives]

## 7. Resumability Protocol
[How to resume from a previous session]
```

---

## 2. Stage Sequence Format

Each stage is encoded as a markdown section with the following structure:

```markdown
### Stage N: <Stage Name>

**Skill:** `<skill_name>` (from manifest skills list)
**Phase:** `step_N` (from manifest phases)
**Required artifacts (output):** [list from manifest required_artifacts]
**Gate:** `<gate_id>` or `none` (from manifest gates)
**Injected context (worker dispatch):** [list from per-skill context manifest]

#### Dispatch Protocol
1. Call deterministic tool: `session_init(session_id)` if first stage
2. Build focused dispatch context:
   - Load artifacts from: [injected context list]
   - Include correction artifact if retry: `correction-{stage}-{attempt}.md`
3. Dispatch to stateless Devin worker:
   - Skill: `<skill_name>`
   - Context: focused context only (not Cascade's full context)
   - Output: worker produces required artifacts
4. Call deterministic tool: `validate_structural(required_artifacts)`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker (always):
   - Model: `swe-1-6` (free)
   - Context: produced artifacts + acceptance criteria
   - Output: `review-{stage}-{attempt}.md`
2. Cascade synthesizes verdict:
   - Reviewer verdict + deterministic floor result
   - Cross-step coherence check against prior artifacts
3. Assign confidence + rationale:
   - HIGH → proceed to next stage or gate
   - MEDIUM → proceed with logged caveat (non-gated stages only)
   - LOW → proceed to correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (if any)
   - Analyze reviewer feedback
   - Analyze cross-step coherence issues
2. Persist correction artifact: `correction-{stage}-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous output + correction artifact
4. Bounded retries: max 3 attempts per stage
5. If still FAIL after retries → ESCALATE to human

#### Gate Protocol (if gate defined)
1. If gate is `g1_requirement_approval`, `g2_design_approval`, or `g3_final_approval`:
   - HARD STOP: surface summary + recommendation
   - Persist decision artifact: `gate-{gate_id}.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(gate_id, verdict)`
3. If approved → proceed to next stage
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(stage, skill, injected_context, structural_result, reviewer_verdict, confidence, rationale, triage_decision, retry_count, gate_verdict)`
2. Write `run.jsonl` entry:
   ```json
   {
     "timestamp": "<ISO8601>",
     "session_id": "<session_id>",
     "stage": "step_N",
     "skill": "<skill_name>",
     "injected_context": ["<artifact1>", "<artifact2>"],
     "structural_result": "PASS|FAIL",
     "reviewer_verdict": "PASS|FAIL|<details>",
     "confidence": "HIGH|MEDIUM|LOW",
     "rationale": "<Cascade reasoning>",
     "triage_decision": "proceed|correct|escalate",
     "retry_count": <N>,
     "gate_verdict": "approved|rejected|none"
   }
   ```
3. Proceed to next stage or await human
```

---

## 3. Triage Protocol (General Rules)

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

3. **User gate rejection** (g1/g2/g3)
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

## 6. Devin Dispatch Protocol

Cascade dispatches to SWE-1.6 (free tier) via Devin CLI with specific guardrails based on learned behavior:

### Skill Loading via Description Matching

Devin CLI loads skills via description matching in `-p` mode. Skills are installed in `workflow-engine/skills/` and automatically injected when their description matches prompt content.

**Installed skills:**
- `ponytail` - YAGNI/laziness discipline (triggers on "coding dispatch and implementation task")
- `swe-compliance` - Ruthless compliance reviewer (triggers on "compliance review task, code verification, artifact audit, and quality check")

**Trigger phrases in prompts:**
- Coder dispatch: "This is a coding dispatch and implementation task."
- Reviewer dispatch: "This is a compliance review task, code verification, artifact audit, and quality check."

### Guardrails

**1. Leaf modules only (coupling ≤2)**
- Before dispatching coder, call `check_leaf_module_boundary(target_module, workspace)`
- If `is_leaf == False`, ESCALATE to human (SWE-1.6 lacks reasoning depth for cross-cutting work)
- A leaf module imports from ≤2 other modules and no other module depends on it

**2. Harness timeout enforcement**
- Devin CLI has no `--max-turns` flag
- Harness enforces timeout wall-clock (default: 30 turns ≈ 300 seconds)
- If dispatch exceeds timeout, process is killed and artifact is discarded

**3. Independent verification for reviewer BLOCK verdicts**
- Compliance reviewers hallucinate ~70% of syntax claims on async code
- After reviewer BLOCK verdict, call `verify_compliance_block(block_verdict, file_path)`
- For syntax claims: `py_compile` is ground truth
- For behavioral claims: read the file yourself
- Trust compliance BLOCKs only on sync/pandas code; escalate async-code BLOCKs to human

**4. Coder devictory guard**
- SWE-1.6 may claim completion without writing files
- Always dispatch compliance reviewer after every coder
- Verify with `grep`/`stat`/`git diff` before accepting completion claims

### When to Use SWE-1.6 vs Higher-Quality Model

| Use SWE-1.6 | Use Higher-Quality Model |
|---|---|
| Single-file or 2-file leaf modules | Architecture review, cross-cutting work |
| The spec is tight — exact behavior, no ambiguity | The spec needs interpretation or design |
| The task is boring and mechanical | The task requires judgment or adversarial thinking |
| You need 8-10 workers in parallel, free | You need reasoning depth |
| Compliance review (spec adherence, file existence) | Security surface analysis |

**When in doubt:** Would you give this task to a junior who follows instructions exactly, or a senior who thinks before acting? SWE-1.6 is the junior.

---

## 7. Per-Skill Context Manifest

Each skill declares exactly which artifacts are injected into its worker dispatch. This preserves worker neutrality by limiting context to only what's needed.

**Format:** Table mapping skill name to injected context list.

**Example (feature workflow):**

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| brainstorming | request.md |
| test-driven-development | requirement.md |
| writing-plans | requirement.md, baseline.md |
| subagent-driven-development | design.md |
| verification-before-completion | design.md, implementation.md |
| code-review | requirement.md, design.md, diff |

**Correction-loop augmentation:**
- On retry (attempt > 1), injected context becomes: `[original_context, previous_output, correction-{stage}-{attempt-1}.md]`
- This ensures the worker sees what it produced before and why it needs correction

---

## 8. Resumability Protocol

A fresh Cascade session can resume from a previous session using:

1. **Load `run.jsonl`** to reconstruct state:
   - Parse last completed stage
   - Load retry counts, gate verdicts, confidence history

2. **Load present artifacts** to reconstruct reasoning train:
   - All produced artifacts (requirement.md, design.md, etc.)
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

---

## 9. Example: Feature Workflow Runbook

```markdown
# Feature Workflow Runbook

**Source manifest:** `workflows/superpower.manifest.yaml`
**Schema version:** 1
**Session shape:** feature

## 1. Overview

The feature workflow implements a comprehensive gated-change methodology for building software features. It follows a structured sequence from requirement gathering through implementation, verification, and final approval. Key invariants:

- Every stage produces a persistent artifact that survives across sessions
- User gates (g1, g2, g3) are hard stops requiring explicit approval
- All skill execution is performed by stateless Devin workers to preserve neutrality
- All artifact evaluation is performed by a separate neutral reviewer worker
- The reasoning train is preserved in artifacts, not volatile context
- **Canonical source deployment:** The canonical source of truth for workflow definitions is the `manifest.yaml` file. Runbooks are agent-facing companions that must maintain parity with the manifest. When deploying workflow changes, update the manifest first, then update the corresponding runbook to match.

## 2. Stage Sequence

### Stage 0: Session Initialization

**Skill:** `none` (deterministic tool only)
**Phase:** `step_0`
**Required artifacts (output):** [request.md, status.md, session-audit.md]
**Gate:** `none`
**Injected context (worker dispatch):** `none`

#### Dispatch Protocol
1. Call deterministic tool: `session_init(session_id)`
   - Creates workdir: `work/<session_id>/`
   - Creates initial artifacts: request.md, status.md, session-audit.md
2. No worker dispatch (this is scaffolding only)
3. Proceed to Stage 1

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with stage=step_0
2. Write `run.jsonl` entry for session initialization

---

### Stage 1: Brainstorming

**Skill:** `brainstorming`
**Phase:** `step_1`
**Required artifacts (output):** [requirement.md]
**Gate:** `g1_requirement_approval`
**Injected context (worker dispatch):** [request.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load: request.md
   - Include correction artifact if retry: `correction-step_1-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `brainstorming`
   - Context: request.md (focused only)
   - Output: requirement.md
3. Call deterministic tool: `validate_structural([requirement.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: requirement.md + acceptance criteria (from skill definition)
   - Output: `review-step_1-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does requirement.md capture the user's intent?
   - Is it clear, complete, and actionable?
   - Reviewer verdict + floor result
3. Assign confidence + rationale

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong:
   - Analyze structural failures (missing sections, placeholders)
   - Analyze reviewer feedback (unclear, incomplete, incoherent)
2. Persist correction artifact: `correction-step_1-{attempt}.md`
3. Re-dispatch with updated context:
   - Previous requirement.md + correction artifact
4. Bounded retries: max 3 attempts
5. If still FAIL → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g1_requirement_approval:
   - Surface summary: requirement.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g1_requirement_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g1_requirement_approval, verdict)`
3. If approved → proceed to Stage 2
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry

---

### Stage 2: Test-Driven Development

**Skill:** `test-driven-development`
**Phase:** `step_2`
**Required artifacts (output):** [baseline.md]
**Gate:** `none`
**Injected context (worker dispatch):** [requirement.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load: requirement.md
   - Include correction artifact if retry: `correction-step_2-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `test-driven-development`
   - Context: requirement.md (focused only)
   - Output: baseline.md (red tests)
3. Call deterministic tool: `validate_structural([baseline.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: baseline.md + requirement.md
   - Output: `review-step_2-{attempt}.md`
2. Cascade synthesizes verdict:
   - Do tests capture the requirement acceptance criteria?
   - Are tests comprehensive and well-structured?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to Stage 3
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong
2. Persist correction artifact: `correction-step_2-{attempt}.md`
3. Re-dispatch with updated context
4. Bounded retries: max 3 attempts
5. If still FAIL → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry

---

### Stage 3: Writing Plans

**Skill:** `writing-plans`
**Phase:** `step_3`
**Required artifacts (output):** [design.md]
**Gate:** `g2_design_approval`
**Injected context (worker dispatch):** [requirement.md, baseline.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load: requirement.md, baseline.md
   - Include correction artifact if retry: `correction-step_3-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `writing-plans`
   - Context: requirement.md, baseline.md (focused only)
   - Output: design.md
3. Call deterministic tool: `validate_structural([design.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: design.md + requirement.md + baseline.md
   - Output: `review-step_3-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does design.md address the requirement?
   - Is the design coherent with the baseline tests?
   - Is the implementation approach sound?
   - Reviewer verdict + floor result
3. Assign confidence + rationale

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong
2. Persist correction artifact: `correction-step_3-{attempt}.md`
3. Re-dispatch with updated context
4. Bounded retries: max 3 attempts
5. If still FAIL → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g2_design_approval:
   - Surface summary: design.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g2_design_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g2_design_approval, verdict)`
3. If approved → proceed to Stage 4
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry

---

### Stage 4: Subagent-Driven Development

**Skill:** `subagent-driven-development`
**Phase:** `step_4`
**Required artifacts (output):** [implementation.md]
**Gate:** `none`
**Injected context (worker dispatch):** [design.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load: design.md
   - Include correction artifact if retry: `correction-step_4-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `subagent-driven-development`
   - Context: design.md (focused only)
   - Output: implementation.md
3. Call deterministic tool: `validate_structural([implementation.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: implementation.md + design.md
   - Output: `review-step_4-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does implementation.md follow the design?
   - Is the implementation complete and correct?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to Stage 5
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong
2. Persist correction artifact: `correction-step_4-{attempt}.md`
3. Re-dispatch with updated context
4. Bounded retries: max 3 attempts
5. If still FAIL → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry

---

### Stage 5: Verification Before Completion

**Skill:** `verification-before-completion`
**Phase:** `step_5`
**Required artifacts (output):** [verification.md]
**Gate:** `none`
**Injected context (worker dispatch):** [design.md, implementation.md]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load: design.md, implementation.md
   - Include correction artifact if retry: `correction-step_5-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `verification-before-completion`
   - Context: design.md, implementation.md (focused only)
   - Output: verification.md
3. Call deterministic tool: `validate_structural([verification.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: verification.md + design.md + implementation.md
   - Output: `review-step_5-{attempt}.md`
2. Cascade synthesizes verdict:
   - Does verification.md confirm build+tests pass?
   - Are all acceptance criteria met?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to Stage 6
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong
2. Persist correction artifact: `correction-step_5-{attempt}.md`
3. Re-dispatch with updated context
4. Bounded retries: max 3 attempts
5. If still FAIL → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry

---

### Stage 6: Code Review

**Skill:** `code-review`
**Phase:** `step_6`
**Required artifacts (output):** [review-spec.md, review-quality.md, human-verdict.md]
**Gate:** `none`
**Injected context (worker dispatch):** [requirement.md, design.md, diff]

#### Dispatch Protocol
1. Build focused dispatch context:
   - Load: requirement.md, design.md, diff
   - Include correction artifact if retry: `correction-step_6-{attempt}.md`
2. Dispatch to stateless Devin worker:
   - Skill: `code-review`
   - Context: requirement.md, design.md, diff (focused only)
   - Output: review-spec.md, review-quality.md, human-verdict.md
3. Call deterministic tool: `validate_structural([review-spec.md, review-quality.md, human-verdict.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: review-spec.md, review-quality.md, human-verdict.md + requirement.md + design.md
   - Output: `review-step_6-{attempt}.md`
2. Cascade synthesizes verdict:
   - Do reviews capture spec compliance and code quality?
   - Is the human verdict documented?
   - Reviewer verdict + floor result
3. Assign confidence + rationale:
   - HIGH → proceed to Stage 7
   - MEDIUM → proceed with logged caveat (non-gated)
   - LOW → correction loop

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong
2. Persist correction artifact: `correction-step_6-{attempt}.md`
3. Re-dispatch with updated context
4. Bounded retries: max 3 attempts
5. If still FAIL → ESCALATE to human

#### Gate Protocol
No gate for this stage → auto-proceed on HIGH/MEDIUM, correct on LOW

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry

---

### Stage 7: Final Summary

**Skill:** `none` (Cascade synthesizes directly)
**Phase:** `step_7`
**Required artifacts (output):** [summary.md, metrics.json, retro.md]
**Gate:** `g3_final_approval`
**Injected context (worker dispatch):** `none`

#### Dispatch Protocol
1. Cascade synthesizes final artifacts directly:
   - summary.md: summary of the feature workflow
   - metrics.json: metrics from the workflow (time, attempts, etc.)
   - retro.md: retrospective on what went well/what could be improved
2. Call deterministic tool: `validate_structural([summary.md, metrics.json, retro.md])`
   - FAIL → proceed to correction loop
   - PASS → proceed to semantic evaluation

#### Semantic Evaluation
1. Dispatch neutral reviewer worker:
   - Model: `swe-1-6`
   - Context: summary.md, metrics.json, retro.md + all prior artifacts
   - Output: `review-step_7-{attempt}.md`
2. Cascade synthesizes verdict:
   - Are final artifacts complete and accurate?
   - Reviewer verdict + floor result
3. Assign confidence + rationale

#### Correction Loop (if floor FAIL or confidence LOW)
1. Cascade reasons about what's wrong
2. Cascade regenerates final artifacts
3. Bounded retries: max 3 attempts
4. If still FAIL → ESCALATE to human

#### Gate Protocol
1. HARD STOP at g3_final_approval:
   - Surface summary: summary.md + metrics.json + retro.md + reviewer verdict + confidence + rationale
   - Persist decision artifact: `gate-g3_final_approval.md`
   - Await human verdict (explicit_approval required)
2. Call deterministic tool: `record_gate(g3_final_approval, verdict)`
3. If approved → workflow complete
4. If rejected → ESCALATE to human for guidance

#### Audit & State Recording
1. Call deterministic tool: `append_audit(...)` with full stage details
2. Write `run.jsonl` entry
3. Workflow complete

---

## 3. Triage Protocol

[As specified in Section 3 of this format spec]

## 4. Escalation Policy

[As specified in Section 4 of this format spec]

## 5. Deterministic Tool Calls

[As specified in Section 5 of this format spec]

## 6. Per-Skill Context Manifest

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| brainstorming | request.md |
| test-driven-development | requirement.md |
| writing-plans | requirement.md, baseline.md |
| subagent-driven-development | design.md |
| verification-before-completion | design.md, implementation.md |
| code-review | requirement.md, design.md, diff |

## 7. Resumability Protocol

[As specified in Section 7 of this format spec]
```

---

## 9. Validation Checklist

Before considering a runbook complete, verify:

- [ ] Runbook source manifest reference matches actual manifest file
- [ ] Schema version matches manifest schema_version
- [ ] Session shape matches manifest session_shape
- [ ] All stages from manifest are represented in runbook
- [ ] All skills from manifest are mapped to stages
- [ ] All required artifacts from manifest are listed per stage
- [ ] All gates from manifest are mapped to correct stages
- [ ] Per-skill context manifest is complete for all skills
- [ ] Triage protocol is specified
- [ ] Escalation policy is specified
- [ ] Deterministic tool calls are specified
- [ ] Resumability protocol is specified
- [ ] Runbook and manifest agree (parity test)

---

## 10. Maintenance

When updating a workflow:

1. Update `manifest.yaml` first (structured source of truth)
2. Update corresponding `*.runbook.md` to match
3. Run parity test to verify agreement
4. Commit both files together

**Parity test concept:**
- Parse manifest for stages, skills, artifacts, gates
- Parse runbook for same information
- Assert: manifest.stages == runbook.stages
- Assert: manifest.skills == runbook.skills
- Assert: manifest.required_artifacts == runbook.required_artifacts
- Assert: manifest.gates == runbook.gates
- Fail if any mismatch

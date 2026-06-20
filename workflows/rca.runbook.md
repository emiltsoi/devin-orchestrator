# RCA Workflow Runbook

**Source manifest:** `workflows/rca.manifest.yaml`
**Schema version:** 1
**Session shape:** rca

## 1. Overview

The RCA (Root Cause Analysis) workflow is an investigation-only workflow for analyzing incidents, bugs, or failures. It follows a systematic debugging approach to gather evidence, analyze it, identify the root cause, and propose fixes.

**Core principle:** Read-only git operations. No implementation or code changes.

**Key invariants:**
- Root cause must be approved before proposing fixes
- Fix recommendations must be approved before completion
- All investigation is read-only (no git write operations)

## 2. Stage Sequence

### Stage 0: Gather Evidence
- **Skill:** systematic-debugging
- **Input:** incident_report, logs
- **Output:** evidence.md
- **Gate:** none
- **Triage:** Proceed if evidence is complete and relevant

### Stage 1: Analyze Evidence
- **Skill:** systematic-debugging
- **Input:** evidence.md
- **Output:** analysis.md
- **Gate:** none
- **Triage:** Proceed if analysis is thorough and identifies potential causes

### Stage 2: Identify Root Cause
- **Skill:** systematic-debugging
- **Input:** analysis.md
- **Output:** root_cause.md
- **Gate:** g1_root_cause_approval (human)
- **Triage:** Wait for human root cause approval before proceeding

### Stage 3: Propose Fixes
- **Skill:** systematic-debugging
- **Input:** root_cause.md
- **Output:** fix_recommendations.md
- **Gate:** none
- **Triage:** Proceed if fix recommendations are specific and actionable

### Stage 4: Verify Fixes
- **Skill:** verification-before-completion
- **Input:** fix_recommendations.md
- **Output:** verification.md
- **Gate:** g2_fix_approval (human)
- **Triage:** Wait for human fix approval before completion

## 3. Triage Protocol

**After each stage:**
1. Validate structural floor (file existence, non-emptiness, no placeholders)
2. Dispatch neutral reviewer (SWE-1.6 with swe-compliance skill)
3. Cascade triage decision based on:
   - Structural result (PASS/FAIL)
   - Reviewer verdict (PASS/BLOCK)
   - Confidence score (HIGH/MEDIUM/LOW)
   - Stage-specific criteria

**Triage decisions:**
- **proceed:** Structural PASS + reviewer PASS + confidence HIGH/MEDIUM
- **retry:** Structural FAIL or reviewer BLOCK + confidence LOW + retry_count < 3
- **escalate:** Retry exhausted or confidence LOW with critical issues
- **wait:** At human gate (g1, g2)

## 4. Escalation Policy

**Escalate to human when:**
- Retry loop exhausted (3 attempts)
- Confidence LOW with critical security or data loss issues
- Root cause cannot be identified
- Fix recommendations are unclear or incomplete
- Verification fails

## 5. Deterministic Tool Calls

| Tool | When to Call | Purpose |
|------|--------------|---------|
| `session_init(session_id)` | Stage 0 only | Scaffolds workdir, creates request.md, status.md, session-audit.md |
| `validate_structural(artifacts)` | After every worker dispatch | Checks existence, non-emptiness, no placeholders, Iron-Law rules |
| `record_gate(gate_id, verdict)` | After every human gate decision | Records gate verdict to audit ledger |
| `append_audit(...)` | After every stage decision | Appends structured entry to session-audit.md |
| `write_run_jsonl(entry)` | After every stage decision | Appends machine-readable entry to run.jsonl for resumability |

## 6. Per-Skill Context Manifest

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| systematic-debugging | incident_report, logs, evidence.md, analysis.md |
| verification-before-completion | fix_recommendations.md, root_cause.md |

**Correction-loop augmentation:**
- On retry (attempt > 1), injected context becomes: `[original_context, previous_output, correction-{stage}-{attempt-1}.md]`

## 7. Resumability Protocol

A fresh Cascade session can resume from a previous session using:

1. **Load `run.jsonl`** to reconstruct state:
   - Parse last completed stage
   - Load retry counts, gate verdicts, confidence history

2. **Load present artifacts** to reconstruct reasoning train:
   - All produced artifacts (evidence.md, analysis.md, root_cause.md, etc.)
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

## 8. Devin Dispatch Protocol

Cascade dispatches to SWE-1.6 (free tier) via Devin CLI with specific guardrails:

### Skill Loading via Description Matching

**Installed skills:**
- `swe-compliance` - Ruthless compliance reviewer (triggers on "compliance review task, code verification, artifact audit, and quality check")

**Trigger phrases in prompts:**
- Reviewer dispatch: "This is a compliance review task, code verification, artifact audit, and quality check."

### Guardrails

**1. Read-only git operations**
- RCA workflow is investigation-only
- No git write operations allowed
- Use `git log`, `git show`, `git diff` for investigation
- Do not create branches, commits, or tags

**2. Independent verification for reviewer BLOCK verdicts**
- Compliance reviewers hallucinate ~70% of syntax claims on async code
- After reviewer BLOCK verdict, call `verify_compliance_block(block_verdict, file_path)`
- For syntax claims: `py_compile` is ground truth

### When to Use SWE-1.6 vs Higher-Quality Model

| Use SWE-1.6 | Use Higher-Quality Model |
|---|---|
| Log analysis and pattern matching | Complex architectural analysis |
| Code reading and understanding | Cross-system dependency analysis |
| Evidence gathering | Adversarial thinking for security issues |
| Compliance review | Security surface analysis |

## 9. Stage-Specific Notes

### Stage 0: Gather Evidence
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Gather logs, code, and reproduction steps
- Document all evidence in evidence.md
- Ensure evidence is complete and relevant

### Stage 1: Analyze Evidence
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Analyze evidence to identify potential causes
- Document analysis in analysis.md
- Consider multiple hypotheses

### Stage 2: Identify Root Cause
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Identify the root cause from analysis
- Document root cause in root_cause.md
- Gate g1: Human must approve root cause before proposing fixes

### Stage 3: Propose Fixes
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Propose specific, actionable fixes
- Document fix recommendations in fix_recommendations.md
- Include implementation details (but do not implement)

### Stage 4: Verify Fixes
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Verify that proposed fixes address the root cause
- Document verification in verification.md
- Gate g2: Human must approve fix recommendations before completion

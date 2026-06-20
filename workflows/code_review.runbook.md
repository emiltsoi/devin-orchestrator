# Code Review Workflow Runbook

**Source manifest:** `workflows/code_review.manifest.yaml`
**Schema version:** 1
**Session shape:** code_review

## 1. Overview

The Code Review workflow is a review-only workflow for evaluating code changes. It follows a structured review process to load code, review spec compliance, review code quality, and compile findings by severity.

**Core principle:** Read-only git operations. No implementation or code changes.

**Key invariants:**
- Code must be loaded before review
- Spec compliance and code quality are reviewed separately
- Findings are compiled by severity (Critical, Important, Minor)
- Human makes final approval decision

## 2. Stage Sequence

### Stage 0: Load Code
- **Skill:** requesting-code-review
- **Input:** code_diff, files_to_review
- **Output:** code_context.md
- **Gate:** none
- **Triage:** Proceed if code context is successfully loaded

### Stage 1: Review Spec Compliance
- **Skill:** requesting-code-review
- **Input:** code_context.md, review_criteria
- **Output:** spec_review.md
- **Gate:** none
- **Triage:** Proceed if spec review is complete and identifies compliance issues

### Stage 2: Review Code Quality
- **Skill:** swe-compliance
- **Input:** code_context.md, spec_review.md
- **Output:** quality_review.md
- **Gate:** none
- **Triage:** Proceed if code quality review is complete and identifies quality issues

### Stage 3: Compile Findings
- **Skill:** requesting-code-review
- **Input:** spec_review.md, quality_review.md
- **Output:** review_findings.md
- **Gate:** g1_approval_decision (human)
- **Triage:** Wait for human approval decision (approve, request changes, or block)

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
- **wait:** At human gate (g1)

## 4. Escalation Policy

**Escalate to human when:**
- Retry loop exhausted (3 attempts)
- Confidence LOW with critical security or data loss issues
- Code cannot be loaded (invalid paths, permissions)
- Review findings are unclear or incomplete

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
| requesting-code-review | code_diff, files_to_review, code_context.md, spec_review.md, quality_review.md |
| swe-compliance | code_context.md, spec_review.md |

**Correction-loop augmentation:**
- On retry (attempt > 1), injected context becomes: `[original_context, previous_output, correction-{stage}-{attempt-1}.md]`

## 7. Resumability Protocol

A fresh Cascade session can resume from a previous session using:

1. **Load `run.jsonl`** to reconstruct state:
   - Parse last completed stage
   - Load retry counts, gate verdicts, confidence history

2. **Load present artifacts** to reconstruct reasoning train:
   - All produced artifacts (code_context.md, spec_review.md, quality_review.md, etc.)
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
- Code review workflow is review-only
- No git write operations allowed
- Use `git show`, `git diff` for review
- Do not create branches, commits, or tags

**2. Independent verification for reviewer BLOCK verdicts**
- Compliance reviewers hallucinate ~70% of syntax claims on async code
- After reviewer BLOCK verdict, call `verify_compliance_block(block_verdict, file_path)`
- For syntax claims: `py_compile` is ground truth

### When to Use SWE-1.6 vs Higher-Quality Model

| Use SWE-1.6 | Use Higher-Quality Model |
|---|---|
| Spec compliance review | Complex architectural review |
| Code quality checks | Security surface analysis |
| Style and best practices | Cross-system dependency analysis |
| Compliance review | Adversarial thinking for security issues |

## 9. Stage-Specific Notes

### Stage 0: Load Code
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Load code diff and files to review
- Document code context in code_context.md
- Ensure code context is complete and accurate

### Stage 1: Review Spec Compliance
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Review code against spec and requirements
- Check if code addresses the intended changes
- Document spec compliance findings in spec_review.md

### Stage 2: Review Code Quality
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Review code quality, style, and best practices
- Check for bugs, security issues, performance problems
- Document quality findings in quality_review.md

### Stage 3: Compile Findings
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance for reviewer)
- Compile findings from spec_review.md and quality_review.md
- Categorize by severity (Critical, Important, Minor)
- Document final findings in review_findings.md
- Gate g1: Human makes approval decision (approve, request changes, or block)

## 10. Severity Levels

**Critical:**
- Security vulnerabilities
- Data loss risk
- Breaking changes
- Incorrect behavior

**Important:**
- Performance issues
- Error handling gaps
- Missing edge cases
- Test coverage gaps

**Minor:**
- Style issues
- Naming inconsistencies
- Documentation gaps
- Code organization

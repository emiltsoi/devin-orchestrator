# Superpower Workflow Runbook

**Source manifest:** `workflows/superpower.manifest.yaml`
**Schema version:** 1
**Session shape:** superpower

## 1. Overview

The Superpower workflow is a complete software development methodology for coding agents, built on composable skills. It follows a "design → plan → execute → verify" pipeline with mandatory skill checks before each task.

**Core principle:** The agent checks for relevant skills before any task. Mandatory workflows, not suggestions.

**Key invariants:**
- Design must be approved before creating worktree
- Plan must be approved before execution
- Code review findings must be reviewed before completion
- Test-driven development enforced during implementation
- Clean worktree cleanup on completion

## 2. Stage Sequence

### Stage 0: Brainstorming
- **Skill:** brainstorming
- **Input:** User request (request.md)
- **Output:** design.md
- **Gate:** none
- **Triage:** Proceed if design is complete and addresses request

### Stage 1: Using Git Worktrees
- **Skill:** using-git-worktrees
- **Input:** design.md
- **Output:** worktree-info.md, baseline-test-results.md
- **Gate:** g1_design_approval (human)
- **Triage:** Wait for human design approval before proceeding

### Stage 2: Writing Plans
- **Skill:** writing-plans
- **Input:** design.md
- **Output:** plan.md
- **Gate:** none
- **Triage:** Proceed if plan is complete with bite-sized tasks

### Stage 3: Subagent-Driven Development
- **Skill:** subagent-driven-development
- **Input:** plan.md, design.md
- **Output:** implementation.md, task-results.md
- **Gate:** g2_plan_approval (human)
- **Triage:** Wait for human plan approval before proceeding

### Stage 4: Test-Driven Development
- **Skill:** test-driven-development
- **Input:** implementation.md
- **Output:** test-results.md, implementation-final.md
- **Gate:** none
- **Triage:** Proceed if RED-GREEN-REFACTOR cycle completed successfully

### Stage 5: Requesting Code Review
- **Skill:** requesting-code-review
- **Input:** plan.md, implementation-final.md
- **Output:** review-findings.md
- **Gate:** g3_review_approval (human)
- **Triage:** Wait for human review approval before proceeding

### Stage 6: Finishing a Development Branch
- **Skill:** finishing-a-development-branch
- **Input:** test-results.md, review-findings.md
- **Output:** completion-summary.md, merge-decision.md
- **Gate:** g4_completion_approval (human)
- **Triage:** Wait for human completion approval before cleanup

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
- **wait:** At human gate (g1, g2, g3, g4)

## 4. Escalation Policy

**Escalate to human when:**
- Retry loop exhausted (3 attempts)
- Confidence LOW with critical security or data loss issues
- Worktree creation fails (git or permission issues)
- Test baseline verification fails
- Merge/PR decision requires human judgment
- Reviewer BLOCK cannot be independently verified (guardrail)

## 5. Deterministic Tool Calls

| Tool | When to Call | Purpose |
|------|--------------|---------|
| `session_init(session_id)` | Stage 0 only | Scaffolds workdir, creates request.md, status.md, session-audit.md |
| `validate_structural(artifacts)` | After every worker dispatch | Checks existence, non-emptiness, no placeholders, Iron-Law rules |
| `record_gate(gate_id, verdict)` | After every human gate decision | Records gate verdict to audit ledger |
| `append_audit(...)` | After every stage decision | Appends structured entry to session-audit.md |
| `write_run_jsonl(entry)` | After every stage decision | Appends machine-readable entry to run.jsonl for resumability |
| `verify_compliance_block(block_verdict, file_path)` | After reviewer BLOCK verdict | Independently verifies compliance reviewer BLOCK verdicts |
| `check_leaf_module_boundary(target_module, workspace)` | Before coder dispatch | Verifies target module respects leaf module boundary (coupling ≤2) |

## 6. Per-Skill Context Manifest

| Skill | Injected Context (Worker Dispatch Only) |
|-------|----------------------------------------|
| brainstorming | request.md |
| using-git-worktrees | design.md |
| writing-plans | design.md |
| subagent-driven-development | plan.md, design.md |
| test-driven-development | implementation.md |
| requesting-code-review | plan.md, implementation-final.md |
| finishing-a-development-branch | test-results.md, review-findings.md |

**Correction-loop augmentation:**
- On retry (attempt > 1), injected context becomes: `[original_context, previous_output, correction-{stage}-{attempt-1}.md]`

## 7. Resumability Protocol

A fresh Cascade session can resume from a previous session using:

1. **Load `run.jsonl`** to reconstruct state:
   - Parse last completed stage
   - Load retry counts, gate verdicts, confidence history

2. **Load present artifacts** to reconstruct reasoning train:
   - All produced artifacts (design.md, plan.md, implementation.md, etc.)
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
- `ponytail` - YAGNI/laziness discipline (triggers on "coding dispatch and implementation task")
- `swe-compliance` - Ruthless compliance reviewer (triggers on "compliance review task, code verification, artifact audit, and quality check")

**Trigger phrases in prompts:**
- Coder dispatch: "This is a coding dispatch and implementation task."
- Reviewer dispatch: "This is a compliance review task, code verification, artifact audit, and quality check."

### Guardrails

**1. Leaf modules only (coupling ≤2)**
- Before dispatching coder, call `check_leaf_module_boundary(target_module, workspace)`
- If `is_leaf == False`, ESCALATE to human

**2. Harness timeout enforcement**
- Devin CLI has no `--max-turns` flag
- Harness enforces timeout wall-clock (default: 30 turns ≈ 300 seconds)

**3. Independent verification for reviewer BLOCK verdicts**
- Compliance reviewers hallucinate ~70% of syntax claims on async code
- After reviewer BLOCK verdict, call `verify_compliance_block(block_verdict, file_path)`
- For syntax claims: `py_compile` is ground truth

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

## 9. Stage-Specific Notes

### Stage 0: Brainstorming
- Trigger phrase: "This is a coding dispatch and implementation task." (ponytail)
- Design document must be in sections for validation
- Explore alternatives before settling on design

### Stage 1: Using Git Worktrees
- Trigger phrase: "This is a coding dispatch and implementation task." (ponytail)
- Creates isolated workspace on new branch
- Verifies clean test baseline before proceeding
- Gate g1: Human must approve design before worktree creation

### Stage 2: Writing Plans
- Trigger phrase: "This is a coding dispatch and implementation task." (ponytail)
- Break work into bite-sized tasks (2-5 minutes each)
- Every task must have exact file paths, complete code, verification steps
- Plan must be detailed enough for independent execution

### Stage 3: Subagent-Driven Development
- Trigger phrase: "This is a coding dispatch and implementation task." (ponytail)
- Dispatches fresh subagent per task
- Two-stage review: spec compliance, then code quality
- Gate g2: Human must approve plan before execution

### Stage 4: Test-Driven Development
- Trigger phrase: "This is a coding dispatch and implementation task." (ponytail)
- Enforces RED-GREEN-REFACTOR cycle
- Write failing test → watch it fail → write minimal code → watch it pass → commit
- Deletes code written before tests

### Stage 5: Requesting Code Review
- Trigger phrase: "This is a compliance review task, code verification, artifact audit, and quality check." (swe-compliance)
- Reviews against plan
- Reports issues by severity
- Critical issues block progress
- Gate g3: Human must review findings before completion

### Stage 6: Finishing a Development Branch
- Trigger phrase: "This is a coding dispatch and implementation task." (ponytail)
- Verifies tests
- Presents options: merge locally, push and create PR, keep as-is, discard
- Cleans up worktree
- Gate g4: Human must approve merge/PR/keep/discard decision

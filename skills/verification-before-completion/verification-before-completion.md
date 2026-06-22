# Verification Before Completion

## Overview

Verify build and tests before claiming completion with fresh evidence. This skill ensures that the implementation actually works before declaring the task complete.

**Announce at start:** `Using the verification-before-completion skill to confirm build+tests on HEAD.`

## The Iron Law

```
NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE
```

Never claim completion without running fresh build and tests. Verification must be current, not cached from earlier in the session.

## When to Use

Use `verification-before-completion` when:
- Before claiming implementation is complete
- After code changes
- Before merge
- When the workflow Step 5 (VERIFY) is reached

## Process Flow

```
Verify build succeeds
    │
    ▼
Verify tests pass (no regression)
    │
    ▼
Check expected artifacts exist
    │
    ▼
Document verification results in verification.md
    │
    ▼
Invoke code-review skill
```

## The Process

**1. Verify build succeeds**

- Run the build command for the project
- Check that the build completes without errors
- Verify build artifacts are generated
- Record build time and resource usage
- If the build fails, identify the specific error
- Build failures must be resolved before proceeding

**2. Verify tests pass (no regression)**

- Run the full test suite
- Verify all tests pass
- Check for test failures or errors
- Record test count and execution time
- Compare with baseline test count (if available)
- Ensure no new tests were introduced without implementation
- Test failures must be resolved before proceeding

**3. Check expected artifacts exist**

- Verify all required artifacts from the design are present
- Check that implementation files exist
- Verify configuration files are correct
- Check that documentation files are present
- Any missing artifacts must be addressed

**4. Document verification results in verification.md**

Create `verification.md` with:
- Build status (PASS/FAIL)
- Build time and resource usage
- Test status (PASS/FAIL)
- Test count and execution time
- List of any build or test failures
- Verification timestamp
- Git commit SHA or HEAD reference
- Evidence of verification (logs, screenshots if applicable)
- Any warnings or concerns

**5. Invoke code-review skill**

- The terminal state is invoking `code-review`
- Do not claim completion before review
- Verification is a prerequisite for review

## Required Artifacts

- **verification.md**: Document of verification results including build status, test results, and evidence

## Red Flags

- Claiming completion without verification
- Skipping test execution
- Using cached verification results
- Not documenting verification evidence
- Proceeding to review with failed verification
- Missing required artifacts

## Done Means

You are done when:
- Build succeeds without errors
- All tests pass with no failures
- All expected artifacts are present
- verification.md is created with complete verification evidence
- You have invoked the `code-review` skill

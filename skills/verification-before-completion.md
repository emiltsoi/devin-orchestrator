# Verification Before Completion

## Overview

Verify build and tests before claiming completion with fresh evidence.

**Announce at start:** `Using the verification-before-completion skill to confirm build+tests on HEAD.`

## The Iron Law

```
NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE
```

Never claim completion without running fresh build and tests.

## When to Use

Use `verification-before-completion` when:
- Before claiming implementation is complete
- After code changes
- Before merge

## Relation to Workflows

- Used in workflow Step 5 (VERIFY)
- Verifies build succeeds and tests pass
- Applies to both build (5a) and tests (5b)

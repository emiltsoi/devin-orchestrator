---
name: test-driven-development
description: "Use when implementing any feature or bugfix, before writing implementation code, to enforce the RED-GREEN-REFACTOR cycle."
---

# Test-Driven Development (TDD)

## Overview

Write the test first. Watch it fail. Write minimal code to pass.

**Core principle:** If you didn't watch the test fail, you don't know if it tests the right thing.

**Violating the letter of the rules is violating the spirit of the rules.**

## When to Use

**Always:**
- New features
- Bug fixes
- Refactoring
- Behavior changes

**Exceptions (ask your human partner):**
- Throwaway prototypes
- Generated code
- Configuration files

Thinking "skip TDD just this once"? Stop. That's rationalization.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Don't look at it
- Delete means delete

Implement fresh from tests. Period.

## Red-Green-Refactor

### RED - Write Failing Test

Write a test that fails because the feature doesn't exist yet.

**Rules:**
- Write the test first
- Make it fail for the right reason
- Don't write production code yet

### Verify RED - Watch It Fail

Run the test and watch it fail.

**If it doesn't fail:**
- The test is wrong — fix it
- The feature already exists — delete the test, write a new one

**If it fails for the wrong reason:**
- Fix the test
- Don't write production code yet

### GREEN - Minimal Code

Write the minimal code to make the test pass.

**Rules:**
- Write the minimal code possible
- Don't optimize yet
- Don't add features not tested
- Don't refactor yet

### Verify GREEN - Watch It Pass

Run the test and watch it pass.

**If it doesn't pass:**
- Fix the code
- Don't change the test (unless the test is wrong)

### REFACTOR - Clean Up

Refactor the code while keeping tests green.

**Rules:**
- Only refactor when tests pass
- Run tests after each refactor
- Stop if tests fail
- Don't add features during refactor

### Repeat

Repeat the cycle for the next feature.

## Good Tests

- **Test behavior, not implementation**
- **Test edge cases**
- **Test error conditions**
- **Test in isolation**
- **Have clear names**

## Why Order Matters

If you write code first, you're testing the code, not the behavior. You don't know if the test actually tests what you think it tests.

If you write the test first and watch it fail, you know the test tests the right thing.

## Common Rationalizations

**"This is too simple to need a test"** — Simple code is where bugs hide.

**"I'll add tests later"** — You won't. Later never comes.

**"The test is too hard to write"** — If the test is hard, the design is wrong.

**"I'm just exploring"** — Then it's a prototype, not production code.

## Red Flags - STOP and Start Over

- You wrote production code before the test
- You didn't watch the test fail
- You're testing implementation, not behavior
- You're skipping tests "just this once"

## Example: Bug Fix

1. Write a test that reproduces the bug
2. Watch it fail (RED)
3. Write minimal code to fix the bug
4. Watch it pass (GREEN)
5. Refactor if needed (REFACTOR)

## Verification Checklist

Before moving on:
- [ ] Test written first
- [ ] Test watched failing
- [ ] Minimal code written
- [ ] Test watched passing
- [ ] No production code before test
- [ ] No features added not tested

## When Stuck

If you're stuck:
- The test might be wrong — rethink the test
- The design might be wrong — rethink the design
- Ask your human partner for help

## Debugging Integration

If integration tests fail:
- Check that unit tests pass
- Check that interfaces match
- Check that dependencies are correct
- Don't skip TDD for integration

## Testing Anti-Patterns

- Testing private methods
- Testing implementation details
- Over-mocking
- Testing everything
- Not testing edge cases

## Final Rule

If you didn't watch the test fail, you don't know if it tests the right thing. Delete the code. Start over.

# Test-Driven Development

## Overview

Write tests before implementation following the red-green-refactor discipline. This skill establishes a baseline of failing tests (RED state) that will drive implementation in subsequent steps.

**Announce at start:** `Using the test-driven-development skill to produce red tests for <task>.`

## The Iron Law

```
WRITE FAILING TEST FIRST, THEN IMPLEMENT TO MAKE IT PASS
```

Never write implementation before tests. Always verify tests fail before implementing. This is the foundation of TDD discipline.

## When to Use

Use `test-driven-development` when:
- You need to write new functionality
- You need to modify existing functionality
- You need to ensure regression coverage
- A baseline.md artifact is required by the workflow

## Process Flow

```
Identify existing relevant tests
    │
    ▼
Run existing tests to confirm green baseline
    │
    ▼
Write test specification with expected behavior
    │
    ▼
Write failing tests (TDD red)
    │
    ▼
Run tests to verify they fail
    │
    ▼
Document baseline in baseline.md
    │
    ▼
Invoke writing-plans skill
```

## The Process

**1. Identify existing relevant tests**

- Search the codebase for existing tests related to the feature/area
- Check test directories (e.g., `tests/`, `spec/`, `__tests__/`)
- Identify test frameworks in use (pytest, unittest, jest, etc.)
- Note any existing test fixtures or test data
- If no tests exist, document this in baseline.md

**2. Confirm green baseline**

- Run the existing test suite
- Verify all existing tests pass
- Record the current test count and execution time
- This establishes the baseline before new tests are added
- If existing tests fail, this must be addressed first (not part of this skill)

**3. Write test specification**

- Define the expected behavior of the new functionality
- Specify edge cases and error conditions
- List the test cases to be written
- Include test data and expected outputs
- This specification guides test implementation

**4. Write failing tests (TDD red)**

- Implement the test cases from the specification
- Write tests that will fail because the implementation doesn't exist yet
- Follow the test framework conventions
- Ensure tests are clear, focused, and independent
- **Do not write any implementation code**

**5. Verify tests fail**

- Run the new tests
- Confirm they fail with the expected error messages
- This validates the tests are correctly detecting the missing implementation
- If tests pass unexpectedly, the test is incorrect (not the implementation)

**6. Document baseline in baseline.md**

Create `baseline.md` with:
- Test count before new tests (baseline)
- Test count after new tests (baseline + new)
- Execution time
- Test framework used
- List of new test files added
- Expected failure reasons for new tests
- Any test fixtures or test data created

**7. Invoke writing-plans skill**

- The terminal state is invoking `writing-plans`
- Do not proceed to implementation
- The design phase comes before implementation

## Required Artifacts

- **baseline.md**: Document of test baseline including test counts, execution time, and new test specifications

## Red Flags

- Writing implementation code before tests
- Skipping the test failure verification
- Writing tests that pass immediately (no red state)
- Not documenting the baseline
- Proceeding to implementation without design approval

## Done Means

You are done when:
- All new tests are written and verified to fail
- baseline.md is created with complete baseline documentation
- The test specification is clear and comprehensive
- You have invoked the `writing-plans` skill

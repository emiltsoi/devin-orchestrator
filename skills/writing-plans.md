# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer (Coder agent) has zero context for this codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks.

DRY. YAGNI. TDD. Frequent commits.

Assume the engineer is skilled but knows almost nothing about our toolset, handler model, or problem domain. Assume they don't know good test design very well.

**Announce at start:** `Using the writing-plans skill to produce design.md for <session_id>.`

## The Iron Law

```
EVERY STEP CONTAINS THE ACTUAL CONTENT THE ENGINEER NEEDS.
NO PLACEHOLDERS. NO TBD. NO "SIMILAR TO TASK N".
```

A plan step that says "add appropriate error handling" is a plan failure. Replace it with the actual code block.

## Where Plans Live

In the harness:
- **Implementation plan** → `work/<session_id>/design.md`

The plan document should include:
- Goal (one sentence)
- Architecture (2-3 sentences)
- Affected layers
- Test strategy
- Bite-sized tasks with exact code blocks

## Scope Check (before writing any task)

If the spec covers multiple independent subsystems, it should have been broken into sub-specs during `brainstorming`. If it wasn't, stop and suggest decomposition — each plan should produce working, testable software on its own.

## File Structure (decompose files, then decompose tasks)

Before defining tasks, map out which files will be created or modified and what each one is responsible for:

- Design units with clear boundaries and well-defined interfaces. Each file has one clear responsibility.
- Files that change together live together. Split by responsibility, not by technical layer.
- Prefer smaller, focused files over large ones doing too much.
- In existing codebases, follow established patterns. Don't unilaterally restructure.

## Bite-Sized Task Granularity

**Each step is ONE action (2-5 minutes):**

| Step style | Example |
|---|---|
| ✅ "Write the failing test" | One test, one file |
| ✅ "Run it to confirm it fails" | Exact command, exact expected message |
| ✅ "Implement the minimal code to make the test pass" | Show the code |
| ✅ "Run tests to confirm they pass" | Exact command |
| ✅ "Commit" | Exact commit message |
| ❌ "Add error handling" | Vague — what errors? where? |
| ❌ "Implement the feature" | Too large — split it |
| ❌ "Similar to Task N" | Agent may read tasks out of order; repeat the code |

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# <session_id> Implementation Plan

> **For the Coder agent / executor:** REQUIRED SUB-SKILL — use `subagent-driven-development` (when the Architect is orchestrating multiple tasks with review between each) or `executing-plans` (when you are running the plan yourself).
>
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** <one sentence describing what this builds>

**Architecture:** <2-3 sentences about the approach>

**Affected layers:** <which layers this change touches>

**Test strategy:** <how we'll know it works — red-green-refactor gates>

---
```

## Task Structure

Each task is a numbered heading with a files manifest and numbered steps:

````markdown
### Task N: <Component Name>

**Files:**
- Create: `exact/path/to/file.cpp`
- Modify: `exact/path/to/existing.cpp:123-145`
- Test: `exact/path/to/test.cpp`

**Preconditions:**
- Task N-1 committed
- `git status` clean on branch

**Steps:**

- [ ] **Step 1: Write the failing test**

  ```cpp
  TEST_F(WidgetTest, handlesEmptyInput) {
      Widget w;
      EXPECT_EQ(w.process(""), WidgetError::EmptyInput);
  }
  ```

- [ ] **Step 2: Run test to verify it fails**

  Run:
  ```
  python -m pytest tests/test_widget.py::test_handles_empty_input
  ```
  Expected: FAIL with `WidgetError::EmptyInput not defined` or similar.

- [ ] **Step 3: Write minimal implementation**

  In `src/widget/Widget.cpp`, add:
  ```cpp
  WidgetError Widget::process(std::string_view input) {
      if (input.empty()) return WidgetError::EmptyInput;
      // existing logic
  }
  ```

- [ ] **Step 4: Run test to verify it passes**

  Run: (same command as Step 2)
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add src/widget/Widget.cpp tests/widget/WidgetTest.cpp
  git commit -m "Widget: reject empty input"
  ```
````

## No Placeholders

These patterns are **plan failures**. Search for them before declaring the plan done:

- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without the actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps describing *what* to do without showing *how* (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Remember

- Exact file paths always (with line ranges for modifications where stable)
- Complete code in every step — if a step changes code, show the code
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits

## Self-Review (before handoff)

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself — not a delegated review.

1. **Spec coverage:** For each numbered acceptance criterion in `requirement.md`, point to the task that implements it. List any gaps.
2. **Placeholder scan:** Search for red flags — any of the patterns from *No Placeholders*. Fix them.
3. **Type consistency:** Do the types, method signatures, and property names in later tasks match what was defined in earlier tasks?
4. **Cross-layer check:** Have you accounted for all layers that the change touches? If a layer is affected but has no task, add it.
5. **KB impact:** Does the change introduce new enums / IDs / protocol messages / state conditions? Is a step in the plan scheduled to update the corresponding knowledge files?

If you find issues, fix them inline. No need to re-review — just fix and move on.

## Execution Handoff

After saving the plan, present the execution options to your human partner:

```
Plan complete and saved to work/<session_id>/design.md.

Two execution options:

1. Subagent-Driven (recommended)
   - Architect dispatches a fresh Coder prompt per task via transport adapter
   - Review between tasks (spec-reviewer then quality-reviewer)
   - Fast iteration, review catches issues early

2. Inline / resume-later
   - Execute tasks using executing-plans skill
   - Batch execution with checkpoints
   - Suitable if picking up partial work

Which approach?
```

If **Subagent-Driven** — use `subagent-driven-development` skill.
If **Inline** — use `executing-plans` skill.

## Relation to Workflows

- Produces the `design.md` artifact at workflow Step 3 (DESIGN)
- The Coder agent consumes tasks from this plan via `executing-plans` or the Architect orchestrates via `subagent-driven-development`

## Attribution

Portions adapted from [obra/superpowers](https://github.com/obra/superpowers), Copyright © 2025 Jesse Vincent, MIT License.

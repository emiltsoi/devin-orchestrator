---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or git worktree fallback
---

# Using Git Worktrees

## Overview

Ensure work happens in an isolated workspace. Prefer your platform's native worktree tools. Fall back to manual git worktrees only when no native tool is available.

**Core principle:** Detect existing isolation first. Then use native tools. Then fall back to git. Never fight the harness.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an isolated workspace."

## Step 0: Detect Existing Isolation

**Before creating anything, check if you are already in an isolated workspace.**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

**Submodule guard:** `GIT_DIR != GIT_COMMON` is also true inside git submodules. Before concluding "already in a worktree," verify you are not in a submodule:

```bash
# If this returns a path, you're in a submodule, not a worktree — treat as normal repo
git rev-parse --show-superproject-working-tree 2>/dev/null
```

**If `GIT_DIR != GIT_COMMON` (and not a submodule):** You are already in a linked worktree. Skip to Step 2 (Project Setup). Do NOT create another worktree.

Report with branch state:
- On a branch: "Already in isolated workspace at `<path>` on branch `<name>`."
- Detached HEAD: "Already in isolated workspace at `<path>` (detached HEAD, externally managed). Branch creation needed at finish time."

**If `GIT_DIR == GIT_COMMON` (or in a submodule):** You are in a normal repo checkout.

Has the user already indicated their worktree preference in your instructions? If not, ask for consent before creating a worktree:

> "Would you like me to set up an isolated worktree? It protects your current branch from changes."

Honor any existing declared preference without asking. If the user declines consent, work in place and skip to Step 2.

## Step 1: Create Isolated Workspace

**You have two mechanisms. Try them in this order.**

### 1a. Native Worktree Tools (preferred)

If your platform provides a native worktree mechanism (e.g., Windsurf workspaces, Claude Code workspaces), use it instead of git worktrees. Native tools are platform-specific and should be used when available.

### 1b. Git Worktree Fallback

If no native tool is available, use git worktrees:

```bash
# Create a new worktree on a new branch
git worktree add -b feature/<name> ../worktrees/<name>
```

## Step 2: Project Setup

Auto-detect and run appropriate setup:

```bash
# Node.js
if [ -f package.json ]; then npm install; fi

# Rust
if [ -f Cargo.toml ]; then cargo build; fi

# Python
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ]; then poetry install; fi

# Go
if [ -f go.mod ]; then go mod download; fi
```

## Step 3: Verify Clean Baseline

Run tests to ensure workspace starts clean:

```bash
# Use project-appropriate command
npm test / cargo test / pytest / go test ./...
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

## Report

After completion, report:
- Worktree location
- Branch state
- Setup commands run
- Test baseline status
- Ready status

## Quick Reference

| Check | Command | Interpretation |
|-------|---------|----------------|
| Already isolated? | `GIT_DIR != GIT_COMMON` | Yes if true (and not submodule) |
| In submodule? | `git rev-parse --show-superproject-working-tree` | Yes if returns path |
| Create worktree | `git worktree add -b <branch> <path>` | Creates isolated workspace |
| Clean baseline? | Run project tests | Must pass before proceeding |

## Common Mistakes

**Fighting the harness:** If the platform provides native worktree tools, use them. Don't force git worktrees when the platform has its own mechanism.

**Skipping detection:** Always check for existing isolation before creating a worktree. Creating nested worktrees causes problems.

**Skipping ignore verification:** If the platform uses `.gitignore` or similar, verify it's working before proceeding.

**Assuming directory location:** Don't assume worktrees are in a specific location. Detect the actual location.

**Proceeding with failing tests:** If the baseline tests fail, don't proceed. Investigate or ask the user.

## Red Flags

- Creating a worktree when already in a worktree
- Proceeding with failing baseline tests
- Fighting the platform's native worktree mechanism
- Not asking for consent before creating a worktree

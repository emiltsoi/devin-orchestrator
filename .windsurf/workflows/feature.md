---
description: Simple feature workflow with design and implementation
---

# Feature Workflow

A simple workflow for implementing features with design approval and implementation.

## Steps

1. **Context** - Load skills and initialize session
2. **Requirement** - Use brainstorming skill to create requirement.md
3. **Design** - Use writing-plans skill to create design.md
4. **Implementation** - Implement per design
5. **Summary** - Write summary.md

## Usage

Run `/feature` to start a new feature session. The workflow will guide you through each step with appropriate skill invocations and user gates.

## Session ID Format

FEATURE-NNN (auto-allocated)

## Branch Policy

Creates branch: `feature/<session_id>`
Policy: implementation_branch_committable

# Deployment Guide: Canonical Source + Workspace Deployment

**Purpose:** Document the canonical source deployment model for orchestrator–worker workflows.

## Canonical Source

The canonical source of truth for workflow definitions is the `devin-orchestrator` repository:
- `workflows/*.manifest.yaml` - Structured workflow manifests
- `workflows/*.runbook.md` - Agent-facing orchestration runbooks
- `skills/*` - Skill definitions (.yaml) and narratives (.md)
- `workflow-engine/*` - Deterministic tools and dispatch mechanics

## Workspace Deployment

When deploying workflow changes to a workspace:

1. **Update canonical source first:**
   - Modify `workflows/<workflow>.manifest.yaml` (structured source)
   - Modify `workflows/<workflow>.runbook.md` (agent-facing companion)
   - Ensure parity between manifest and runbook

2. **Deploy to workspace:**
   - Copy `workflows/<workflow>.manifest.yaml` to workspace
   - Copy `workflows/<workflow>.runbook.md` to workspace
   - Copy `skills/*` to workspace (if skill changes)
   - Copy `workflow-engine/*` to workspace (if tool changes)

3. **Validate deployment:**
   - Run parity test: manifest.stages == runbook.stages
   - Verify all required skills are present
   - Verify all deterministic tools are present

## Deployment Workflow

```bash
# In canonical source (devin-orchestrator)
cd /path/to/devin-orchestrator

# 1. Update manifest
vim workflows/feature.manifest.yaml

# 2. Update runbook
vim workflows/feature.runbook.md

# 3. Validate parity
python -m workflow_engine.parity_test workflows/feature.manifest.yaml workflows/feature.runbook.md

# 4. Commit changes
git add workflows/feature.manifest.yaml workflows/feature.runbook.md
git commit -m "Update feature workflow: <description>"

# 5. Deploy to workspace
cp workflows/feature.manifest.yaml /path/to/workspace/workflows/
cp workflows/feature.runbook.md /path/to/workspace/workflows/
```

## Parity Test

The parity test ensures manifest and runbook agree:
- Stages match (step_0 through step_N)
- Skills match per stage
- Required artifacts match per stage
- Gates match per stage

If parity fails, the deployment is blocked.

## Canonical Source Invariant

The canonical source (devin-orchestrator) is always the authoritative source. Workspace copies are deployed from canonical source and should not be modified independently.

## Rollback

If a deployment causes issues:
1. Revert canonical source changes
2. Re-deploy previous version to workspace
3. Verify parity
4. Resume workflow execution

## Versioning

Workflow definitions are versioned via git:
- `manifest.yaml` includes `schema_version` field
- `runbook.md` includes `schema version` in header
- Breaking changes require schema version bump

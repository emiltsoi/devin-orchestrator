# Deployment Guide: Hybrid Global + Local Override Deployment

**Purpose:** Document the hybrid deployment model for orchestrator–worker workflows.

## Deployment Model

The hybrid deployment model combines global installation with optional per-workspace overrides:

- **Global Installation**: Skills, workflows, and workflow engine are installed to `~/.devin-orchestrator/` and serve as the canonical source for all workspaces
- **Local Overrides**: Optional per-workspace workflow overrides via `.devin/workflows/` for workspace-specific customization
- **Single Source of Truth**: Global installation is the authoritative source; local overrides provide flexibility

## Global Installation

The canonical source of truth is installed globally:

```bash
# Install devin-orchestrator globally
python install.py

# Or use automated installation
python install_automated.py
```

This installs to `~/.devin-orchestrator/`:
- `skills/*` - Skill definitions (.yaml) and narratives (.md)
- `workflows/*.manifest.yaml` - Structured workflow manifests
- `workflows/*.runbook.md` - Agent-facing orchestration runbooks
- `workflow-engine/*` - Deterministic tools and dispatch mechanics
- `config.yaml` - Configuration file

## Local Overrides (Optional)

For workspace-specific workflow customization:

```bash
# Create local overrides directory
mkdir -p .devin/workflows

# Copy specific workflow manifests to override
cp ~/.devin-orchestrator/workflows/superpower.manifest.yaml .devin/workflows/

# Modify the local override as needed
vim .devin/workflows/superpower.manifest.yaml
```

**Note**: Local overrides are optional. Most workspaces can use the global installation directly.

## Deployment Workflow

### Updating Global Installation

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

# 5. Reinstall globally
python install.py
```

### Adding Local Override

```bash
# In workspace
cd /path/to/workspace

# 1. Create local overrides directory
mkdir -p .devin/workflows

# 2. Copy workflow to override
cp ~/.devin-orchestrator/workflows/superpower.manifest.yaml .devin/workflows/

# 3. Modify local override
vim .devin/workflows/superpower.manifest.yaml

# 4. Test the override
# (The system will use .devin/workflows/superpower.manifest.yaml instead of global)
```

## Parity Test

The parity test ensures manifest and runbook agree:
- Stages match (step_0 through step_N)
- Skills match per stage
- Required artifacts match per stage
- Gates match per stage

If parity fails, the deployment is blocked.

## Resolution Order

When loading workflows, the system checks in this order:
1. `.devin/workflows/<workflow>.manifest.yaml` (local override, if exists)
2. `~/.devin-orchestrator/workflows/<workflow>.manifest.yaml` (global source)

This allows workspace-specific customization while maintaining a global baseline.

## Rollback

### Global Rollback

If a global update causes issues:
1. Revert canonical source changes
2. Reinstall globally: `python install.py`
3. Verify all workspaces work correctly

### Local Override Rollback

If a local override causes issues:
1. Delete the local override: `rm .devin/workflows/<workflow>.manifest.yaml`
2. The system will fall back to the global version
3. Verify the workspace works correctly

## Versioning

Workflow definitions are versioned via git:
- `manifest.yaml` includes `schema_version` field
- `runbook.md` includes `schema version` in header
- Breaking changes require schema version bump
- Global installation tracks version via git commit hash

## Best Practices

- **Prefer Global**: Use global installation for most workflows
- **Local for Customization**: Use local overrides only for workspace-specific needs
- **Document Overrides**: Document why a local override exists in `.devin/workflows/README.md`
- **Keep Overrides Minimal**: Override only what's necessary, not entire workflows
- **Sync Regularly**: Reinstall globally regularly to get updates

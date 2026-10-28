# Backup and Recovery Procedures for devin-orchestrator

This document outlines the backup strategy and recovery procedures for the devin-orchestrator system.

## Overview

The devin-orchestrator system contains data worth protecting:
- **Session data**: Work sessions, task progress, and intermediate artifacts
- **Configuration files**: System config, skill definitions, workflow manifests
- **Logs**: Orchestration and execution logs for debugging and auditing

All of it lives under the global install root, `~/.devin-orchestrator/`, plus
optional per-workspace overrides in `.devin/workflows/`.

## What to Back Up

| Data | Location | Suggested frequency |
|------|----------|---------------------|
| Session data | `~/.devin-orchestrator/work/` | Daily, or before critical ops |
| Configuration | `~/.devin-orchestrator/config.yaml` | Before any config change |
| Skills/workflows/roles | `~/.devin-orchestrator/{skills,workflows,roles}/` | Weekly (also in git) |
| Logs | `~/.devin-orchestrator/logs/` | Daily if needed |

Suggested retention: 7 daily, 4 weekly, 3 monthly backups.

## Manual Backup

Everything is plain files — a recursive copy is sufficient:

```bash
# Full backup
cp -a ~/.devin-orchestrator backups/devin-orchestrator-$(date +%Y%m%d_%H%M%S)

# Targeted: just sessions and config
mkdir -p backups/partial-$(date +%Y%m%d)
cp -a ~/.devin-orchestrator/work ~/.devin-orchestrator/config.yaml \
      backups/partial-$(date +%Y%m%d)/
```

```powershell
# Windows equivalent
Copy-Item -Recurse "$env:USERPROFILE\.devin-orchestrator" "backups\devin-orchestrator-$(Get-Date -Format yyyyMMdd_HHmmss)"
```

## Recovery Procedures

### Session Recovery

1. **Identify the backup**: locate the timestamped copy
2. **Stop running sessions**: ensure no dispatched runs are active
3. **Restore session data**: copy the session directory back into `~/.devin-orchestrator/work/`
4. **Verify integrity**: check that session state files are consistent
5. **Resume operations**: restart the MCP server if needed

### Configuration Recovery

1. **Locate the config backup**
2. **Back up the current config first** — always keep the broken state for comparison
3. **Restore** `config.yaml` to `~/.devin-orchestrator/`
4. **Validate**: YAML must parse and paths must resolve
5. **Test**: run `devin-orchestrator-doctor` to verify

### Log Recovery

1. Locate the log backup
2. Copy log files back into `~/.devin-orchestrator/logs/`
3. Verify files are readable and not truncated

## Best Practices

1. **Regular Backups**: schedule a daily copy of the global root
2. **Test Restores**: periodically verify a backup restores cleanly
3. **Off-site Storage**: keep critical backups in more than one location
4. **Before Critical Operations**: always snapshot before upgrades or config changes
5. **Document Changes**: note any configuration change that would need a restore

## Emergency Recovery

In case of system failure:

1. **Assess Damage**: identify what needs to be recovered
2. **Prioritize**: recover `config.yaml` first, then sessions
3. **Use Latest Valid Backup**: newest copy that passes validation
4. **Verify System**: run `devin-orchestrator-doctor` before resuming operations
5. **Reinstall if needed**: `devin-orchestrator install` rebuilds skills/workflows/roles from the package — those don't need backups, only `work/`, `logs/`, and `config.yaml` do

## Troubleshooting

### Backup Fails

- Check disk space availability
- Verify write permissions to the backup destination
- Check if files are locked by running processes

### Recovery Fails

- Verify the backup copy is complete before restoring
- Ensure no processes are using the files being restored
- Check available disk space and file permissions

### Configuration Issues After Recovery

- Validate YAML syntax
- Check file paths in configuration
- Verify that external dependencies are available
- Test with `devin-orchestrator-doctor` before running a workflow

## Contact and Support

For issues with backup and recovery procedures, refer to the main project documentation or contact the system administrator.

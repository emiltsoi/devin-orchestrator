# Backup and Recovery Procedures for devin-orchestrator

This document outlines the backup strategy and recovery procedures for the devin-orchestrator system.

## Overview

The devin-orchestrator system contains critical data including:
- **Session data**: Work sessions, task progress, and intermediate artifacts
- **Configuration files**: System configs, skill definitions, workflow manifests
- **Logs**: Orchestration and execution logs for debugging and auditing

## Backup Strategy

### Session Data Backup

**Location**: `~/.devin-orchestrator/work/` and `work/`

Session directories contain:
- Active and completed work sessions
- Task progress and state
- Generated artifacts and intermediate files
- Session-specific metrics and logs

**Backup Frequency**: Daily (or before critical operations)

**Retention Policy**: 
- Keep last 7 days of daily backups
- Keep weekly backups for 4 weeks
- Keep monthly backups for 3 months

### Configuration Backup

**Locations**:
- `config.yaml` (project root and `~/.devin-orchestrator/`)
- `.devin/workflows/` - Workflow manifests
- `skills/` - Skill definitions and configurations
- `workflows/` - Workflow configurations
- `adapters/` - Adapter configurations
- `contracts/` - Contract definitions

**Backup Frequency**: 
- Before any configuration changes
- Weekly automated backup

**Retention Policy**: Keep last 10 backups

### Log Backup

**Location**: `~/.devin-orchestrator/logs/`

**Backup Frequency**: Daily

**Retention Policy**: Keep last 30 days of logs

## Backup Script

The `backup_script.py` automates the backup process with the following features:
- Configurable backup destinations
- Timestamped backup archives
- Automatic retention policy enforcement
- Compression for space efficiency
- Backup validation and verification

## Recovery Procedures

### Session Recovery

To recover session data:

1. **Identify the backup**: Use the backup timestamp to locate the correct backup
2. **Stop running sessions**: Ensure no active sessions are running
3. **Restore session data**: Extract the session directory from the backup
4. **Verify integrity**: Check that session state is consistent
5. **Resume operations**: Restart the orchestration engine if needed

### Configuration Recovery

To recover configuration files:

1. **Identify the backup**: Locate the configuration backup
2. **Backup current config**: Always backup existing configuration before restore
3. **Restore configuration**: Extract configuration files from backup
4. **Validate configuration**: Ensure YAML files are valid and paths are correct
5. **Test configuration**: Run a test workflow to verify configuration

### Log Recovery

To recover logs:

1. **Identify the backup**: Locate the log backup
2. **Restore logs**: Extract log files to the logs directory
3. **Verify log integrity**: Ensure log files are not corrupted
4. **Restart logging services** if needed

## Automated Backup Script

Run the backup script:
```bash
python backup_script.py
```

Options:
- `--destination`: Specify backup destination (default: `./backups`)
- `--type`: Backup type - `all`, `sessions`, `configs`, `logs` (default: `all`)
- `--compress`: Enable compression (default: True)
- `--retention`: Number of backups to keep (default: per policy)

## Automated Recovery Script

Run the recovery script:
```bash
python recovery_script.py --backup <backup-timestamp> --type <type>
```

Options:
- `--backup`: Backup timestamp to restore from
- `--type`: Recovery type - `all`, `sessions`, `configs`, `logs` (default: `all`)
- `--dry-run`: Show what would be restored without actually restoring
- `--validate-only`: Validate backup integrity without restoring

## Best Practices

1. **Regular Backups**: Schedule automated daily backups
2. **Test Restores**: Periodically test recovery procedures
3. **Off-site Storage**: Store critical backups in multiple locations
4. **Monitor Storage**: Monitor backup storage usage and clean up old backups
5. **Document Changes**: Document any configuration changes that require backup
6. **Before Critical Operations**: Always create a backup before major changes

## Emergency Recovery

In case of system failure:

1. **Assess Damage**: Identify what needs to be recovered
2. **Prioritize**: Recover critical configurations first, then sessions
3. **Use Latest Valid Backup**: Use the most recent backup that passes validation
4. **Verify System**: Test the system after recovery before resuming operations
5. **Document Incident**: Document the recovery process for future reference

## Troubleshooting

### Backup Fails

- Check disk space availability
- Verify write permissions to backup destination
- Check if files are locked by running processes

### Recovery Fails

- Validate backup integrity before recovery
- Ensure no processes are using the files being restored
- Check available disk space
- Verify file permissions

### Configuration Issues After Recovery

- Validate YAML syntax
- Check file paths in configuration
- Verify that external dependencies are available
- Test with a simple workflow before full operation

## Contact and Support

For issues with backup and recovery procedures, refer to the main project documentation or contact the system administrator.
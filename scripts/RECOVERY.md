# Recovery Procedures for devin-orchestrator

This document provides detailed procedures for recovering devin-orchestrator data from backups, including step-by-step instructions for different recovery scenarios.

## Overview

Recovery procedures restore the devin-orchestrator system to a functional state after data loss, corruption, or system failure. This guide covers session recovery, configuration recovery, log recovery, and full system recovery.

## Prerequisites

Before performing any recovery operation:

1. **Stop Running Sessions**: Ensure no active orchestration sessions are running
2. **Backup Current State**: Always backup existing data before recovery
3. **Validate Backup**: Verify backup integrity before restoration
4. **Check Disk Space**: Ensure sufficient space for recovery
5. **Review Permissions**: Verify write access to target directories

## Recovery Tools

### Windows PowerShell
- **Script**: `recovery.ps1`
- **Location**: `scripts/recovery.ps1`
- **Requirements**: PowerShell 5.1+, Windows 10+

### Linux/Mac Bash
- **Script**: `recovery.sh`
- **Location**: `scripts/recovery.sh`
- **Requirements**: Bash 4.0+, common Unix utilities

### Python (Cross-platform)
- **Script**: `../recovery_script.py`
- **Location**: `recovery_script.py`
- **Requirements**: Python 3.6+, zipfile module

## Recovery Scenarios

### Scenario 1: Session Data Recovery

**Use Case**: Recover lost or corrupted session data while preserving configurations.

#### Steps

1. **Identify the Backup**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --list --type sessions
   
   # Linux/Mac
   ./scripts/recovery.sh --list --type sessions
   ```

2. **Validate the Backup**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --validate --backup devin-orchestrator-sessions-20240622_143000.zip
   
   # Linux/Mac
   ./scripts/recovery.sh --validate --backup devin-orchestrator-sessions-20240622_143000.zip
   ```

3. **Perform Dry Run** (Recommended)
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-sessions-20240622_143000.zip --type sessions --dry-run
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-sessions-20240622_143000.zip --type sessions --dry-run
   ```

4. **Execute Recovery**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-sessions-20240622_143000.zip --type sessions
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-sessions-20240622_143000.zip --type sessions
   ```

5. **Verify Recovery**
   - Check session directories exist
   - Verify session metadata is intact
   - Test session loading

#### Recovery Locations
- `work/` → Project work directory
- `~/.devin-orchestrator/work/` → User work directory

### Scenario 2: Configuration Recovery

**Use Case**: Restore configuration files after corruption or unintended changes.

#### Steps

1. **Identify the Backup**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --list --type configs
   
   # Linux/Mac
   ./scripts/recovery.sh --list --type configs
   ```

2. **Backup Current Configuration**
   ```powershell
   # Windows
   Copy-Item config.yaml config.yaml.backup
   Copy-Item .devin .devin.backup -Recurse
   
   # Linux/Mac
   cp config.yaml config.yaml.backup
   cp -r .devin .devin.backup
   ```

3. **Validate the Backup**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --validate --backup devin-orchestrator-configs-20240622_143000.zip
   
   # Linux/Mac
   ./scripts/recovery.sh --validate --backup devin-orchestrator-configs-20240622_143000.zip
   ```

4. **Perform Dry Run**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-configs-20240622_143000.zip --type configs --dry-run
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-configs-20240622_143000.zip --type configs --dry-run
   ```

5. **Execute Recovery**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-configs-20240622_143000.zip --type configs
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-configs-20240622_143000.zip --type configs
   ```

6. **Validate Configuration**
   ```powershell
   # Test YAML syntax
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   
   # Test configuration loading
   python -c "from workflow_engine.config_loader import ConfigLoader; ConfigLoader()"
   ```

7. **Test Configuration**
   - Run a simple test workflow
   - Verify skill loading
   - Check workflow manifests

#### Recovery Locations
- `config.yaml` → Project configuration
- `.devin/` → Devin workflows
- `skills/` → Skill definitions
- `workflows/` → Workflow configurations
- `adapters/` → Adapter configurations
- `contracts/` → Contract definitions
- `~/.devin-orchestrator/*` → User configurations

### Scenario 3: Log Recovery

**Use Case**: Restore lost or corrupted log files for troubleshooting and auditing.

#### Steps

1. **Identify the Backup**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --list --type logs
   
   # Linux/Mac
   ./scripts/recovery.sh --list --type logs
   ```

2. **Validate the Backup**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --validate --backup devin-orchestrator-logs-20240622_143000.zip
   
   # Linux/Mac
   ./scripts/recovery.sh --validate --backup devin-orchestrator-logs-20240622_143000.zip
   ```

3. **Execute Recovery**
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-logs-20240622_143000.zip --type logs
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-logs-20240622_143000.zip --type logs
   ```

4. **Verify Log Integrity**
   - Check log files are not corrupted
   - Verify log format and structure
   - Test log parsing if applicable

#### Recovery Locations
- `~/.devin-orchestrator/logs/` → System logs

### Scenario 4: Full System Recovery

**Use Case**: Complete system restoration after catastrophic failure or migration.

#### Steps

1. **Assess Damage**
   - Identify what components are affected
   - Determine recovery priority
   - Check system dependencies

2. **Select Backup**
   - Choose the most recent valid backup
   - Validate backup integrity
   - Review backup metadata

3. **Prepare System**
   ```powershell
   # Stop all services
   # Ensure no running sessions
   # Clear temporary files
   ```

4. **Recover Configuration First** (Priority 1)
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-full-20240622_143000.zip --type configs
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-full-20240622_143000.zip --type configs
   ```

5. **Validate Configuration**
   - Test configuration loading
   - Verify system dependencies
   - Check external integrations

6. **Recover Session Data** (Priority 2)
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-full-20240622_143000.zip --type sessions
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-full-20240622_143000.zip --type sessions
   ```

7. **Recover Logs** (Priority 3)
   ```powershell
   # Windows
   .\scripts\recovery.ps1 --backup devin-orchestrator-full-20240622_143000.zip --type logs
   
   # Linux/Mac
   ./scripts/recovery.sh --backup devin-orchestrator-full-20240622_143000.zip --type logs
   ```

8. **System Verification**
   - Test orchestration engine startup
   - Run health checks
   - Verify session loading
   - Test workflow execution

9. **Document Recovery**
   - Record recovery actions
   - Note any issues encountered
   - Update recovery procedures if needed

## Advanced Recovery Options

### Selective File Recovery

Recover specific files from a backup:

```powershell
# Extract backup to temporary location
# Windows
Expand-Archive -Path backups\devin-orchestrator-full-20240622_143000.zip -DestinationPath temp_recovery

# Linux/Mac
unzip backups/devin-orchestrator-full-20240622_143000.zip -d temp_recovery

# Copy specific files
# Windows
Copy-Item temp_recovery\config.yaml config.yaml

# Linux/Mac
cp temp_recovery/config.yaml config.yaml
```

### Point-in-Time Recovery

Recover to a specific point in time:

1. **Identify desired backup timestamp**
2. **Validate backup from that time**
3. **Recover using that specific backup**
4. **Verify system state matches expected point**

### Partial Recovery

Recover only specific components:

```powershell
# Recover only skills
.\scripts\recovery.ps1 --backup devin-orchestrator-configs-20240622_143000.zip --type configs --include skills

# Recover only workflows
.\scripts\recovery.ps1 --backup devin-orchestrator-configs-20240622_143000.zip --type configs --include workflows
```

## Recovery Validation

### Post-Recovery Checks

1. **Configuration Validation**
   ```powershell
   # Validate YAML syntax
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   
   # Test configuration loading
   python -c "from workflow_engine.config_loader import ConfigLoader; ConfigLoader()"
   ```

2. **Session Validation**
   ```powershell
   # Check session directories
   ls work/
   
   # Verify session metadata
   python -c "import json; print(json.load(open('work/session-id/metadata.json')))"
   ```

3. **System Health Check**
   ```powershell
   # Run health check
   python workflow-engine/health_check.py
   ```

4. **Integration Test**
   ```powershell
   # Run integration tests
   pytest workflow-engine/test_integration.py
   ```

### Rollback Procedures

If recovery fails or causes issues:

1. **Stop the system**
2. **Restore from backup created before recovery**
3. **Investigate recovery failure**
4. **Attempt alternative recovery method**
5. **Document the issue**

## Troubleshooting

### Recovery Fails

**Symptoms**: Recovery script errors, incomplete restoration

**Solutions**:
- Validate backup integrity before recovery
- Check disk space availability
- Verify file permissions
- Ensure no processes are using target files
- Check for corrupted backup files

### Configuration Issues After Recovery

**Symptoms**: System won't start, workflows fail

**Solutions**:
- Validate YAML syntax
- Check file paths in configuration
- Verify external dependencies
- Test with simple workflow first
- Review configuration changes

### Session Data Corruption

**Symptoms**: Sessions won't load, data appears corrupted

**Solutions**:
- Try recovering from an earlier backup
- Validate session metadata
- Check for partial recovery
- Reconstruct session from logs if possible

### Log Recovery Issues

**Symptoms**: Logs missing or corrupted

**Solutions**:
- Validate log file format
- Check log file permissions
- Verify log directory structure
- Accept data loss for very old logs

## Best Practices

1. **Always Validate**: Never skip backup validation
2. **Dry Run First**: Test recovery with dry-run mode
3. **Backup Before Recovery**: Always backup current state
4. **Document Everything**: Record all recovery actions
5. **Test Regularly**: Practice recovery procedures monthly
6. **Monitor Storage**: Ensure adequate disk space
7. **Plan Rollback**: Have rollback procedure ready
8. **Verify After Recovery**: Always test system after recovery

## Emergency Recovery

### Critical System Failure

**Immediate Actions**:
1. Assess system state and damage
2. Identify recovery priority (configs > sessions > logs)
3. Select most recent valid backup
4. Begin with configuration recovery
5. Verify system functionality
6. Recover remaining data
7. Full system validation

### Data Corruption

**Recovery Strategy**:
1. Identify corruption scope
2. Locate last known good backup
3. Validate backup integrity
4. Perform selective recovery
5. Verify data integrity
6. Update monitoring to detect future corruption

### Ransomware/Malware

**Recovery Strategy**:
1. Isolate affected systems
2. Identify safe backup source
3. Validate backup is not compromised
4. Recover to clean system
5. Scan recovered data
6. Update security measures
7. Implement additional protections

## Recovery Documentation

### Recovery Log Template

```
Date: YYYY-MM-DD HH:MM:SS
Operator: [Name]
Reason: [Recovery reason]
Backup Used: [Backup name]
Recovery Type: [sessions/configs/logs/all]
Actions Taken:
  - [Action 1]
  - [Action 2]
Issues Encountered:
  - [Issue 1]
  - [Issue 2]
Resolution: [Final resolution]
Validation Results: [Pass/Fail]
Next Steps: [Follow-up actions]
```

## Related Documentation

- [BACKUP-STRATEGY.md](BACKUP-STRATEGY.md) - Backup strategy and policies
- [recovery.ps1](recovery.ps1) - Windows recovery script
- [recovery.sh](recovery.sh) - Linux/Mac recovery script
- [../BACKUP-RECOVERY.md](../BACKUP-RECOVERY.md) - General backup/recovery information
- [../ORCHESTRATION-RUNBOOK.md](../ORCHESTRATION-RUNBOOK.md) - System operations guide
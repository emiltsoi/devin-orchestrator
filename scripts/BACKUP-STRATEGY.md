# Backup Strategy for devin-orchestrator

This document outlines the comprehensive backup strategy for the devin-orchestrator system, detailing what data is backed up, when, and how.

## Overview

The devin-orchestrator system manages critical data that must be regularly backed up to ensure business continuity and data integrity. This strategy covers session data, configuration files, and system logs.

## Data Classification

### Critical Data (Tier 1)
**Backup Frequency**: Daily  
**Retention**: 7 days daily, 4 weeks weekly, 3 months monthly

- **Session Data**: Active and completed work sessions, task progress, intermediate artifacts
- **Configuration Files**: System configurations that define orchestration behavior
- **Recent Logs**: Logs from the last 7 days for immediate troubleshooting

### Important Data (Tier 2)
**Backup Frequency**: Weekly  
**Retention**: 10 backups

- **Skill Definitions**: Custom skills and their configurations
- **Workflow Manifests**: Workflow definitions and runbooks
- **Adapter Configurations**: External system integration settings
- **Contract Definitions**: API contracts and schemas

### Archival Data (Tier 3)
**Backup Frequency**: Monthly  
**Retention**: 12 months

- **Historical Logs**: Logs older than 7 days for audit trails
- **Completed Session Archives**: Sessions that are no longer active
- **Deprecated Configurations**: Old configuration versions for reference

## Backup Locations

### Session Data
- **Primary**: `work/` (project root)
- **Secondary**: `~/.devin-orchestrator/work/` (user home directory)
- **Content**: 
  - Active session directories
  - Task progress files
  - Generated artifacts
  - Session-specific metrics
  - Intermediate work products

### Configuration Data
- **Project Configs**:
  - `config.yaml` (project root)
  - `.devin/workflows/` - Workflow manifests
  - `skills/` - Skill definitions
  - `workflows/` - Workflow configurations
  - `adapters/` - Adapter configurations
  - `contracts/` - Contract definitions

- **User Configs**:
  - `~/.devin-orchestrator/config.yaml`
  - `~/.devin-orchestrator/skills/`
  - `~/.devin-orchestrator/workflows/`
  - `~/.devin-orchestrator/workflow-engine/`

### Log Data
- **Location**: `~/.devin-orchestrator/logs/`
- **Content**:
  - Orchestration engine logs
  - Skill execution logs
  - Error logs and stack traces
  - Performance metrics logs
  - Audit trail logs

## Backup Schedule

### Automated Backups

#### Daily Backup (Cron: 0 2 * * *)
- **Time**: 2:00 AM daily
- **Scope**: Session data + recent logs (7 days)
- **Compression**: Enabled
- **Validation**: Post-backup integrity check

#### Weekly Backup (Cron: 0 3 * * 0)
- **Time**: 3:00 AM Sunday
- **Scope**: Full configuration backup + all logs
- **Compression**: Enabled
- **Validation**: Full backup validation

#### Monthly Backup (Cron: 0 4 1 * *)
- **Time**: 4:00 AM on 1st of month
- **Scope**: Complete system backup
- **Compression**: Enabled
- **Validation**: Comprehensive validation test

### Manual Backups

Manual backups should be created:
- Before any configuration changes
- Before software updates
- Before major workflow modifications
- After critical session completions
- Before system migrations

## Backup Methods

### Full Backup
- **Command**: `python backup_script.py --type all`
- **Content**: All data types (sessions, configs, logs)
- **Compression**: ZIP format
- **Size**: Typically 100MB - 1GB depending on usage
- **Time**: 5-15 minutes

### Incremental Backup
- **Command**: `python backup_script.py --type sessions`
- **Content**: Only session data changes
- **Compression**: ZIP format
- **Size**: Typically 10MB - 100MB
- **Time**: 2-5 minutes

### Configuration-Only Backup
- **Command**: `python backup_script.py --type configs`
- **Content**: Configuration files only
- **Compression**: ZIP format
- **Size**: Typically 5MB - 50MB
- **Time**: 1-3 minutes

## Backup Storage

### Local Storage
- **Location**: `./backups/` (project root)
- **Format**: Timestamped ZIP archives
- **Naming**: `devin-orchestrator-{type}-{timestamp}.zip`
- **Access**: Immediate access for quick restores

### Offsite Storage
- **Location**: Cloud storage (S3, Azure Blob, etc.)
- **Sync**: Automated sync after each backup
- **Encryption**: AES-256 encryption at rest
- **Access**: Available for disaster recovery

### Backup Rotation
- **Daily backups**: Keep last 7 days
- **Weekly backups**: Keep last 4 weeks
- **Monthly backups**: Keep last 3 months
- **Archive backups**: Keep last 12 months

## Backup Validation

### Integrity Checks
- **Post-backup validation**: Automatic after each backup
- **Periodic validation**: Weekly validation of random backups
- **Restore testing**: Monthly test restore of oldest backup

### Validation Methods
- **Archive integrity**: ZIP file validation
- **File checksums**: MD5/SHA256 verification
- **Content validation**: YAML syntax checking
- **Structure validation**: Directory structure verification

## Backup Security

### Encryption
- **At rest**: AES-256 encryption for offsite backups
- **In transit**: TLS 1.3 for cloud storage transfers
- **Key management**: Secure key storage with rotation

### Access Control
- **Local backups**: File system permissions (600/700)
- **Cloud backups**: IAM role-based access
- **Audit logging**: All backup/restore operations logged

### Compliance
- **Data retention**: Configurable retention policies
- **Data classification**: Tiered backup approach
- **Privacy**: No sensitive data in backup metadata

## Monitoring and Alerting

### Backup Monitoring
- **Success/failure alerts**: Email/Slack notifications
- **Storage monitoring**: Disk space alerts (80% threshold)
- **Performance monitoring**: Backup duration tracking
- **Validation monitoring**: Integrity check alerts

### Metrics to Track
- Backup success rate (target: >99%)
- Backup duration (baseline: <15 minutes)
- Storage utilization (target: <80%)
- Restore success rate (target: >95%)

## Disaster Recovery

### Recovery Point Objective (RPO)
- **Critical data**: 24 hours (daily backups)
- **Important data**: 7 days (weekly backups)
- **Archival data**: 30 days (monthly backups)

### Recovery Time Objective (RTO)
- **Session recovery**: 1 hour
- **Configuration recovery**: 2 hours
- **Full system recovery**: 4 hours

### Recovery Priorities
1. **Configuration files** (system must be operational)
2. **Active sessions** (current work in progress)
3. **Recent logs** (troubleshooting capability)
4. **Historical data** (archive restoration)

## Best Practices

1. **Test Regularly**: Perform monthly test restores
2. **Document Changes**: Log all configuration changes
3. **Monitor Storage**: Clean up old backups automatically
4. **Secure Backups**: Encrypt sensitive backup data
5. **Multiple Locations**: Store backups in multiple locations
6. **Version Control**: Track backup script versions
7. **Automate**: Automate as much as possible
8. **Review Quarterly**: Review and update strategy quarterly

## Troubleshooting

### Backup Failures
- **Disk space**: Clean up old backups or increase storage
- **Permissions**: Verify write access to backup destination
- **Locked files**: Stop running sessions before backup
- **Corruption**: Validate source data before backup

### Slow Backups
- **Compression**: Disable compression for faster backups
- **Network**: Use local storage for faster backups
- **Exclusions**: Exclude unnecessary files from backup
- **Throttling**: Adjust backup schedule to off-peak hours

### Storage Issues
- **Growth**: Monitor backup size trends
- **Cleanup**: Implement automatic retention policies
- **Compression**: Use higher compression ratios
- **Archiving**: Move old backups to cold storage

## Related Documentation

- [RECOVERY.md](RECOVERY.md) - Recovery procedures
- [backup.ps1](backup.ps1) - Windows backup script
- [backup.sh](backup.sh) - Linux/Mac backup script
- [../BACKUP-RECOVERY.md](../BACKUP-RECOVERY.md) - General backup/recovery info
#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Backup script for devin-orchestrator
.DESCRIPTION
    Creates timestamped backups of sessions, configurations, and logs for devin-orchestrator
.PARAMETER Destination
    Backup destination directory (default: ./backups)
.PARAMETER Type
    Type of backup to perform: all, sessions, configs, logs (default: all)
.PARAMETER Compress
    Enable compression (default: True)
.PARAMETER ProjectRoot
    Project root directory (default: current directory)
.PARAMETER Validate
    Validate an existing backup (provide backup name)
.EXAMPLE
    .\backup.ps1 -Type all -Compress
.EXAMPLE
    .\backup.ps1 -Destination C:\backups -Type sessions
.EXAMPLE
    .\backup.ps1 -Validate devin-orchestrator-full-20240622_143000.zip
#>

[CmdletBinding()]
param(
    [string]$Destination,
    [ValidateSet('all', 'sessions', 'configs', 'logs')]
    [string]$Type = 'all',
    [switch]$Compress = $true,
    [string]$ProjectRoot,
    [string]$Validate
)

# Import required modules
Import-Module Microsoft.PowerShell.Archive

# Configure logging
$LogDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "$timestamp - $Level - $Message"
}

class BackupManager {
    [string]$ProjectRoot
    [string]$BackupDestination
    [System.Collections.Generic.List[string]]$SessionPaths
    [System.Collections.Generic.List[string]]$ConfigPaths
    [System.Collections.Generic.List[string]]$LogPaths
    [hashtable]$RetentionPolicies

    BackupManager([string]$projectRoot, [string]$backupDestination) {
        if ([string]::IsNullOrEmpty($projectRoot)) {
            $this.ProjectRoot = Get-Location
        } else {
            $this.ProjectRoot = $projectRoot
        }

        if ([string]::IsNullOrEmpty($backupDestination)) {
            $this.BackupDestination = Join-Path $this.ProjectRoot "backups"
        } else {
            $this.BackupDestination = $backupDestination
        }

        # Define paths to backup
        $this.SessionPaths = @(
            Join-Path $this.ProjectRoot "work",
            Join-Path $env:USERPROFILE ".devin-orchestrator\work"
        )

        $this.ConfigPaths = @(
            Join-Path $this.ProjectRoot "config.yaml",
            Join-Path $this.ProjectRoot ".devin",
            Join-Path $this.ProjectRoot "skills",
            Join-Path $this.ProjectRoot "workflows",
            Join-Path $this.ProjectRoot "adapters",
            Join-Path $this.ProjectRoot "contracts",
            Join-Path $env:USERPROFILE ".devin-orchestrator\config.yaml",
            Join-Path $env:USERPROFILE ".devin-orchestrator\skills",
            Join-Path $env:USERPROFILE ".devin-orchestrator\workflows",
            Join-Path $env:USERPROFILE ".devin-orchestrator\workflow-engine"
        )

        $this.LogPaths = @(
            Join-Path $env:USERPROFILE ".devin-orchestrator\logs"
        )

        # Retention policies (number of backups to keep)
        $this.RetentionPolicies = @{
            'sessions' = 7
            'configs' = 10
            'logs' = 30
            'all' = 7
        }
    }

    [string] CreateBackupName([string]$backupType) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        return "devin-orchestrator-$backupType-$timestamp"
    }

    [object] BackupDirectory([string]$sourceDir, [string]$backupDir, [bool]$compress) {
        if (-not (Test-Path $sourceDir)) {
            Write-Log "Source directory does not exist: $sourceDir" "WARNING"
            return $false
        }

        try {
            if ($compress) {
                # Create compressed archive
                $archiveName = "$backupDir.zip"
                $archivePath = Join-Path $this.BackupDestination $archiveName
                $parentDir = Split-Path $sourceDir -Parent
                $dirName = Split-Path $sourceDir -Leaf

                Compress-Archive -Path "$sourceDir\*" -DestinationPath $archivePath -Force
                Write-Log "Created compressed backup: $archivePath"
                return $archivePath
            } else {
                # Create directory copy
                $destDir = Join-Path $this.BackupDestination $backupDir
                Copy-Item -Path $sourceDir -Destination $destDir -Recurse -Force
                Write-Log "Created directory backup: $destDir"
                return $destDir
            }
        } catch {
            Write-Log "Failed to backup $sourceDir: $_" "ERROR"
            return $false
        }
    }

    [object] BackupFile([string]$sourceFile, [string]$backupDir) {
        if (-not (Test-Path $sourceFile)) {
            Write-Log "Source file does not exist: $sourceFile" "WARNING"
            return $false
        }

        try {
            $destDir = Join-Path $this.BackupDestination $backupDir
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            $destFile = Join-Path $destDir (Split-Path $sourceFile -Leaf)
            Copy-Item -Path $sourceFile -Destination $destFile -Force
            Write-Log "Backed up file: $sourceFile -> $destFile"
            return $destFile
        } catch {
            Write-Log "Failed to backup $sourceFile: $_" "ERROR"
            return $false
        }
    }

    [string] BackupSessions([bool]$compress) {
        Write-Log "Starting session backup..."
        $backupName = $this.CreateBackupName("sessions")
        $backupDir = Join-Path $this.BackupDestination $backupName
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

        $successCount = 0
        foreach ($sessionPath in $this.SessionPaths) {
            if (Test-Path $sessionPath) {
                $dirName = Split-Path $sessionPath -Leaf
                if ($this.BackupDirectory($sessionPath, (Join-Path $backupName $dirName), $compress)) {
                    $successCount++
                }
            }
        }

        if ($successCount -gt 0) {
            $this.ApplyRetentionPolicy('sessions')
            Write-Log "Session backup completed: $backupName"
            return $backupName
        } else {
            Write-Log "No session data backed up" "WARNING"
            return $null
        }
    }

    [string] BackupConfigs([bool]$compress) {
        Write-Log "Starting configuration backup..."
        $backupName = $this.CreateBackupName("configs")
        $backupDir = Join-Path $this.BackupDestination $backupName
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

        $successCount = 0
        foreach ($configPath in $this.ConfigPaths) {
            if (Test-Path $configPath) {
                $itemName = Split-Path $configPath -Leaf
                if (Test-Path $configPath -PathType Container) {
                    if ($this.BackupDirectory($configPath, (Join-Path $backupName $itemName), $compress)) {
                        $successCount++
                    }
                } else {
                    if ($this.BackupFile($configPath, $backupName)) {
                        $successCount++
                    }
                }
            }
        }

        if ($successCount -gt 0) {
            $this.ApplyRetentionPolicy('configs')
            Write-Log "Configuration backup completed: $backupName"
            return $backupName
        } else {
            Write-Log "No configuration data backed up" "WARNING"
            return $null
        }
    }

    [string] BackupLogs([bool]$compress) {
        Write-Log "Starting log backup..."
        $backupName = $this.CreateBackupName("logs")
        $backupDir = Join-Path $this.BackupDestination $backupName
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

        $successCount = 0
        foreach ($logPath in $this.LogPaths) {
            if (Test-Path $logPath) {
                $dirName = Split-Path $logPath -Leaf
                if ($this.BackupDirectory($logPath, (Join-Path $backupName $dirName), $compress)) {
                    $successCount++
                }
            }
        }

        if ($successCount -gt 0) {
            $this.ApplyRetentionPolicy('logs')
            Write-Log "Log backup completed: $backupName"
            return $backupName
        } else {
            Write-Log "No log data backed up" "WARNING"
            return $null
        }
    }

    [string] BackupAll([bool]$compress) {
        Write-Log "Starting full backup..."
        $backupName = $this.CreateBackupName("full")
        $backupDir = Join-Path $this.BackupDestination $backupName
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

        # Backup each type
        $results = @{
            'sessions' = $this.BackupSessions($compress)
            'configs' = $this.BackupConfigs($compress)
            'logs' = $this.BackupLogs($compress)
        }

        # Create metadata
        $metadata = @{
            'backup_name' = $backupName
            'timestamp' = (Get-Date).ToString("o")
            'backup_type' = 'full'
            'components' = $results
            'project_root' = $this.ProjectRoot
        }

        $metadataFile = Join-Path $backupDir "backup_metadata.json"
        $metadata | ConvertTo-Json -Depth 10 | Out-File -FilePath $metadataFile -Encoding utf8

        if ($compress) {
            # Compress the full backup
            $archiveName = "$backupName.zip"
            $archivePath = Join-Path $this.BackupDestination $archiveName
            Compress-Archive -Path "$backupDir\*" -DestinationPath $archivePath -Force
            Remove-Item -Path $backupDir -Recurse -Force
            Write-Log "Full backup completed and compressed: $archiveName"
        } else {
            Write-Log "Full backup completed: $backupName"
        }

        $this.ApplyRetentionPolicy('all')
        return $backupName
    }

    [void] ApplyRetentionPolicy([string]$backupType) {
        $retentionCount = $this.RetentionPolicies[$backupType]

        # Get list of backups for this type
        $pattern = "devin-orchestrator-$backupType-*"
        $backups = Get-ChildItem -Path $this.BackupDestination -Filter $pattern | 
                   Sort-Object LastWriteTime -Descending

        # Remove old backups
        if ($backups.Count -gt $retentionCount) {
            $oldBackups = $backups[$retentionCount..($backups.Count - 1)]
            foreach ($oldBackup in $oldBackups) {
                try {
                    Remove-Item -Path $oldBackup.FullName -Recurse -Force
                    Write-Log "Removed old backup: $($oldBackup.Name)"
                } catch {
                    Write-Log "Failed to remove old backup $($oldBackup.Name): $_" "ERROR"
                }
            }
        }
    }

    [bool] ValidateBackup([string]$backupName) {
        $backupPath = Join-Path $this.BackupDestination $backupName

        if (-not (Test-Path $backupPath)) {
            Write-Log "Backup not found: $backupPath" "ERROR"
            return $false
        }

        # Check if it's a compressed archive
        if ($backupPath -match '\.zip$') {
            try {
                # Test the zip file
                $archive = [System.IO.Compression.ZipFile]::OpenRead($backupPath)
                $archive.Dispose()
                Write-Log "Backup validation passed: $backupPath"
                return $true
            } catch {
                Write-Log "Backup validation failed: $backupPath - $_" "ERROR"
                return $false
            }
        } else {
            # For directory backups, check if it exists and has content
            if (Test-Path $backupPath -PathType Container) {
                $items = Get-ChildItem -Path $backupPath
                if ($items.Count -gt 0) {
                    Write-Log "Backup validation passed: $backupPath"
                    return $true
                } else {
                    Write-Log "Backup validation failed: $backupPath - empty directory" "ERROR"
                    return $false
                }
            } else {
                Write-Log "Backup validation failed: $backupPath - not a directory" "ERROR"
                return $false
            }
        }
    }
}

# Main execution
try {
    # Initialize backup manager
    $manager = [BackupManager]::new($ProjectRoot, $Destination)

    # Create backup destination if it doesn't exist
    if (-not (Test-Path $manager.BackupDestination)) {
        New-Item -ItemType Directory -Path $manager.BackupDestination -Force | Out-Null
    }

    # Validate backup if requested
    if ($Validate) {
        $success = $manager.ValidateBackup($Validate)
        exit $(if ($success) { 0 } else { 1 })
    }

    # Perform backup based on type
    $backupName = $null
    switch ($Type) {
        'all' {
            $backupName = $manager.BackupAll($Compress)
        }
        'sessions' {
            $backupName = $manager.BackupSessions($Compress)
        }
        'configs' {
            $backupName = $manager.BackupConfigs($Compress)
        }
        'logs' {
            $backupName = $manager.BackupLogs($Compress)
        }
    }

    if ($backupName) {
        Write-Log "Backup completed successfully: $backupName"
        exit 0
    } else {
        Write-Log "Backup failed" "ERROR"
        exit 1
    }
} catch {
    Write-Log "Fatal error: $_" "ERROR"
    exit 1
}
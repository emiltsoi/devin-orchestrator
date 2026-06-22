#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Backup script for devin-orchestrator
.DESCRIPTION
    PowerShell wrapper for Python backup script. Creates timestamped backups of sessions, configurations, and logs for devin-orchestrator.
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

# Build Python command arguments
$pythonArgs = @("backup_script.py")

if ($Destination) {
    $pythonArgs += "--destination", $Destination
}

$pythonArgs += "--type", $Type

if ($Compress) {
    $pythonArgs += "--compress"
} else {
    $pythonArgs += "--no-compress"
}

if ($ProjectRoot) {
    $pythonArgs += "--project-root", $ProjectRoot
}

if ($Validate) {
    $pythonArgs += "--validate", $Validate
}

# Call Python backup script
& python $pythonArgs
exit $LASTEXITCODE

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Recovery script for devin-orchestrator
.DESCRIPTION
    PowerShell wrapper for Python recovery script. Restores sessions, configurations, and logs from backups for devin-orchestrator.
.PARAMETER Backup
    Backup name to restore from (required)
.PARAMETER Type
    Type of recovery to perform: all, sessions, configs, logs (default: all)
.PARAMETER Source
    Backup source directory (default: ./backups)
.PARAMETER ProjectRoot
    Project root directory (default: current directory)
.PARAMETER DryRun
    Show what would be restored without actually restoring
.PARAMETER NoBackup
    Do not backup existing files before restore
.PARAMETER List
    List available backups
.PARAMETER Validate
    Validate backup before recovery
.PARAMETER ValidateOnly
    Only validate backup, do not perform recovery
.EXAMPLE
    .\recovery.ps1 -Backup devin-orchestrator-full-20240622_143000.zip -Type all
.EXAMPLE
    .\recovery.ps1 -List
.EXAMPLE
    .\recovery.ps1 -Backup devin-orchestrator-sessions-20240622_143000.zip -Type sessions -DryRun
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$Backup,
    
    [ValidateSet('all', 'sessions', 'configs', 'logs')]
    [string]$Type = 'all',
    
    [string]$Source,
    [string]$ProjectRoot,
    [switch]$DryRun,
    [switch]$NoBackup = $false,
    [switch]$List,
    [switch]$Validate,
    [switch]$ValidateOnly
)

# Build Python command arguments
$pythonArgs = @("recovery_script.py")

if ($Backup) {
    $pythonArgs += "--backup", $Backup
}

$pythonArgs += "--type", $Type

if ($Source) {
    $pythonArgs += "--source", $Source
}

if ($ProjectRoot) {
    $pythonArgs += "--project-root", $ProjectRoot
}

if ($DryRun) {
    $pythonArgs += "--dry-run"
}

if ($NoBackup) {
    $pythonArgs += "--no-backup"
}

if ($List) {
    $pythonArgs += "--list"
}

if ($Validate) {
    $pythonArgs += "--validate"
}

if ($ValidateOnly) {
    $pythonArgs += "--validate-only"
}

# Call Python recovery script
& python $pythonArgs
exit $LASTEXITCODE

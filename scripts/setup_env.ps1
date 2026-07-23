#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Set up environment variables for devin-orchestrator on Windows

.DESCRIPTION
    This script configures environment variables for devin-orchestrator.
    It can set variables for the current session or persist them for the user.

.PARAMETER GlobalInstallPath
    Path where devin-orchestrator is installed (default: $env:USERPROFILE\.devin-orchestrator)

.PARAMETER Persist
    Persist environment variables to user profile (default: false)

.PARAMETER DevinCliPath
    Path to Devin CLI executable (optional)

.PARAMETER DefaultModel
    Default model to use (default: swe-1.6)

.PARAMETER PermissionMode
    Default permission mode (default: dangerous)

.EXAMPLE
    .\setup_env.ps1
    Set up environment variables for current session only

.EXAMPLE
    .\setup_env.ps1 -Persist -DevinCliPath "C:\Users\user\AppData\Local\devin\cli\bin\devin.exe"
    Set up and persist environment variables with custom Devin CLI path
#>

param(
    [string]$GlobalInstallPath = "$env:USERPROFILE\.devin-orchestrator",
    [switch]$Persist,
    [string]$DevinCliPath,
    [string]$DefaultModel = "swe-1.6",
    [string]$PermissionMode = "dangerous"
)

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Set-EnvironmentVariable {
    param(
        [string]$Name,
        [string]$Value,
        [bool]$Persist
    )

    if ($Persist) {
        # Set for user scope (persistent)
        [Environment]::SetEnvironmentVariable($Name, $Value, "User")
        # Also set for current session
        Set-Item -Path "env:$Name" -Value $Value
        Write-ColorOutput "✓ Set $Name=$Value (persistent)" "Green"
    }
    else {
        # Set for current session only
        Set-Item -Path "env:$Name" -Value $Value
        Write-ColorOutput "✓ Set $Name=$Value (current session)" "Yellow"
    }
}

function Test-Installation {
    param([string]$InstallPath)

    Write-ColorOutput "Checking installation at $InstallPath..." "Cyan"

    if (!(Test-Path $InstallPath)) {
        Write-ColorOutput "✗ Installation path not found: $InstallPath" "Red"
        Write-ColorOutput "Please run install.ps1 first" "Yellow"
        exit 1
    }

    $requiredDirs = @("skills", "workflows", "workflow-engine")
    foreach ($dir in $requiredDirs) {
        $dirPath = Join-Path $InstallPath $dir
        if (!(Test-Path $dirPath)) {
            Write-ColorOutput "✗ Required directory not found: $dir" "Red"
            exit 1
        }
    }

    Write-ColorOutput "✓ Installation verified" "Green"
}

function Update-ConfigFile {
    param(
        [string]$InstallPath,
        [string]$DevinCliPath,
        [string]$DefaultModel,
        [string]$PermissionMode
    )

    Write-ColorOutput "Updating config.yaml..." "Cyan"

    $configPath = Join-Path $InstallPath "config.yaml"

    if (!(Test-Path $configPath)) {
        Write-ColorOutput "⚠ config.yaml not found, skipping" "Yellow"
        return
    }

    $configContent = Get-Content $configPath -Raw

    # Update paths
    $configContent = $configContent -replace 'global_root:.*', "global_root: $InstallPath"
    $configContent = $configContent -replace 'skills_dir:.*', "skills_dir: $InstallPath\skills"
    $configContent = $configContent -replace 'workflows_dir:.*', "workflows_dir: $InstallPath\workflows"
    $configContent = $configContent -replace 'workflow_engine_dir:.*', "workflow_engine_dir: $InstallPath\workflow-engine"
    $configContent = $configContent -replace 'session_work_dir:.*', "session_work_dir: $InstallPath\work"

    # Update Devin CLI path if provided
    if ($DevinCliPath) {
        if ($configContent -match 'devin_cli_path:') {
            $configContent = $configContent -replace 'devin_cli_path:.*', "devin_cli_path: $DevinCliPath"
        }
        else {
            $configContent += "`ndevin_cli_path: $DevinCliPath"
        }
    }

    # Update default model if provided
    if ($DefaultModel) {
        if ($configContent -match 'default_model:') {
            $configContent = $configContent -replace 'default_model:.*', "default_model: $DefaultModel"
        }
        else {
            $configContent += "`ndefault_model: $DefaultModel"
        }
    }

    # Update permission mode if provided
    if ($PermissionMode) {
        if ($configContent -match 'default_permission_mode:') {
            $configContent = $configContent -replace 'default_permission_mode:.*', "default_permission_mode: $PermissionMode"
        }
        else {
            $configContent += "`ndefault_permission_mode: $PermissionMode"
        }
    }

    Set-Content -Path $configPath -Value $configContent
    Write-ColorOutput "✓ config.yaml updated" "Green"
}

function Add-ToPath {
    param(
        [string]$PathToAdd,
        [bool]$Persist
    )

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

    if ($currentPath -notlike "*$PathToAdd*") {
        if ($Persist) {
            $newPath = "$currentPath;$PathToAdd"
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            # Also set for current session
            $env:Path = "$env:Path;$PathToAdd"
            Write-ColorOutput "✓ Added $PathToAdd to PATH (persistent)" "Green"
        }
        else {
            $env:Path = "$env:Path;$PathToAdd"
            Write-ColorOutput "✓ Added $PathToAdd to PATH (current session)" "Yellow"
        }
    }
    else {
        Write-ColorOutput "⚠ $PathToAdd already in PATH" "Yellow"
    }
}

# Main execution
try {
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "devin-orchestrator Environment Setup" "Cyan"
    Write-ColorOutput "========================================" "Cyan"
    Write-Host ""

    Test-Installation -InstallPath $GlobalInstallPath

    # Set environment variables
    Write-ColorOutput "Setting environment variables..." "Cyan"

    Set-EnvironmentVariable -Name "DEVIN_ORCHESTRATOR_ROOT" -Value $GlobalInstallPath -Persist $Persist
    Set-EnvironmentVariable -Name "DEVIN_ORCHESTRATOR_SKILLS_DIR" -Value "$GlobalInstallPath\skills" -Persist $Persist
    Set-EnvironmentVariable -Name "DEVIN_ORCHESTRATOR_WORKFLOWS_DIR" -Value "$GlobalInstallPath\workflows" -Persist $Persist
    Set-EnvironmentVariable -Name "DEVIN_ORCHESTRATOR_WORKFLOW_ENGINE_DIR" -Value "$GlobalInstallPath\workflow-engine" -Persist $Persist
    Set-EnvironmentVariable -Name "DEVIN_ORCHESTRATOR_WORK_DIR" -Value "$GlobalInstallPath\work" -Persist $Persist

    if ($DevinCliPath) {
        Set-EnvironmentVariable -Name "DEVIN_CLI_PATH" -Value $DevinCliPath -Persist $Persist
    }

    if ($DefaultModel) {
        Set-EnvironmentVariable -Name "DEVIN_DEFAULT_MODEL" -Value $DefaultModel -Persist $Persist
    }

    if ($PermissionMode) {
        Set-EnvironmentVariable -Name "DEVIN_DEFAULT_PERMISSION_MODE" -Value $PermissionMode -Persist $Persist
    }

    # Add to PATH if dispatch script exists
    $dispatchScript = Join-Path $GlobalInstallPath "dispatch_skill.py"
    if (Test-Path $dispatchScript) {
        Add-ToPath -PathToAdd $GlobalInstallPath -Persist $Persist
    }

    # Update config file
    Update-ConfigFile -InstallPath $GlobalInstallPath -DevinCliPath $DevinCliPath -DefaultModel $DefaultModel -PermissionMode $PermissionMode

    Write-Host ""
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "Environment setup complete!" "Green"
    Write-ColorOutput "========================================" "Cyan"
    Write-Host ""

    if ($Persist) {
        Write-ColorOutput "Environment variables have been persisted to your user profile." "Green"
        Write-ColorOutput "You may need to restart your terminal for changes to take effect." "Yellow"
    }
    else {
        Write-ColorOutput "Environment variables are set for the current session only." "Yellow"
        Write-ColorOutput "Use -Persist flag to make changes permanent." "Yellow"
    }

    Write-Host ""
    Write-ColorOutput "Current environment variables:" "Cyan"
    Write-Host "DEVIN_ORCHESTRATOR_ROOT=$env:DEVIN_ORCHESTRATOR_ROOT"
    Write-Host "DEVIN_ORCHESTRATOR_SKILLS_DIR=$env:DEVIN_ORCHESTRATOR_SKILLS_DIR"
    Write-Host "DEVIN_ORCHESTRATOR_WORKFLOWS_DIR=$env:DEVIN_ORCHESTRATOR_WORKFLOWS_DIR"
    if ($env:DEVIN_CLI_PATH) {
        Write-Host "DEVIN_CLI_PATH=$env:DEVIN_CLI_PATH"
    }
    if ($env:DEVIN_DEFAULT_MODEL) {
        Write-Host "DEVIN_DEFAULT_MODEL=$env:DEVIN_DEFAULT_MODEL"
    }
}
catch {
    Write-ColorOutput "✗ Environment setup failed: $_" "Red"
    exit 1
}

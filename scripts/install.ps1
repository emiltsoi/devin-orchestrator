#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install or update devin-orchestrator on Windows

.DESCRIPTION
    This script installs devin-orchestrator globally to the user's home directory
    and sets up the current workspace with workflow manifests.

.PARAMETER GlobalInstallPath
    Path where devin-orchestrator will be installed globally (default: $env:USERPROFILE\.devin-orchestrator)

.PARAMETER WorkspacePath
    Path to the workspace to set up (default: current directory)

.PARAMETER SkipWorkspaceSetup
    Skip workspace setup if specified

.EXAMPLE
    .\install.ps1
    Install to default location and setup current workspace

.EXAMPLE
    .\install.ps1 -GlobalInstallPath "C:\devin-orchestrator" -WorkspacePath "C:\my-project"
    Install to custom location and setup specific workspace
#>

param(
    [string]$GlobalInstallPath = "$env:USERPROFILE\.devin-orchestrator",
    [string]$WorkspacePath = (Get-Location).Path,
    [switch]$SkipWorkspaceSetup
)

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-Prerequisites {
    Write-ColorOutput "Checking prerequisites..." "Cyan"

    # Check Python
    try {
        $pythonVersion = python --version 2>&1
        Write-ColorOutput "✓ Python found: $pythonVersion" "Green"
    }
    catch {
        Write-ColorOutput "✗ Python not found. Please install Python 3.8 or higher." "Red"
        exit 1
    }

    # Check Git
    try {
        $gitVersion = git --version 2>&1
        Write-ColorOutput "✓ Git found: $gitVersion" "Green"
    }
    catch {
        Write-ColorOutput "✗ Git not found. Please install Git." "Red"
        exit 1
    }

    # Check pip
    try {
        $pipVersion = pip --version 2>&1
        Write-ColorOutput "✓ pip found: $pipVersion" "Green"
    }
    catch {
        Write-ColorOutput "✗ pip not found. Please install pip." "Red"
        exit 1
    }

    Write-ColorOutput "All prerequisites satisfied." "Green"
}

function Install-Dependencies {
    Write-ColorOutput "Installing Python dependencies..." "Cyan"

    $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    $requirementsPath = Join-Path $scriptPath "..\requirements.txt"

    if (Test-Path $requirementsPath) {
        pip install -r $requirementsPath
        Write-ColorOutput "✓ Dependencies installed" "Green"
    }
    else {
        Write-ColorOutput "⚠ requirements.txt not found, skipping dependency installation" "Yellow"
    }
}

function Install-Global {
    param([string]$InstallPath)

    Write-ColorOutput "Installing devin-orchestrator to $InstallPath..." "Cyan"

    # Create installation directory
    if (!(Test-Path $InstallPath)) {
        New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
        Write-ColorOutput "✓ Created installation directory" "Green"
    }

    # Copy core directories
    $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectRoot = Split-Path -Parent $scriptPath

    $directoriesToCopy = @(
        "skills",
        "workflows",
        "workflow-engine",
        "adapters",
        "contracts"
    )

    foreach ($dir in $directoriesToCopy) {
        $sourcePath = Join-Path $projectRoot $dir
        $destPath = Join-Path $InstallPath $dir

        if (Test-Path $sourcePath) {
            if (Test-Path $destPath) {
                Remove-Item $destPath -Recurse -Force
            }
            Copy-Item -Path $sourcePath -Destination $destPath -Recurse -Force
            Write-ColorOutput "✓ Copied $dir" "Green"
        }
        else {
            Write-ColorOutput "⚠ $dir not found, skipping" "Yellow"
        }
    }

    # Copy individual files
    $filesToCopy = @(
        "dispatch_skill.py",
        "config.yaml"
    )

    foreach ($file in $filesToCopy) {
        $sourcePath = Join-Path $projectRoot $file
        $destPath = Join-Path $InstallPath $file

        if (Test-Path $sourcePath) {
            Copy-Item -Path $sourcePath -Destination $destPath -Force
            Write-ColorOutput "✓ Copied $file" "Green"
        }
        else {
            Write-ColorOutput "⚠ $file not found, skipping" "Yellow"
        }
    }

    # Create work directory
    $workPath = Join-Path $InstallPath "work"
    if (!(Test-Path $workPath)) {
        New-Item -ItemType Directory -Path $workPath -Force | Out-Null
        Write-ColorOutput "✓ Created work directory" "Green"
    }

    Write-ColorOutput "✓ Global installation complete" "Green"
}

function Setup-Workspace {
    param([string]$Workspace, [string]$GlobalPath)

    Write-ColorOutput "Setting up workspace at $Workspace..." "Cyan"

    # Create .devin/workflows directory
    $devinWorkflowsPath = Join-Path $Workspace ".devin\workflows"
    if (!(Test-Path $devinWorkflowsPath)) {
        New-Item -ItemType Directory -Path $devinWorkflowsPath -Force | Out-Null
        Write-ColorOutput "✓ Created .devin/workflows directory" "Green"
    }

    # Copy workflow manifests
    $globalWorkflowsPath = Join-Path $GlobalPath "workflows"
    if (Test-Path $globalWorkflowsPath) {
        $manifestFiles = Get-ChildItem -Path $globalWorkflowsPath -Filter "*.manifest.yaml"

        foreach ($manifest in $manifestFiles) {
            $destPath = Join-Path $devinWorkflowsPath $manifest.Name
            Copy-Item -Path $manifest.FullName -Destination $destPath -Force
            Write-ColorOutput "✓ Copied $($manifest.Name)" "Green"
        }
    }
    else {
        Write-ColorOutput "⚠ Global workflows directory not found" "Yellow"
    }

    Write-ColorOutput "✓ Workspace setup complete" "Green"
}

function Update-Config {
    param([string]$InstallPath)

    Write-ColorOutput "Updating configuration..." "Cyan"

    $configPath = Join-Path $InstallPath "config.yaml"

    if (Test-Path $configPath) {
        $configContent = Get-Content $configPath -Raw

        # Update paths in config
        $configContent = $configContent -replace 'global_root:.*', "global_root: $InstallPath"
        $configContent = $configContent -replace 'skills_dir:.*', "skills_dir: $InstallPath\skills"
        $configContent = $configContent -replace 'workflows_dir:.*', "workflows_dir: $InstallPath\workflows"
        $configContent = $configContent -replace 'workflow_engine_dir:.*', "workflow_engine_dir: $InstallPath\workflow-engine"
        $configContent = $configContent -replace 'session_work_dir:.*', "session_work_dir: $InstallPath\work"

        Set-Content -Path $configPath -Value $configContent
        Write-ColorOutput "✓ Configuration updated" "Green"
    }
    else {
        Write-ColorOutput "⚠ config.yaml not found" "Yellow"
    }
}

# Main execution
try {
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "devin-orchestrator Installation Script" "Cyan"
    Write-ColorOutput "========================================" "Cyan"
    Write-Host ""

    Test-Prerequisites
    Install-Dependencies
    Install-Global -InstallPath $GlobalInstallPath
    Update-Config -InstallPath $GlobalInstallPath

    if (-not $SkipWorkspaceSetup) {
        Setup-Workspace -Workspace $WorkspacePath -GlobalPath $GlobalInstallPath
    }

    Write-Host ""
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "Installation complete!" "Green"
    Write-ColorOutput "========================================" "Cyan"
    Write-Host ""
    Write-ColorOutput "Global installation: $GlobalInstallPath" "White"
    Write-ColorOutput "Workspace: $WorkspacePath" "White"
    Write-Host ""
    Write-ColorOutput "Next steps:" "Cyan"
    Write-ColorOutput "1. Update $GlobalInstallPath\config.yaml with your Devin CLI path" "White"
    Write-ColorOutput "2. Set environment variables if needed" "White"
    Write-ColorOutput "3. Run workflows using Cascade" "White"
}
catch {
    Write-ColorOutput "✗ Installation failed: $_" "Red"
    exit 1
}

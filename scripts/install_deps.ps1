#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install Python dependencies for devin-orchestrator on Windows

.DESCRIPTION
    This script installs all required Python dependencies for devin-orchestrator.
    It can install from requirements.txt or individual packages.

.PARAMETER RequirementsPath
    Path to requirements.txt file (default: ../requirements.txt)

.PARAMETER Upgrade
    Upgrade packages to latest versions

.PARAMETER Dev
    Install development dependencies

.PARAMETER User
    Install to user directory

.EXAMPLE
    .\install_deps.ps1
    Install dependencies from requirements.txt

.EXAMPLE
    .\install_deps.ps1 -Upgrade -User
    Upgrade and install to user directory
#>

param(
    [string]$RequirementsPath,
    [switch]$Upgrade,
    [switch]$Dev,
    [switch]$User
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

function Install-FromRequirements {
    param(
        [string]$ReqPath,
        [bool]$Upgrade,
        [bool]$User
    )

    if ([string]::IsNullOrEmpty($ReqPath)) {
        $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
        $ReqPath = Join-Path $scriptPath "..\requirements.txt"
    }

    if (!(Test-Path $ReqPath)) {
        Write-ColorOutput "✗ requirements.txt not found at: $ReqPath" "Red"
        exit 1
    }

    Write-ColorOutput "Installing dependencies from $ReqPath..." "Cyan"

    $pipArgs = @("install", "-r", $ReqPath)

    if ($Upgrade) {
        $pipArgs += "--upgrade"
    }

    if ($User) {
        $pipArgs += "--user"
    }

    try {
        & pip @pipArgs
        Write-ColorOutput "✓ Dependencies installed successfully" "Green"
    }
    catch {
        Write-ColorOutput "✗ Failed to install dependencies: $_" "Red"
        exit 1
    }
}

function Install-CoreDependencies {
    param([bool]$Upgrade, [bool]$User)

    Write-ColorOutput "Installing core dependencies..." "Cyan"

    $corePackages = @(
        "PyYAML>=5.1"
    )

    $pipArgs = @("install")
    if ($Upgrade) { $pipArgs += "--upgrade" }
    if ($User) { $pipArgs += "--user" }
    $pipArgs += $corePackages

    try {
        & pip @pipArgs
        Write-ColorOutput "✓ Core dependencies installed" "Green"
    }
    catch {
        Write-ColorOutput "✗ Failed to install core dependencies: $_" "Red"
        exit 1
    }
}

function Install-DevDependencies {
    param([bool]$Upgrade, [bool]$User)

    Write-ColorOutput "Installing development dependencies..." "Cyan"

    $devPackages = @(
        "pytest>=7.0.0",
        "pytest-cov>=4.0.0",
        "ruff>=0.1.0",
        "bandit>=1.7.0",
        "safety>=2.0.0",
        "pip-audit>=2.0.0"
    )

    $pipArgs = @("install")
    if ($Upgrade) { $pipArgs += "--upgrade" }
    if ($User) { $pipArgs += "--user" }
    $pipArgs += $devPackages

    try {
        & pip @pipArgs
        Write-ColorOutput "✓ Development dependencies installed" "Green"
    }
    catch {
        Write-ColorOutput "✗ Failed to install development dependencies: $_" "Red"
        exit 1
    }
}

function Show-InstalledPackages {
    Write-ColorOutput "Installed packages:" "Cyan"
    pip list
}

# Main execution
try {
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "devin-orchestrator Dependency Installer" "Cyan"
    Write-ColorOutput "========================================" "Cyan"
    Write-Host ""

    Test-Prerequisites

    if ($Dev) {
        Install-DevDependencies -Upgrade $Upgrade -User $User
    }
    elseif ([string]::IsNullOrEmpty($RequirementsPath)) {
        # Default: install from requirements.txt
        Install-FromRequirements -ReqPath $RequirementsPath -Upgrade $Upgrade -User $User
    }
    else {
        # Custom requirements path
        Install-FromRequirements -ReqPath $RequirementsPath -Upgrade $Upgrade -User $User
    }

    # Always install core dependencies if not using requirements.txt
    if (![string]::IsNullOrEmpty($RequirementsPath) -and !(Test-Path $RequirementsPath)) {
        Install-CoreDependencies -Upgrade $Upgrade -User $User
    }

    Write-Host ""
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "Dependency installation complete!" "Green"
    Write-ColorOutput "========================================" "Cyan"
    Write-Host ""

    Show-InstalledPackages
}
catch {
    Write-ColorOutput "✗ Dependency installation failed: $_" "Red"
    exit 1
}

# Deployment Scripts

This directory contains platform-specific deployment automation scripts for devin-orchestrator.

## Script Overview

### Installation Scripts

- **`install.ps1`** (Windows) - Main installation script for Windows
- **`install.sh`** (Linux/Mac) - Main installation script for Linux and macOS

These scripts handle the complete installation process:
- Check prerequisites (Python, Git, pip)
- Install Python dependencies
- Copy core directories to global installation path
- Set up workspace with workflow manifests
- Update configuration files

### Environment Setup Scripts

- **`setup_env.ps1`** (Windows) - Environment variable configuration for Windows
- **`setup_env.sh`** (Linux/Mac) - Environment variable configuration for Linux and macOS

These scripts configure environment variables:
- Set `DEVIN_ORCHESTRATOR_ROOT` and related paths
- Configure Devin CLI path
- Set default model and permission mode
- Optionally persist to user profile

### Dependency Installation Scripts

- **`install_deps.ps1`** (Windows) - Python dependency installation for Windows
- **`install_deps.sh`** (Linux/Mac) - Python dependency installation for Linux and macOS

These scripts install Python dependencies:
- Install from requirements.txt by default
- Can install development dependencies
- Support upgrade and user installation options

## Quick Start

### Windows

```powershell
# Complete installation
.\scripts\install.ps1
.\scripts\setup_env.ps1 -Persist
.\scripts\install_deps.ps1
```

### Linux/Mac

```bash
# Make scripts executable (first time only)
chmod +x scripts/*.sh

# Complete installation
./scripts/install.sh
./scripts/setup_env.sh --persist
./scripts/install_deps.sh
```

## Script Options

### install.ps1 / install.sh

**Windows:**
```powershell
.\scripts\install.ps1 [-GlobalInstallPath <path>] [-WorkspacePath <path>] [-SkipWorkspaceSetup]
```

**Linux/Mac:**
```bash
./scripts/install.sh [--global-path PATH] [--workspace-path PATH] [--skip-workspace-setup]
```

### setup_env.ps1 / setup_env.sh

**Windows:**
```powershell
.\scripts\setup_env.ps1 [-GlobalInstallPath <path>] [-Persist] [-DevinCliPath <path>] [-DefaultModel <model>] [-PermissionMode <mode>]
```

**Linux/Mac:**
```bash
./scripts/setup_env.sh [--global-path PATH] [--persist] [--devin-cli-path PATH] [--default-model MODEL] [--permission-mode MODE]
```

### install_deps.ps1 / install_deps.sh

**Windows:**
```powershell
.\scripts\install_deps.ps1 [-RequirementsPath <path>] [-Upgrade] [-Dev] [-User]
```

**Linux/Mac:**
```bash
./scripts/install_deps.sh [--requirements-path PATH] [--upgrade] [--dev] [--user]
```

## Default Paths

- **Windows:** `C:\Users\<username>\.devin-orchestrator`
- **Linux/Mac:** `~/.devin-orchestrator`

## Troubleshooting

### Script Execution Permission (Linux/Mac)

If you get "Permission denied" when running scripts:
```bash
chmod +x scripts/*.sh
```

### PowerShell Execution Policy (Windows)

If you get "execution of scripts is disabled" error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Python Not Found

Ensure Python 3.8 or higher is installed and available in your PATH:
```bash
python --version  # Windows
python3 --version  # Linux/Mac
```

## See Also

- [INSTALL.md](../INSTALL.md) - Complete installation guide
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment guide

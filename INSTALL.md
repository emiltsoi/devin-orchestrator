# Installation Guide

**See Also:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment model and workflow updates
- [ARCHITECTURE.md](ARCHITECTURE.md) - Core abstractions and design
- [AGENT-INSTALL.md](AGENT-INSTALL.md) - Agent-specific installation guide

## Quick Start

### Option 1: Automated Installation (Recommended)

Run the automated installation script from any workspace:

```bash
python install_automated.py
```

This will:
1. Clone the repository (if not already cloned)
2. Install globally to `~/.devin-orchestrator/`
3. Set up the current workspace with workflow manifests

### Option 2: Deployment Scripts (New)

Use the platform-specific deployment scripts in the `scripts/` directory:

#### Windows
```powershell
# Install devin-orchestrator
.\scripts\install.ps1

# Set up environment variables
.\scripts\setup_env.ps1 -Persist

# Install dependencies
.\scripts\install_deps.ps1
```

#### Linux/Mac
```bash
# Install devin-orchestrator
./scripts/install.sh

# Set up environment variables
./scripts/setup_env.sh --persist

# Install dependencies
./scripts/install_deps.sh
```

### Option 3: Manual Installation

#### 1. Clone the Repository
```bash
git clone <devin-orchestrator-url>
cd devin-orchestrator
```

#### 2. Install Globally
```bash
python install.py
```

This installs devin-orchestrator to `~/.devin-orchestrator/`:
- Skills: `~/.devin-orchestrator/skills/`
- Workflows: `~/.devin-orchestrator/workflows/`
- Workflow Engine: `~/.devin-orchestrator/workflow-engine/`
- Config: `~/.devin-orchestrator/config.yaml`

### 3. Setup Workspace (Optional - for local overrides)
For each workspace where you want to use devin-orchestrator:

```bash
# Create .devin/workflows directory (optional - for local overrides)
mkdir -p .devin/workflows

# Copy workflow manifests (optional - for local overrides)
cp ~/.devin-orchestrator/workflows/superpower.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/rca.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/pr_review.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/code_review.manifest.yaml .devin/workflows/
```

Note: This step is optional. The canonical source is `~/.devin-orchestrator/workflows/`. Copying to `.devin/workflows/` allows per-workspace overrides.

## Usage

### Cascade Workflow Execution

**Important:** Cascade uses the orchestrator-worker pattern. Cascade orchestrates the workflow and dispatches skills to Devin via the bash tool.

When Cascade loads a workflow, it will:
1. Read the manifest from `~/.devin-orchestrator/workflows/` (canonical) or `.devin/workflows/` (local override)
2. Load the orchestrate-superpower skill
3. For each stage: dispatch skill via `dispatch_skill.py` using the bash tool
4. Reason through results and make triage decisions
5. Handle gates and structural floor validation

**Cascade is the orchestrator, Devin is the worker.** Cascade dispatches to Devin via subprocess calls.

### Example Dispatch

```bash
python ~/.devin-orchestrator/dispatch_skill.py brainstorming SUPERPOWER-001 ~/.devin-orchestrator/work/SUPERPOWER-001 false true
```

Parameters:
- `skill_name`: Name of the skill (e.g., brainstorming, writing-plans)
- `session_id`: Session identifier
- `workspace`: Path to session directory
- `is_reviewer`: true for reviewer stages, false otherwise
- `demo_mode`: true for testing, false for production

## Configuration

Edit `~/.devin-orchestrator/config.yaml` to customize. The config file supports environment variable substitution using `${VAR}` or `${VAR:-default}` syntax.

### Cross-Platform Configuration

**Option 1: Edit config.yaml directly**
```yaml
global_root: ~/.devin-orchestrator
skills_dir: ~/.devin-orchestrator/skills
workflows_dir: ~/.devin-orchestrator/workflows
workflow_engine_dir: ~/.devin-orchestrator/workflow-engine

# Windows
devin_cli_path: C:/Users/<username>/AppData/Local/devin/cli/bin/devin.exe
# Linux/macOS
# devin_cli_path: ~/.local/bin/devin

default_model: swe-1.6
default_permission_mode: dangerous

session_work_dir: ~/.devin-orchestrator/work
```

**Option 2: Use environment variables (recommended for multi-user setups)**
```yaml
devin_cli_path: ${DEVIN_CLI_PATH}
default_model: ${DEVIN_DEFAULT_MODEL:-swe-1.6}
default_permission_mode: ${DEVIN_DEFAULT_PERMISSION_MODE:-dangerous}
```

**Option 3: Use config.yaml.template**
```bash
cp config.yaml.template config.yaml
# Edit config.yaml with your specific paths
```

### Environment Variables

Override config with environment variables:

```bash
# Windows (PowerShell)
$env:DEVIN_CLI_PATH = "C:/Users/<username>/AppData/Local/devin/cli/bin/devin.exe"
$env:DEVIN_DEFAULT_MODEL = "swe-1.6"
$env:DEVIN_DEFAULT_PERMISSION_MODE = "dangerous"

# Linux/macOS (Bash)
export DEVIN_CLI_PATH="~/.local/bin/devin"
export DEVIN_DEFAULT_MODEL="swe-1.6"
export DEVIN_DEFAULT_PERMISSION_MODE="dangerous"
```

## Architecture

- **Global Skills**: Stored in `~/.devin-orchestrator/skills/` (no workspace duplication)
- **Global Workflows**: Stored in `~/.devin-orchestrator/workflows/` (canonical source)
- **Local Workflows**: Stored in `.devin/workflows/` (optional - for per-workspace overrides)
- **Global Workflow Engine**: Stored in `~/.devin-orchestrator/workflow-engine/`
- **Dispatch Script**: Stored in `~/.devin-orchestrator/dispatch_skill.py`

**Orchestrator-Worker Pattern:**
- Cascade is the orchestrator (intelligent decision-making)
- Devin is the worker (stateless execution)
- Cascade dispatches to Devin via subprocess calls
- Cascade reasons through results and makes triage decisions

## Deployment Scripts

The `scripts/` directory contains platform-specific deployment automation scripts:

### Install Scripts (`install.ps1` / `install.sh`)

Main installation script that:
- Checks prerequisites (Python, Git, pip)
- Installs Python dependencies
- Copies core directories to global installation path
- Sets up workspace with workflow manifests
- Updates configuration files

**Windows Usage:**
```powershell
.\scripts\install.ps1
.\scripts\install.ps1 -GlobalInstallPath "C:\custom\path" -WorkspacePath "C:\my-project"
.\scripts\install.ps1 -SkipWorkspaceSetup  # Skip workspace setup
```

**Linux/Mac Usage:**
```bash
./scripts/install.sh
./scripts/install.sh --global-path /custom/path --workspace-path /my-project
./scripts/install.sh --skip-workspace-setup  # Skip workspace setup
```

### Environment Setup Scripts (`setup_env.ps1` / `setup_env.sh`)

Configures environment variables for devin-orchestrator:
- Sets `DEVIN_ORCHESTRATOR_ROOT` and related paths
- Configures Devin CLI path
- Sets default model and permission mode
- Optionally persists to user profile

**Windows Usage:**
```powershell
# Current session only
.\scripts\setup_env.ps1

# Persist to user profile
.\scripts\setup_env.ps1 -Persist

# With custom Devin CLI path
.\scripts\setup_env.ps1 -Persist -DevinCliPath "C:\Users\user\AppData\Local\devin\cli\bin\devin.exe"
```

**Linux/Mac Usage:**
```bash
# Current session only
./scripts/setup_env.sh

# Persist to shell config
./scripts/setup_env.sh --persist

# With custom Devin CLI path
./scripts/setup_env.sh --persist --devin-cli-path /usr/local/bin/devin
```

### Dependency Installation Scripts (`install_deps.ps1` / `install_deps.sh`)

Installs Python dependencies:
- Installs from requirements.txt by default
- Can install development dependencies
- Supports upgrade and user installation options

**Windows Usage:**
```powershell
# Install from requirements.txt
.\scripts\install_deps.ps1

# Install development dependencies
.\scripts\install_deps.ps1 -Dev

# Upgrade existing packages
.\scripts\install_deps.ps1 -Upgrade

# Install to user directory
.\scripts\install_deps.ps1 -User
```

**Linux/Mac Usage:**
```bash
# Install from requirements.txt
./scripts/install_deps.sh

# Install development dependencies
./scripts/install_deps.sh --dev

# Upgrade existing packages
./scripts/install_deps.sh --upgrade

# Install to user directory
./scripts/install_deps.sh --user
```

## Updating

To update to the latest version:

```bash
cd devin-orchestrator
git pull
python install.py
```

Or use the deployment scripts:

**Windows:**
```powershell
cd devin-orchestrator
git pull
.\scripts\install.ps1
```

**Linux/Mac:**
```bash
cd devin-orchestrator
git pull
./scripts/install.sh
```

This will overwrite the global installation with the latest skills, workflows, and workflow engine.

## Troubleshooting

### Skill Not Found
Check that skills are in `~/.devin-orchestrator/skills/` and config points to correct location.

### Workflow Not Found
Check that manifests are in `~/.devin-orchestrator/workflows/` (canonical) or `.devin/workflows/` (if using local overrides).

### Devin CLI Not Found
Update `devin_cli_path` in `~/.devin-orchestrator/config.yaml` to your Devin CLI path.

### Bash Tool Not Available
If Cascade cannot use the bash tool to dispatch skills, check Cascade's tool configuration. The orchestrator-worker pattern requires Cascade to be able to spawn subprocess calls to dispatch to Devin.

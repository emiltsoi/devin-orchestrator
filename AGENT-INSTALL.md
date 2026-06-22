# Agent Installation Guide

This guide provides step-by-step instructions for agents (Cascade, Devin, etc.) to install and deploy devin-orchestrator.

## Quick Installation

### Step 1: Clone Repository (if not already present)
```bash
git clone <devin-orchestrator-url>
cd devin-orchestrator
```

### Step 2: Run Automated Installation
```bash
python install_automated.py
```

This single command:
- Installs devin-orchestrator to `~/.devin-orchestrator/`
- Sets up the current workspace with workflow manifests
- Configures environment variables

### Step 3: Verify Installation
```bash
# Check if installation succeeded
ls ~/.devin-orchestrator/
# Should show: skills/, workflows/, workflow-engine/, config.yaml

# Check if workspace is set up
ls .devin/workflows/
# Should show: *.manifest.yaml files
```

## Manual Installation (Alternative)

### Step 1: Install Globally
```bash
python install.py
```

### Step 2: Setup Workspace
```bash
mkdir -p .devin/workflows
cp ~/.devin-orchestrator/workflows/*.manifest.yaml .devin/workflows/
```

## Deployment to Existing Workspaces

For existing repositories, after global installation:

```bash
# Navigate to existing repo
cd /path/to/existing/repo

# Create workflows directory
mkdir -p .devin/workflows

# Copy desired workflow manifests
cp ~/.devin-orchestrator/workflows/superpower.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/rca.manifest.yaml .devin/workflows/
# Add other workflows as needed
```

## Available Workflows

After installation, these workflows are available:
- `superpower.manifest.yaml` - Complete software development methodology
- `rca.manifest.yaml` - Root cause analysis workflow
- `pr_review.manifest.yaml` - Pull request review workflow
- `code_review.manifest.yaml` - Code review workflow
- `devin-support.manifest.yaml` - Meta-workflow for orchestration

## Configuration

Default configuration is in `~/.devin-orchestrator/config.yaml`. Edit if needed:

```yaml
devin_cli_path: C:/Users/<user>/AppData/Local/devin/cli/bin/devin.exe
default_model: swe-1.6
default_permission_mode: dangerous
```

## Verification

Test installation by running health check:
```bash
python ~/.devin-orchestrator/workflow-engine/health_check.py
```

Expected output: All components should show "healthy" status.

## Troubleshooting

If installation fails:
1. Check Python 3.8+ is available: `python --version`
2. Check pip is available: `pip --version`
3. Check git is available: `git --version`
4. Re-run installation with verbose output if needed

## Agent-Specific Notes

- **Cascade**: Has bash tool access, can run all commands directly
- **File Operations**: Agents with file access can copy directories directly
- **Environment Variables**: May need to set `DEVIN_CLI_PATH` if not auto-detected
- **Non-Invasive**: Installation does not modify existing project files

## Expected Installation Structure

After successful installation:

```
~/.devin-orchestrator/
├── skills/              # Global skills (shared across workspaces)
├── workflows/           # Workflow manifests
├── workflow-engine/     # Orchestration engine
├── config.yaml          # Configuration
└── dispatch_skill.py    # Dispatch script

.devin/workflows/        # Per-workspace workflow manifests
├── superpower.manifest.yaml
├── rca.manifest.yaml
└── ...
```

## Success Indicators

Installation is successful when:
1. `~/.devin-orchestrator/` directory exists with all subdirectories
2. `config.yaml` is present and valid
3. `.devin/workflows/` contains workflow manifests
4. Health check passes with all components healthy
5. Skills are accessible from workflow engine

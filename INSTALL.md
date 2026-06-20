# Installation Guide

## Quick Start

### 1. Clone the Repository
```bash
git clone <devin-orchestrator-url>
cd devin-orchestrator
```

### 2. Install Globally
```bash
python install.py
```

This installs devin-orchestrator to `~/.devin-orchestrator/`:
- Skills: `~/.devin-orchestrator/skills/`
- Workflows: `~/.devin-orchestrator/workflows/`
- Workflow Engine: `~/.devin-orchestrator/workflow-engine/`
- Config: `~/.devin-orchestrator/config.yaml`
- Dispatch Script: `~/.devin-orchestrator/dispatch_skill.py`

### 3. Setup Workspace
For each workspace where you want to use devin-orchestrator:

```bash
# Create .devin/workflows directory
mkdir -p .devin/workflows

# Copy workflow manifests
cp ~/.devin-orchestrator/workflows/superpower.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/rca.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/pr_review.manifest.yaml .devin/workflows/
cp ~/.devin-orchestrator/workflows/code_review.manifest.yaml .devin/workflows/
```

## Usage

### Cascade Workflow Execution

When Cascade loads a workflow, it will:
1. Read the manifest from `.devin/workflows/`
2. Load the orchestrate-superpower skill
3. Use `dispatch_skill.py` to dispatch each stage to Devin

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

Edit `~/.devin-orchestrator/config.yaml` to customize:

```yaml
global_root: ~/.devin-orchestrator
skills_dir: ~/.devin-orchestrator/skills
workflows_dir: ~/.devin-orchestrator/workflows
workflow_engine_dir: ~/.devin-orchestrator/workflow-engine

devin_cli_path: C:/Users/<user>/AppData/Local/devin/cli/bin/devin.exe
default_model: swe-1.6
default_permission_mode: dangerous

session_work_dir: ~/.devin-orchestrator/work
```

## Environment Variables

Override config with environment variables:

```bash
export DEVIN_ORCHESTRATOR_ROOT=~/.devin-orchestrator
export DEVIN_ORCHESTRATOR_SKILLS_DIR=~/.devin-orchestrator/skills
export DEVIN_ORCHESTRATOR_WORKFLOWS_DIR=~/.devin-orchestrator/workflows
export DEVIN_CLI_PATH=C:/Users/<user>/AppData/Local/devin/cli/bin/devin.exe
export DEVIN_DEFAULT_MODEL=swe-1.6
export DEVIN_DEFAULT_PERMISSION_MODE=dangerous
```

## Architecture

- **Global Skills**: Stored in `~/.devin-orchestrator/skills/` (no workspace duplication)
- **Local Workflows**: Stored in `.devin/workflows/` (Cascade requirement)
- **Global Workflow Engine**: Stored in `~/.devin-orchestrator/workflow-engine/`
- **Dispatch Script**: Stored in `~/.devin-orchestrator/dispatch_skill.py`

## Updating

To update to the latest version:

```bash
cd devin-orchestrator
git pull
python install.py
```

This will overwrite the global installation with the latest skills, workflows, and workflow engine.

## Troubleshooting

### Skill Not Found
Check that skills are in `~/.devin-orchestrator/skills/` and config points to correct location.

### Workflow Not Found
Check that manifests are in `.devin/workflows/` in your workspace.

### Devin CLI Not Found
Update `devin_cli_path` in `~/.devin-orchestrator/config.yaml` to your Devin CLI path.

### Module Import Errors
Ensure `~/.devin-orchestrator/workflow-engine/` is in Python path (dispatch_skill.py handles this).

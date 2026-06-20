# Installation Guide

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

### Option 2: Manual Installation

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

**Important:** Cascade cannot spawn external processes (subprocess calls). Cascade executes skill logic directly using its available tools.

When Cascade loads a workflow, it will:
1. Read the manifest from `.devin/workflows/`
2. Load the orchestrate-superpower skill
3. Load skill definitions and narratives from `~/.devin-orchestrator/skills/`
4. Execute skill logic directly using its available tools (read files, write files, run commands, etc.)
5. Reason through results and make triage decisions
6. Handle gates and structural floor validation

**Cascade is both the orchestrator AND the worker.** It does not dispatch to external processes like devin.exe.

## Configuration

Edit `~/.devin-orchestrator/config.yaml` to customize:

```yaml
global_root: ~/.devin-orchestrator
skills_dir: ~/.devin-orchestrator/skills
workflows_dir: ~/.devin-orchestrator/workflows
workflow_engine_dir: ~/.devin-orchestrator/workflow-engine

session_work_dir: ~/.devin-orchestrator/work
```

**Note:** `devin_cli_path`, `default_model`, and `default_permission_mode` are not used by Cascade since it executes skills directly and cannot spawn external processes.

## Environment Variables

Override config with environment variables:

```bash
export DEVIN_ORCHESTRATOR_ROOT=~/.devin-orchestrator
export DEVIN_ORCHESTRATOR_SKILLS_DIR=~/.devin-orchestrator/skills
export DEVIN_ORCHESTRATOR_WORKFLOWS_DIR=~/.devin-orchestrator/workflows
```

## Architecture

- **Global Skills**: Stored in `~/.devin-orchestrator/skills/` (no workspace duplication)
- **Local Workflows**: Stored in `.devin/workflows/` (Cascade requirement)
- **Global Workflow Engine**: Stored in `~/.devin-orchestrator/workflow-engine/`
- **Cascade Execution**: Cascade loads skill definitions and executes logic directly using available tools

**Important Limitations:**
- Cascade cannot spawn external processes (subprocess calls)
- Cascade cannot dispatch to devin.exe
- Cascade executes skill logic directly using its available tools
- Cascade is both orchestrator and worker

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

### Cascade Cannot Execute Skills
Cascade executes skills directly using its available tools. If skills require external processes that Cascade cannot spawn, the skill may not work. Skills should be designed to use Cascade's available tools (read files, write files, run commands, etc.).

### Module Import Errors
Ensure `~/.devin-orchestrator/workflow-engine/` is in Python path if importing modules.

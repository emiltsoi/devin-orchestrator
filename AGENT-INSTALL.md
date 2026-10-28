# Agent Installation Guide

This guide provides step-by-step instructions for agents (Cascade, Devin, etc.) to install and deploy devin-orchestrator.

## Quick Installation

### Option A: From PyPI (preferred)

```bash
pip install devin-orchestrator
devin-orchestrator install   # copies runtime to ~/.devin-orchestrator and registers the MCP server
```

### Option B: From a source checkout

```bash
git clone <devin-orchestrator-url>
cd devin-orchestrator
python install.py
```

`install.py` copies the `devin_orchestrator` package, skills, workflows, roles,
config, and the dispatch/MCP entry scripts into `~/.devin-orchestrator/`, and
creates a `devin-orchestrator` launcher under `~/.devin-orchestrator/bin/`.

### Step 3: Verify Installation
```bash
# Check if installation succeeded
ls ~/.devin-orchestrator/
# Should show: skills/, workflows/, roles/, devin-orchestrator/, config.yaml,
#              dispatch_devin.py, dispatch_skill.py, mcp_server.py, bin/

# Check if workspace is set up (optional - for local overrides)
ls .devin/workflows/
# Should show: *.manifest.yaml files (if copied for local overrides)
```

## Deployment to Existing Workspaces

For existing repositories, after global installation:

```bash
# Navigate to existing repo
cd /path/to/existing/repo

# Create workflows directory (optional - for local overrides)
mkdir -p .devin/workflows

# Copy desired workflow manifests (optional - for local overrides)
cp ~/.devin-orchestrator/workflows/rca.manifest.yaml .devin/workflows/
# Add other workflows as needed
```

Note: Copying to `.devin/workflows/` is optional. The canonical source is `~/.devin-orchestrator/workflows/`. Use `.devin/workflows/` only for per-workspace overrides.

## Available Workflows

After installation, these workflows are available:
- `rca.manifest.yaml` - Root cause analysis workflow
- `pr_review.manifest.yaml` - Pull request review workflow
- `code_review.manifest.yaml` - Code review workflow

## Configuration

Default configuration is in `~/.devin-orchestrator/config.yaml`. Edit if needed:

```yaml
devin_cli_path: C:/Users/<user>/AppData/Local/devin/cli/bin/devin.exe
default_model: swe-1.6
default_permission_mode: smart
```

## Verification

Test installation by running the doctor (validates paths, CLI, and config):

```bash
devin-orchestrator-doctor
# or, from the installed tree:
python -m devin_orchestrator.doctor
```

Expected output: all components should report healthy.

## Troubleshooting

If installation fails:
1. Check Python 3.10+ is available: `python --version`
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
├── skills/                # Global skills (shared across workspaces)
├── workflows/             # Canonical workflow manifests + use-cases.yaml
├── roles/                 # Role prompts used by dispatch_devin.py
├── devin_orchestrator/    # Engine package (MCP server, orchestrator, adapters)
├── config.yaml            # Configuration
├── dispatch_devin.py      # Dispatch a Devin run with a role + prompt file
├── dispatch_skill.py      # Dispatch a skill into a session
├── mcp_server.py          # MCP server entry point
├── bin/devin-orchestrator # Launcher
├── work/                  # Dispatched-run workspaces
└── logs/                  # Logs

.devin/workflows/          # Per-workspace workflow overrides (optional)
└── *.manifest.yaml
```

Note: `.devin/workflows/` is optional and only needed for per-workspace overrides. The canonical source is `~/.devin-orchestrator/workflows/`.

## Success Indicators

Installation is successful when:
1. `~/.devin-orchestrator/` directory exists with all subdirectories
2. `config.yaml` is present and valid
3. `devin-orchestrator-doctor` reports all components healthy
4. The MCP server registers (check your agent's MCP config, or run `register_mcp.py`)
5. Skills are listed by the `list_skills` MCP tool

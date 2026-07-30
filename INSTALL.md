# Installation

The fastest way to install is with [pipx](https://pypa.github.io/pipx/):

```bash
pipx install devin-orchestrator
devin-orchestrator install
```

This creates a user service (systemd on Linux, launchd on macOS, Task Scheduler on Windows) and registers the MCP server with every known local agent config.

See [DEPLOY.md](DEPLOY.md) for the full deployment guide, including uninstall/upgrade, dry-run, legacy scripts, and troubleshooting.

# Deploy `devin-orchestrator`

`devin-orchestrator` can be installed as a service on Linux, macOS, and Windows.
Once installed, the MCP server is registered with all known local agent configs.

## Quick start

Install with [pipx](https://pypa.github.io/pipx/) and create the service:

```bash
pipx install devin-orchestrator
devin-orchestrator install
```

Restart your agent/IDE so it picks up the MCP config changes.

## Manage the service

- `devin-orchestrator install` — create the service and register the MCP server.
- `devin-orchestrator install uninstall` — stop and remove the service.
- `devin-orchestrator install uninstall --deregister` — also remove the MCP server from agent configs.
- `devin-orchestrator install upgrade` — upgrade the package with pip.

## Common options

- `--dry-run` — show what would change without touching files or services.
- `--system` — install a system service (requires root/Administrator).
- `--service-name <name>` — use a different service name.
- `--work-dir <path>` — working directory for the service.
- `--run-as <user>` — user account for the service (Linux/macOS).
- `--exec ...` — custom command for the service.
- `--python <exe>` — Python executable for the default MCP server command.
- `--global-root <path>` — global root used when writing agent configs.
- `--register` / `--no-register` — control agent config registration.
- `--skip-smoke` — skip the post-install `devin-orchestrator doctor` smoke test.
- `--create-missing` / `--no-create-missing` — create missing agent config files.
- `--keep-backups <n>` — number of agent config backups to retain (default 10).

## Dry run

```bash
devin-orchestrator install --dry-run
devin-orchestrator install uninstall --deregister --dry-run
```

## Cross-platform notes

- **Linux:** creates a systemd user unit in `~/.config/systemd/user/`.
- **macOS:** creates a `launchd` user agent in `~/Library/LaunchAgents/`.
- **Windows:** creates a `schtasks` logon task and a wrapper `.bat` in `%APPDATA%\devin-orchestrator\`.

## Legacy scripts

The root `install.py`, `deploy.py`, and `register_mcp.py` scripts still work from the repository tree but print a deprecation warning and forward to the new CLI:

```bash
python3 deploy.py --dry-run
python3 deploy.py --uninstall
python3 deploy.py --list
python3 register_mcp.py --remove
```

When installed from pip/pipx, use `devin-orchestrator install` instead.

## Agent configs

`devin-orchestrator install` registers the MCP server in the usual cross-platform
locations (devin, aider, windsurf, pi, claude, hermes). Run `devin-orchestrator install --dry-run` to see which files would be touched.

The command registered in each config is chosen automatically:

- If `devin-orchestrator` is on PATH (pip/pipx install), it uses `devin-orchestrator mcp`.
- If the legacy `install.py` wrapper exists, it uses that wrapper.
- Otherwise it falls back to `python -m devin_orchestrator.mcp_server`.

### Service and agent-spawned stdio MCP

`devin-orchestrator install` does two things by default:

1. It registers the stdio MCP server command in each agent config so agents can spawn it on demand.
2. It installs a background service (systemd/launchd/Task Scheduler) that runs the same stdio MCP server at logon.

This means both the service and an individual agent may have a `devin-orchestrator` MCP process running at the same time. That is intentional for now: the service keeps an instance ready for clients that cannot spawn their own process, while the registered command lets agents launch the server themselves. Future transports (HTTP/SSE) will replace the background stdio service with a single long-running server.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common install, PATH, PyYAML, stale process, and smoke-test issues.

## After deploying

Most agents read their MCP config on startup.  Restart the agent/IDE (or its MCP
connection) so it spawns the new `devin-orchestrator` process.

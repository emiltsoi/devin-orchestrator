# Troubleshooting devin-orchestrator

## Install / deploy

### `ModuleNotFoundError: No module named 'devin_orchestrator'`

You ran a script with an absolute path from a different directory. Either:

- `cd` into the repository and use relative paths:
  ```bash
  cd /path/to/devin-orchestrator
  python3 deploy.py
  ```
- Set `PYTHONPATH` to the repo root:
  ```bash
  PYTHONPATH=/path/to/devin-orchestrator python3 /path/to/devin-orchestrator/deploy.py
  ```

### Launcher not found after install

**Linux / macOS:**
The launcher is at `~/.local/bin/devin-orchestrator`. Add it to your PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Windows:**
The launcher is at `%USERPROFILE%\.devin-orchestrator\bin\devin-orchestrator.bat`. The agent config points to it directly, so PATH changes are not needed.

### `PyYAML not installed` warning for Hermes

Hermes uses a YAML config. If you want `register_mcp.py` to edit it:
```bash
pip install pyyaml
```

### Stale `devin-orchestrator` processes

If an old MCP server process is hanging:
```bash
pkill -f "devin-orchestrator.*mcp_server"
```
On Windows:
```powershell
Get-Process | Where-Object {$_.ProcessName -like "*python*" -and $_.CommandLine -like "*mcp_server*"} | Stop-Process
```

### Smoke test fails

Run it by hand with verbose output:
```bash
python3 deploy.py --smoke-only
```
Common causes:
- The launcher path is wrong or not on PATH.
- `mcp_server.py` fails to import because `PYTHONPATH` is missing.
- A stale process is holding the stdio pipe.

## Uninstall

```bash
python3 deploy.py --uninstall
```

Use `--dry-run` first to see what would be removed.

## MCP client issues

See [MCP-CLIENTS.md](MCP-CLIENTS.md) for per-agent config format and examples.

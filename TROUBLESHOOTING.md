# Troubleshooting devin-orchestrator

## Install / deploy

### `ModuleNotFoundError: No module named 'devin_orchestrator'`

You are running a script from the repository without the package installed. Either:

- Install the package and use the CLI:
  ```bash
  pip install -e .
  devin-orchestrator doctor
  ```
- Or set `PYTHONPATH` to the repo root when running from source:
  ```bash
  PYTHONPATH=/path/to/devin-orchestrator python3 -m devin_orchestrator.cli install
  ```

### Launcher not found after install

**Linux / macOS:**
The console script is at `~/.local/bin/devin-orchestrator` (pipx) or in the active virtual environment's `bin/`. Add it to your PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Windows:**
The console script is in the Python `Scripts` directory (e.g. `%USERPROFILE%\AppData\Local\Programs\Python\Python312\Scripts\devin-orchestrator.exe`). Add the `Scripts` directory to PATH, or use the absolute path in the agent config.

### `PyYAML not installed` warning for Hermes

Hermes uses a YAML config. If you want `devin-orchestrator install` to edit it:
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
devin-orchestrator doctor
```
Common causes:
- The `devin-orchestrator` console script is not on PATH.
- The package fails to import because the wrong Python environment is active.
- A stale process is holding the stdio pipe.

## Uninstall

```bash
devin-orchestrator install uninstall
```

Use `--dry-run` first to see what would be removed.

## MCP client issues

See [MCP-CLIENTS.md](MCP-CLIENTS.md) for per-agent config format and examples.

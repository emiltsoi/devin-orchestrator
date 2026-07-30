#!/usr/bin/env python3
"""
Register the devin-orchestrator MCP server with the agents installed on this VM.

Supports dry-run, listing, and removing the registration.  It backs up every file
before mutating it.
"""

import argparse
import contextlib
import glob
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any


def _is_legacy_launcher(path: Path) -> bool:
    """Return True if *path* is the old install.py wrapper around mcp_server.py."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return "mcp_server.py" in text

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

DEFAULT_INSTRUCTIONS = (
    "devin-orchestrator MCP server. Prefer high-level intent tools: execute "
    "(auto-route), implement (full superpower workflow), review (code_review), "
    "investigate (rca, read-only), plan (writing-plans). Use run_workflow/run_skill "
    "for explicit workflows/process skills. Use dispatch_devin for focused single-shot "
    "workers with a prompt_file, work_dir, and output_file. Discovery: list_skills, "
    "get_skill, list_workflows, get_workflow, read_artifact. Gate control: "
    "gate_decision, continue_workflow."
)


def _global_root(global_root: Path | None = None) -> Path:
    if global_root is None:
        global_root = Path.home() / ".devin-orchestrator"
    return global_root.expanduser()


def _launcher_path(global_root: Path | None = None) -> str:
    """Return the platform-appropriate launcher path."""
    exe = shutil.which("devin-orchestrator")
    if exe:
        return exe
    root = _global_root(global_root)
    if sys.platform == "win32":
        return str(root / "bin" / "devin-orchestrator.bat")
    return str(Path.home() / ".local" / "bin" / "devin-orchestrator")


def devin_mcp_config(global_root: Path | None = None) -> dict[str, Any]:
    """Return an MCP server config for the current installation."""
    launcher = Path(_launcher_path(global_root))
    if launcher.exists() and _is_legacy_launcher(launcher):
        # Old install.py wrapper: it already runs mcp_server.py.
        return {"command": str(launcher), "instructions": DEFAULT_INSTRUCTIONS}
    if shutil.which("devin-orchestrator"):
        # Modern pip/pipx console script: add the `mcp` subcommand.
        return {
            "command": str(launcher),
            "args": ["mcp"],
            "instructions": DEFAULT_INSTRUCTIONS,
        }
    # Fallback for running from source or an unpacked package.
    return {
        "command": sys.executable,
        "args": ["-m", "devin_orchestrator.mcp_server"],
        "instructions": DEFAULT_INSTRUCTIONS,
    }


ConfigTarget = dict[str, Any]


def _resolve(candidates: list[Path]) -> Path:
    """Return the first existing candidate, or the first candidate as fallback."""
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _env_path(var: str, *parts: str) -> Path | None:
    """Return a path under an environment variable if it is set."""
    value = os.environ.get(var)
    if not value:
        return None
    return Path(value).expanduser() / Path(*parts)


def _targets() -> list[ConfigTarget]:
    home = Path.home()
    appdata = _env_path("APPDATA")
    library = home / "Library" / "Application Support"

    devin_candidates = [home / ".config" / "devin" / "mcp_config.json"]
    if appdata:
        devin_candidates.append(appdata / "devin" / "mcp_config.json")

    windsurf_candidates = [home / ".codeium" / "windsurf" / "mcp_config.json"]
    if appdata:
        windsurf_candidates.append(appdata / "Windsurf" / "mcp_config.json")
    if (library / "Codeium" / "windsurf").is_dir() or not windsurf_candidates[0].parent.exists():
        windsurf_candidates.append(library / "Codeium" / "windsurf" / "mcp_config.json")

    claude_candidates = [home / ".claude.json"]
    if appdata:
        claude_candidates.append(appdata / "Claude" / "settings" / "claude_desktop_config.json")
        claude_candidates.append(appdata / "Claude" / "claude_desktop_config.json")
    claude_candidates.append(library / "Claude" / "claude_desktop_config.json")

    hermes_candidates = [home / ".hermes" / "config.yaml"]
    if appdata:
        hermes_candidates.append(appdata / "hermes" / "config.yaml")

    return [
        {
            "name": "devin",
            "path": _resolve(devin_candidates),
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
        {
            "name": "aider",
            "path": home / ".aider" / "mcp.json",
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
        {
            "name": "windsurf",
            "path": _resolve(windsurf_candidates),
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
        {
            "name": "pi",
            "path": home / ".pi" / "agent" / "mcp.json",
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
        {
            "name": "claude",
            "path": _resolve(claude_candidates),
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
        {
            "name": "hermes",
            "path": _resolve(hermes_candidates),
            "format": "yaml",
            "root_key": "mcp_servers",
            "default": {"mcp_servers": {}},
            "create_if_missing": True,
        },
    ]


def _prune_backups(backups_dir: Path, keep: int) -> None:
    """Keep only the ``keep`` most recent backups in a directory."""
    if keep <= 0:
        return
    pattern = str(backups_dir / "*.bak")
    backups = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for old in backups[keep:]:
        with contextlib.suppress(OSError):
            os.remove(old)


def _backup(path: Path, keep_backups: int = 10) -> Path:
    backup = path.parent / f"{path.name}.{int(time.time())}.bak"
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    _prune_backups(path.parent, keep_backups)
    return backup


def _load(path: Path, fmt: str, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return default
        if fmt == "json":
            return json.loads(text)
        if fmt == "yaml":
            if yaml is None:
                raise RuntimeError("PyYAML is required to edit Hermes config")
            return yaml.safe_load(text) or default
        raise ValueError(f"Unknown format {fmt}")
    except Exception as e:
        raise RuntimeError(f"Failed to load {path}: {e}") from e


def _save(path: Path, fmt: str, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif fmt == "yaml":
        if yaml is None:
            raise RuntimeError("PyYAML is required to edit Hermes config")
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    else:
        raise ValueError(f"Unknown format {fmt}")


def _status(target: ConfigTarget) -> str:
    path = target["path"]
    if not path.exists():
        return "missing"
    data = _load(path, target["format"], target["default"])
    servers = data.get(target["root_key"], {})
    if "devin-orchestrator" in servers:
        return "registered"
    return "exists"


def register(
    dry_run: bool = False,
    create_missing: bool = True,
    global_root: Path | None = None,
    keep_backups: int = 10,
) -> list[tuple[ConfigTarget, bool]]:
    """Add or update devin-orchestrator in every agent config."""
    results = []
    for target in _targets():
        path = target["path"]
        exists = path.exists()
        if not exists and not create_missing:
            results.append((target, False))
            continue

        if target["format"] == "yaml" and yaml is None:
            print(
                f"  Skipped {target['name']}: PyYAML not installed (pip install pyyaml)",
                file=sys.stderr,
            )
            results.append((target, False))
            continue

        data = _load(path, target["format"], target["default"])
        servers = data.setdefault(target["root_key"], {})
        old = servers.get("devin-orchestrator")
        new = devin_mcp_config(global_root)
        changed = old != new

        if not dry_run and (not exists or changed):
            if exists:
                _backup(path, keep_backups)
            servers["devin-orchestrator"] = new
            _save(path, target["format"], data)

        results.append((target, bool(not dry_run and (not exists or changed))))
    return results


def remove(dry_run: bool = False, keep_backups: int = 10) -> list[tuple[ConfigTarget, bool]]:
    """Remove devin-orchestrator from every agent config."""
    results = []
    for target in _targets():
        path = target["path"]
        if not path.exists():
            results.append((target, False))
            continue
        if target["format"] == "yaml" and yaml is None:
            print(
                f"  Skipped {target['name']}: PyYAML not installed (pip install pyyaml)",
                file=sys.stderr,
            )
            results.append((target, False))
            continue
        data = _load(path, target["format"], target["default"])
        servers = data.get(target["root_key"], {})
        if "devin-orchestrator" not in servers:
            results.append((target, False))
            continue
        if not dry_run:
            _backup(path, keep_backups)
            del servers["devin-orchestrator"]
            _save(path, target["format"], data)
        results.append((target, True))
    return results


def list_status() -> None:
    print(f"{'Agent':<12} {'Status':<12} {'Path'}")
    for target in _targets():
        print(f"{target['name']:<12} {_status(target):<12} {target['path']}")


def print_snippet(global_root: Path | None = None) -> None:
    """Print a generic mcpServers snippet for unsupported clients."""
    snippet = {"mcpServers": {"devin-orchestrator": devin_mcp_config(global_root)}}
    print(json.dumps(snippet, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register devin-orchestrator with all known agent MCP clients"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List current registration status for each agent",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove devin-orchestrator from all agent configs",
    )
    parser.add_argument(
        "--create-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create agent config files if they do not already exist (default: True)",
    )
    parser.add_argument(
        "--global-root",
        type=Path,
        default=None,
        help="Path to the devin-orchestrator global root (default: ~/.devin-orchestrator)",
    )
    parser.add_argument(
        "--keep-backups",
        type=int,
        default=10,
        help="Number of backups to retain (default: 10)",
    )
    parser.add_argument(
        "--snippet",
        action="store_true",
        help="Print a generic mcpServers snippet for any client",
    )

    args = parser.parse_args()

    if args.list:
        list_status()
        return 0

    if args.snippet:
        print_snippet(args.global_root)
        return 0

    if args.remove:
        results = remove(dry_run=args.dry_run, keep_backups=args.keep_backups)
    else:
        results = register(
            dry_run=args.dry_run,
            create_missing=args.create_missing,
            global_root=args.global_root,
            keep_backups=args.keep_backups,
        )

    for target, changed in results:
        status = "updated" if changed else ("no change" if target["path"].exists() else "missing")
        action = "Would update" if args.dry_run and changed else ("Updated" if changed else "No change")
        print(f"{action:<13} {target['name']:<12} {target['path']} [{status}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

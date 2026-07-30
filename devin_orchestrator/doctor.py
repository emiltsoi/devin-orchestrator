#!/usr/bin/env python3
"""Diagnostic check for a devin-orchestrator installation."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from devin_orchestrator import __version__
from devin_orchestrator.config_loader import ConfigLoader
from register_mcp import _launcher_path, _targets


def _ok(label: str) -> None:
    print(f"  [OK]   {label}")


def _fail(label: str, detail: str) -> None:
    print(f"  [FAIL] {label}")
    print(f"         {detail}")


def _warn(label: str, detail: str) -> None:
    print(f"  [WARN] {label}")
    print(f"         {detail}")


def main() -> int:
    from importlib.metadata import version as get_version

    print(f"devin-orchestrator doctor ({__version__})")
    print()

    # Python version
    if sys.version_info >= (3, 10):
        _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    else:
        _fail("Python 3.10+", f"running {sys.version}")

    # Package version
    try:
        get_version("devin-orchestrator")
        _ok(f"Package version: {__version__}")
    except Exception as e:  # pragma: no cover
        _warn("Package version", str(e))

    # Global root
    config = ConfigLoader.load()
    global_root = Path(config.global_root)
    if global_root.exists():
        _ok(f"Global root: {global_root}")
    else:
        _fail("Global root", f"missing {global_root}")

    for subdir in ("skills", "workflows", "roles"):
        path = global_root / subdir
        if path.is_dir() and any(path.iterdir()):
            _ok(f"Data directory: {path}")
        else:
            _fail(f"Data directory", f"missing or empty: {path}")

    config_file = global_root / "config.yaml"
    if config_file.exists():
        _ok(f"Config file: {config_file}")
    else:
        _fail("Config file", f"missing: {config_file}")

    # Launcher
    launcher = Path(_launcher_path(global_root))
    if launcher.exists():
        _ok(f"Launcher: {launcher}")
    else:
        _fail("Launcher", f"missing: {launcher}")

    exe = shutil.which("devin-orchestrator")
    if exe:
        _ok(f"Launcher on PATH: {exe}")
    else:
        _warn("PATH", "devin-orchestrator not found on PATH; agents may use absolute launcher path")

    # Agent configs
    print()
    print("Agent MCP registrations:")
    for target in _targets():
        path = target["path"]
        status = "registered" if path.exists() else "missing"
        if path.exists():
            data = path.read_text(encoding="utf-8")
            if "devin-orchestrator" in data:
                _ok(f"{target['name']:<12} {path}")
            else:
                _warn(f"{target['name']:<12} {path}", "devin-orchestrator not found")
        else:
            _warn(f"{target['name']:<12} {path}", f"config file {status}")

    print()
    print("Run 'deploy.py' to install or 'register_mcp.py' to update agent configs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

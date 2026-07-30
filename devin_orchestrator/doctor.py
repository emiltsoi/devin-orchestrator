#!/usr/bin/env python3
"""Diagnostic check for a devin-orchestrator installation."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from devin_orchestrator import __version__
from devin_orchestrator.config_loader import ConfigLoader
from devin_orchestrator.manifest_loader import ManifestLoader
from devin_orchestrator.register_mcp import (
    _is_legacy_launcher,
    _launcher_path,
    _targets,
)


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
    _ok(
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

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
            _fail("Data directory", f"missing or empty: {path}")

    config_file = global_root / "config.yaml"
    if config_file.exists():
        _ok(f"Config file: {config_file}")
    else:
        _fail("Config file", f"missing: {config_file}")

    # Launcher
    launcher = Path(_launcher_path(global_root))
    if launcher.exists():
        kind = "Legacy launcher" if _is_legacy_launcher(launcher) else "Console script"
        _ok(f"{kind}: {launcher}")
    else:
        _fail("Launcher", f"missing: {launcher}")

    exe = shutil.which("devin-orchestrator")
    if exe:
        _ok(f"Launcher on PATH: {exe}")
    else:
        _warn(
            "PATH",
            "devin-orchestrator not found on PATH; agents may use absolute launcher path",
        )

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

    # Workflow manifests
    print()
    print("Workflow manifests:")
    loader = ManifestLoader(global_root)
    valid, errors = loader.validate_all()
    for name in valid:
        _ok(name)
    for name, error in errors:
        _fail(name, error)

    print()
    print("Run 'deploy.py' to install or 'register_mcp.py' to update agent configs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

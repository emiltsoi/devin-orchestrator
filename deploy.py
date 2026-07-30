#!/usr/bin/env python3
"""
One-click cross-platform deploy for devin-orchestrator.

Works on Linux, macOS, and Windows (with python3 / py).
"""

import argparse
import contextlib
import json
import os
import shutil
import stat
import subprocess  # nosec B404
import sys
from pathlib import Path

from devin_orchestrator import __version__
from devin_orchestrator.register_mcp import (
    _launcher_path,
)
from devin_orchestrator.register_mcp import (
    list_status as do_list_status,
)
from devin_orchestrator.register_mcp import (
    register as do_register,
)
from devin_orchestrator.register_mcp import (
    remove as do_remove,
)
from install import install as do_install


def _mcp_request(method: str, params: dict, request_id: int = 1) -> bytes:
    """Encode a JSON-RPC 2.0 request with Content-Length framing."""
    body = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        separators=(",", ":"),
    ).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def _parse_mcp_response(data: bytes) -> dict | None:
    """Parse the first Content-Length framed JSON-RPC response in ``data``."""
    if not data:
        return None
    text = data.decode("utf-8", errors="replace")
    if not text.startswith("Content-Length:"):
        return None
    try:
        header, rest = text.split("\r\n\r\n", 1)
        length = int(header.split(":", 1)[1].strip())
        body = rest[:length]
        return json.loads(body)
    except (ValueError, IndexError, json.JSONDecodeError):
        return None


def smoke_test(launcher: str, timeout: int = 10) -> dict | None:
    """Send an initialize request to the launcher and return the response."""
    try:
        proc = subprocess.Popen(
            [launcher],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, FileNotFoundError) as e:
        print(f"Failed to start launcher: {e}", file=sys.stderr)
        return None

    try:
        req = _mcp_request("initialize", {})
        stdout, _ = proc.communicate(input=req, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None
    finally:
        if proc.returncode is None:
            proc.kill()

    return _parse_mcp_response(stdout)


def _on_rmtree_error(func, path, exc_info):
    """Retry removal after making a path writable (Windows-friendly)."""
    with contextlib.suppress(OSError, NotImplementedError):
        os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    """Remove a directory tree with a Python-version-safe callback."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rmtree_error)
    else:
        shutil.rmtree(path, onerror=_on_rmtree_error)


def _uninstall(global_root: Path | None, dry_run: bool) -> None:
    """Remove the global install directory and launcher."""
    root = (global_root or Path.home() / ".devin-orchestrator").expanduser()
    launcher = Path(_launcher_path(global_root))

    if root.exists():
        if dry_run:
            print(f"Would remove directory: {root}")
        else:
            _rmtree(root)
            print(f"Removed directory: {root}")
    else:
        print(f"Global root not found: {root}")

    if launcher.exists():
        if dry_run:
            print(f"Would remove launcher: {launcher}")
        else:
            launcher.unlink()
            print(f"Removed launcher: {launcher}")
    else:
        print(f"Launcher not found: {launcher}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy devin-orchestrator globally and register it with local agents."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--global-root",
        type=Path,
        default=None,
        help="Global root path (default: ~/.devin-orchestrator)",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python executable to use in the launcher (default: this interpreter)",
    )
    parser.add_argument(
        "--keep-backups",
        type=int,
        default=10,
        help="Number of backups to retain (default: 10)",
    )
    parser.add_argument(
        "--skip-register",
        action="store_true",
        help="Only run install.py, skip agent config registration",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List current agent registration status and exit",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Run the install/registration smoke test and exit",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the post-install smoke test",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove devin-orchestrator from agents and delete global install",
    )

    args = parser.parse_args()

    if args.list:
        do_list_status()
        return 0

    if args.smoke_only:
        launcher = _launcher_path(args.global_root)
        print(f"Running smoke test with launcher: {launcher}")
        result = smoke_test(launcher)
        if result is None:
            print("Smoke test FAILED: no response from MCP server", file=sys.stderr)
            return 1
        print("Smoke test OK:", json.dumps(result, indent=2))
        return 0

    if args.uninstall:
        print("=== devin-orchestrator uninstall ===")
        if args.dry_run:
            print("DRY RUN MODE - No actual changes will be made")
        print("\n-- Removing agent registrations --")
        do_remove(dry_run=args.dry_run, keep_backups=args.keep_backups)
        print("\n-- Removing global install --")
        _uninstall(args.global_root, dry_run=args.dry_run)
        print("\n=== Done ===")
        return 0

    source_dir = Path(__file__).parent

    print("=== devin-orchestrator deploy ===")
    print(f"Version: {__version__}")
    if args.dry_run:
        print("DRY RUN MODE - No actual changes will be made")

    print("\n-- Installing package --")
    do_install(
        global_root=args.global_root,
        source_dir=source_dir,
        dry_run=args.dry_run,
        python=args.python,
        keep_backups=args.keep_backups,
    )

    if args.skip_register:
        print("\n-- Skipping agent registration --")
    else:
        print("\n-- Registering with agents --")
        do_register(
            dry_run=args.dry_run,
            create_missing=True,
            global_root=args.global_root,
            keep_backups=args.keep_backups,
        )

    if not args.skip_smoke and not args.dry_run:
        print("\n-- Smoke test --")
        launcher = _launcher_path(args.global_root)
        result = smoke_test(launcher)
        if result is None:
            print(
                f"Smoke test FAILED: {launcher} did not respond to initialize",
                file=sys.stderr,
            )
            return 1
        print("Smoke test OK:", json.dumps(result.get("result", {}), indent=2))

    print("\n=== Done ===")
    if not args.skip_register and not args.dry_run:
        print(
            "Restart your agent/IDE to pick up the new devin-orchestrator MCP server."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

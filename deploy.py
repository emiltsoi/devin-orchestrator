#!/usr/bin/env python3
"""
One-click cross-platform deploy for devin-orchestrator.

Works on Linux, macOS, and Windows (with python3 / py).
"""

import argparse
import sys
from pathlib import Path

from install import install as do_install
from register_mcp import (
    list_status as do_list_status,
    register as do_register,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy devin-orchestrator globally and register it with local agents."
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
        "--skip-register",
        action="store_true",
        help="Only run install.py, skip agent config registration",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List current agent registration status and exit",
    )

    args = parser.parse_args()

    if args.list:
        do_list_status()
        return 0

    source_dir = Path(__file__).parent

    print("=== devin-orchestrator deploy ===")
    if args.dry_run:
        print("DRY RUN MODE - No actual changes will be made")

    print("\n-- Installing package --")
    do_install(
        global_root=args.global_root,
        source_dir=source_dir,
        dry_run=args.dry_run,
        python=args.python,
    )

    if args.skip_register:
        print("\n-- Skipping agent registration --")
    else:
        print("\n-- Registering with agents --")
        do_register(
            dry_run=args.dry_run,
            create_missing=True,
            global_root=args.global_root,
        )

    print("\n=== Done ===")
    if not args.skip_register and not args.dry_run:
        print("Restart your agent/IDE to pick up the new devin-orchestrator MCP server.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Unified top-level CLI for devin-orchestrator."""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

from devin_orchestrator import __version__

LEGACY_PROGS = {"dispatch-devin", "dispatch-skill"}


def _warn_if_legacy(prog: str) -> None:
    if os.environ.get("DEVIN_ORCHESTRATOR_NO_DEPRECATION"):
        return
    base = Path(prog).name
    if base in LEGACY_PROGS:
        warnings.warn(
            f"{base} is deprecated; use 'devin-orchestrator dispatch' instead.",
            DeprecationWarning,
            stacklevel=2,
        )


def _mcp_cmd(_namespace: argparse.Namespace, extra: list[str]) -> int:
    from devin_orchestrator.mcp_server import main as mcp_main

    mcp_main(extra)
    return 0


def _doctor_cmd(_namespace: argparse.Namespace, _extra: list[str]) -> int:
    from devin_orchestrator.doctor import main as doctor_main

    return doctor_main()


def _health_cmd(_namespace: argparse.Namespace, extra: list[str]) -> int:
    from devin_orchestrator.health_cli import main as health_main

    return health_main(extra)


def _install_cmd(_namespace: argparse.Namespace, extra: list[str]) -> int:
    from devin_orchestrator.cli_install import install

    return install(extra)


def _dispatch_cmd(_namespace: argparse.Namespace, extra: list[str]) -> int:
    """Forward to dispatch_devin or dispatch_skill based on args."""
    from devin_orchestrator.dispatch_devin import main as dispatch_devin_main
    from devin_orchestrator.dispatch_skill import main as dispatch_skill_main

    if not extra:
        print(
            "Usage: devin-orchestrator dispatch [--role ROLE --prompt-file FILE | "
            "--skill-name NAME --session-id ID --workspace PATH]",
            file=sys.stderr,
        )
        return 2

    if "--skill-name" in extra or (extra and not extra[0].startswith("-")):
        return dispatch_skill_main(extra)

    return dispatch_devin_main(extra)


def _build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Unified CLI for devin-orchestrator.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("mcp", add_help=False, help="Run the MCP server")
    subparsers.add_parser("dispatch", add_help=False, help="Dispatch a Devin worker or skill")
    subparsers.add_parser("doctor", add_help=False, help="Run diagnostic checks")
    subparsers.add_parser("health", add_help=False, help="Print health report as JSON")
    subparsers.add_parser("install", add_help=False, help="Install, uninstall, or upgrade the service")

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    prog = Path(argv[0]).name
    _warn_if_legacy(prog)

    # Legacy entry points do not include a subcommand; default to dispatch.
    if prog in LEGACY_PROGS or prog == "devin-orchestrator-dispatch":
        argv = [str(argv[0]), "dispatch", *argv[1:]]

    parser = _build_parser(prog if prog in LEGACY_PROGS else "devin-orchestrator")
    args, extra = parser.parse_known_args(list(argv[1:]))

    command = args.command

    if command == "mcp":
        return _mcp_cmd(args, extra)
    if command == "doctor":
        return _doctor_cmd(args, extra)
    if command == "health":
        return _health_cmd(args, extra)
    if command == "install":
        return _install_cmd(args, extra)
    if command == "dispatch":
        return _dispatch_cmd(args, extra)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

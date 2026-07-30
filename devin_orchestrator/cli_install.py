#!/usr/bin/env python3
"""CLI subcommand to install, uninstall, and upgrade devin-orchestrator."""
from __future__ import annotations

import argparse
import importlib.resources
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import devin_orchestrator.register_mcp as _register_mcp


def _smoke_test() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "devin_orchestrator.doctor"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def _render_template(template_name: str, variables: dict[str, str]) -> str:
    package_files = importlib.resources.files("devin_orchestrator")
    template_path = package_files / "templates" / template_name
    text = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{{ {key} }}}}", value)
    return text


def _install_service(
    system: bool,
    service_name: str,
    work_dir: Path,
    user: str,
    command: list[str] | None = None,
    dry_run: bool = False,
    register: bool = True,
    keep_backups: int = 10,
    create_missing: bool = True,
) -> int:
    if command is None:
        command = [sys.executable, "-m", "devin_orchestrator.mcp_server"]

    if system:
        unit_dir = Path("/etc/systemd/system")
    else:
        unit_dir = Path.home() / ".config" / "systemd" / "user"

    if not unit_dir.exists():
        unit_dir.mkdir(parents=True, exist_ok=True)

    exec_start = " ".join(str(c) for c in command)
    rendered = _render_template(
        "devin-orchestrator.service",
        {
            "exec_start": exec_start,
            "work_dir": str(work_dir),
            "user": user,
        },
    )

    unit_file = unit_dir / f"{service_name}.service"

    if dry_run:
        print(f"Would write systemd unit: {unit_file}")
    else:
        unit_file.write_text(rendered, encoding="utf-8")
        print(f"Wrote systemd unit: {unit_file}")

    if not dry_run and not _smoke_test():
        print("Smoke test failed; run `devin-orchestrator doctor` for details.", file=sys.stderr)

    if not dry_run and not system:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", service_name], check=False)
        print(f"Enabled {service_name} for the current user.")
    elif not dry_run:
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "enable", service_name], check=False)
        print(f"Enabled {service_name} system-wide.")

    if register:
        results = _register_mcp.register(
            dry_run=dry_run,
            create_missing=create_missing,
            keep_backups=keep_backups,
        )
        for target, changed in results:
            action = (
                "Would update" if dry_run and changed else ("Updated" if changed else "No change")
            )
            print(f"{action:<13} {target['name']:<12} {target['path']}")

    return 0


def _uninstall_service(
    system: bool,
    service_name: str,
    dry_run: bool = False,
    deregister: bool = False,
    keep_backups: int = 10,
) -> int:
    if deregister:
        results = _register_mcp.remove(dry_run=dry_run, keep_backups=keep_backups)
        for target, changed in results:
            action = (
                "Would remove" if dry_run and changed else ("Removed" if changed else "No change")
            )
            print(f"{action:<13} {target['name']:<12} {target['path']}")

    if system:
        unit_dir = Path("/etc/systemd/system")
        systemctl = ["systemctl"]
    else:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        systemctl = ["systemctl", "--user"]

    unit_file = unit_dir / f"{service_name}.service"
    if unit_file.exists():
        if dry_run:
            print(f"Would remove service unit: {unit_file}")
        else:
            subprocess.run([*systemctl, "stop", service_name], check=False)
            subprocess.run([*systemctl, "disable", service_name], check=False)
            unit_file.unlink()
            subprocess.run([*systemctl, "daemon-reload"], check=False)
            print(f"Removed {unit_file}")
    else:
        print(f"Service unit not found: {unit_file}")
        return 1
    return 0


def _upgrade_package(user: bool) -> int:
    pip = shutil.which("pip") or shutil.which("pip3") or sys.executable
    if pip == sys.executable:
        cmd = [pip, "-m", "pip", "install", "--upgrade", "devin-orchestrator"]
    else:
        cmd = [pip, "install", "--upgrade", "devin-orchestrator"]
    if user:
        cmd.append("--user")
    return subprocess.run(cmd).returncode


_SUBCOMMANDS = ("install", "uninstall", "upgrade")


def _build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Install, uninstall, or upgrade devin-orchestrator as a systemd service.",
    )
    subparsers = parser.add_subparsers(dest="command")

    install_cmd = subparsers.add_parser(
        "install", help="Install the devin-orchestrator service"
    )
    install_cmd.add_argument(
        "--system", action="store_true", help="Install a system service (requires root)"
    )
    install_cmd.add_argument("--service-name", default="devin-orchestrator")
    install_cmd.add_argument("--work-dir", default=str(Path.home()))
    install_cmd.add_argument(
        "--run-as",
        default=str(Path.home().name) or "root",
        help="User account the service runs as",
    )
    install_cmd.add_argument(
        "--exec",
        dest="exec_cmd",
        nargs=argparse.REMAINDER,
        default=None,
        help="Command to run in the service (default: run MCP server)",
    )
    install_cmd.add_argument(
        "--register",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Register the MCP server in agent configs (default: True)",
    )
    install_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files or starting services",
    )
    install_cmd.add_argument(
        "--keep-backups",
        type=int,
        default=10,
        help="Number of agent config backups to retain (default: 10)",
    )
    install_cmd.add_argument(
        "--create-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create agent config files if they do not exist (default: True)",
    )

    uninstall_cmd = subparsers.add_parser(
        "uninstall", help="Uninstall the devin-orchestrator service"
    )
    uninstall_cmd.add_argument(
        "--system", action="store_true", help="Uninstall a system service (requires root)"
    )
    uninstall_cmd.add_argument("--service-name", default="devin-orchestrator")
    uninstall_cmd.add_argument(
        "--deregister",
        action="store_true",
        help="Remove the MCP server from agent configs",
    )
    uninstall_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files or stopping services",
    )
    uninstall_cmd.add_argument(
        "--keep-backups",
        type=int,
        default=10,
        help="Number of agent config backups to retain (default: 10)",
    )

    upgrade_cmd = subparsers.add_parser(
        "upgrade", help="Upgrade the devin-orchestrator package with pip"
    )
    upgrade_cmd.add_argument(
        "--user",
        dest="user_install",
        action="store_true",
        default=True,
        help="Pass --user to pip when upgrading",
    )
    upgrade_cmd.add_argument(
        "--no-user", dest="user_install", action="store_false"
    )

    return parser


def install(argv: list[str] | None = None) -> int:
    """Entry point for the `install` subcommand."""
    parser = _build_parser("devin-orchestrator install")
    argv = list(argv) if argv is not None else []

    if not argv:
        parser.print_help()
        return 0

    if argv[0] in ("-h", "--help"):
        args = parser.parse_args(argv)
        return 0

    if argv[0] not in _SUBCOMMANDS:
        # Bare `devin-orchestrator install --service-name ...` defaults to the
        # `install` subcommand for a friendlier UX.
        argv = ["install", *argv]

    args = parser.parse_args(argv)

    if args.command == "uninstall":
        return _uninstall_service(
            system=args.system,
            service_name=args.service_name,
            dry_run=args.dry_run,
            deregister=args.deregister,
            keep_backups=args.keep_backups,
        )

    if args.command == "upgrade":
        return _upgrade_package(user=args.user_install)

    if args.command == "install":
        if not args.dry_run and args.system and not args.run_as:
            print("--run-as is required for --system installs.", file=sys.stderr)
            return 2
        return _install_service(
            system=args.system,
            service_name=args.service_name,
            work_dir=Path(args.work_dir),
            user=args.run_as,
            command=args.exec_cmd,
            dry_run=args.dry_run,
            register=args.register,
            keep_backups=args.keep_backups,
            create_missing=args.create_missing,
        )

    parser.print_help()
    return 0


def _legacy_shim(legacy_name: str, argv: list[str] | None) -> int:
    if not os.environ.get("DEVIN_ORCHESTRATOR_NO_DEPRECATION"):
        warnings.warn(
            f"{legacy_name} is deprecated; use `devin-orchestrator install` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    argv = list(argv) if argv is not None else []
    if argv and argv[0] == "--uninstall":
        argv = ["uninstall", *argv[1:]]
    if argv and argv[0] == "--upgrade":
        argv = ["upgrade", *argv[1:]]
    return install(argv)


def install_py_main(argv: list[str] | None = None) -> int:
    return _legacy_shim("install.py", argv)


def deploy_py_main(argv: list[str] | None = None) -> int:
    return _legacy_shim("deploy.py", argv)

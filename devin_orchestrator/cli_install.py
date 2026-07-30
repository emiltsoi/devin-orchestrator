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
    unit_file.write_text(rendered, encoding="utf-8")
    print(f"Wrote systemd unit: {unit_file}")

    if not _smoke_test():
        print("Smoke test failed; run `devin-orchestrator doctor` for details.", file=sys.stderr)

    if not system:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", service_name], check=False)
        print(f"Enabled {service_name} for the current user.")
    else:
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "enable", service_name], check=False)
        print(f"Enabled {service_name} system-wide.")

    return 0


def _uninstall_service(system: bool, service_name: str) -> int:
    if system:
        unit_dir = Path("/etc/systemd/system")
        systemctl = ["systemctl"]
    else:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        systemctl = ["systemctl", "--user"]

    unit_file = unit_dir / f"{service_name}.service"
    if unit_file.exists():
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

    uninstall_cmd = subparsers.add_parser(
        "uninstall", help="Uninstall the devin-orchestrator service"
    )
    uninstall_cmd.add_argument(
        "--system", action="store_true", help="Uninstall a system service (requires root)"
    )
    uninstall_cmd.add_argument("--service-name", default="devin-orchestrator")

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
        return _uninstall_service(system=args.system, service_name=args.service_name)

    if args.command == "upgrade":
        return _upgrade_package(user=args.user_install)

    if args.command == "install":
        if args.system and not args.run_as:
            print("--run-as is required for --system installs.", file=sys.stderr)
            return 2
        return _install_service(
            system=args.system,
            service_name=args.service_name,
            work_dir=Path(args.work_dir),
            user=args.run_as,
            command=args.exec_cmd,
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

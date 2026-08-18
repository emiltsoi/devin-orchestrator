from __future__ import annotations

import argparse
import getpass  # noqa: F401
import os
import shutil
import subprocess  # nosec
import sys
import warnings
from pathlib import Path

import devin_orchestrator.register_mcp as _register_mcp
from devin_orchestrator.cli_install_platform import (
    _install_launchd,
    _install_systemd,
    _install_windows,
    _platform,
    _render_template,  # noqa: F401
    _smoke_test,
    _uninstall_launchd,
    _uninstall_systemd,
    _uninstall_windows,
    _validate_rendered,  # noqa: F401
    _xml_escape,  # noqa: F401
)


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
    global_root: Path | None = None,
    python_arg: str | None = None,
    source_dir: Path | None = None,
    skip_smoke: bool = False,
    extra_args: list[str] | None = None,
) -> int:
    del source_dir  # Legacy no-op

    if command is None:
        python = python_arg or sys.executable
        command = [python, "-m", "devin_orchestrator.mcp_server"]

    exec_start = " ".join(str(c) for c in command)
    platform = _platform()

    if platform == "launchd":
        result = _install_launchd(
            service_name, work_dir, command, system, dry_run, skip_smoke
        )
    elif platform == "windows":
        result = _install_windows(
            service_name, work_dir, command, system, dry_run, user, skip_smoke
        )
    else:
        result = _install_systemd(
            service_name, work_dir, user, exec_start, system, dry_run, skip_smoke
        )
    if result != 0:
        return result

    if register:
        results = _register_mcp.register(
            dry_run=dry_run,
            create_missing=create_missing,
            keep_backups=keep_backups,
            global_root=global_root,
            extra_args=extra_args,
        )
        for target, changed in results:
            action = (
                "Would update"
                if dry_run and changed
                else ("Updated" if changed else "No change")
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
                "Would remove"
                if dry_run and changed
                else ("Removed" if changed else "No change")
            )
            print(f"{action:<13} {target['name']:<12} {target['path']}")

    platform = _platform()
    if platform == "launchd":
        return _uninstall_launchd(service_name, system, dry_run)
    if platform == "windows":
        return _uninstall_windows(service_name, system, dry_run)
    return _uninstall_systemd(service_name, system, dry_run)


def _upgrade_package(user: bool) -> int:
    pip = shutil.which("pip") or shutil.which("pip3") or sys.executable
    if pip == sys.executable:
        cmd = [pip, "-m", "pip", "install", "--upgrade", "devin-orchestrator"]
    else:
        cmd = [pip, "install", "--upgrade", "devin-orchestrator"]
    if user:
        cmd.append("--user")
    return subprocess.run(cmd).returncode  # noqa: S603 - pip path is resolved with shutil.which


_SUBCOMMANDS = ("install", "uninstall", "upgrade")


def _build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Install, uninstall, or upgrade devin-orchestrator as a system service.",
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
        "--global-root",
        type=Path,
        default=None,
        help="Path to the devin-orchestrator global root for agent configs",
    )
    install_cmd.add_argument(
        "--python",
        default=None,
        help="Python executable to use in the service command",
    )
    install_cmd.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Legacy no-op option kept for install.py compatibility",
    )
    install_cmd.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the post-install smoke test",
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
    install_cmd.add_argument(
        "--message-log",
        nargs="?",
        const=str(_register_mcp.DEFAULT_MESSAGE_LOG),
        default=None,
        help="Append --message-log to the registered MCP server args (default: %(const)s)",
    )

    uninstall_cmd = subparsers.add_parser(
        "uninstall", help="Uninstall the devin-orchestrator service"
    )
    uninstall_cmd.add_argument(
        "--system",
        action="store_true",
        help="Uninstall a system service (requires root)",
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
    upgrade_cmd.add_argument("--no-user", dest="user_install", action="store_false")

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
        extra_args: list[str] | None = None
        if args.message_log is not None:
            extra_args = ["--message-log", args.message_log]
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
            global_root=args.global_root,
            python_arg=args.python,
            source_dir=args.source_dir,
            skip_smoke=args.skip_smoke,
            extra_args=extra_args,
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

    if legacy_name == "deploy.py":
        if "--list" in argv:
            _register_mcp.list_status()
            return 0
        if "--smoke-only" in argv:
            print("Running smoke test with launcher: devin-orchestrator")
            if _smoke_test():
                print("Smoke test OK")
                return 0
            print("Smoke test FAILED", file=sys.stderr)
            return 1

    if "--uninstall" in argv:
        argv.remove("--uninstall")
        argv = ["uninstall", "--deregister", *argv]
    if "--upgrade" in argv:
        argv.remove("--upgrade")
        argv = ["upgrade", *argv]

    for old, new in (("--skip-register", "--no-register"),):
        argv = [new if a == old else a for a in argv]

    if argv and argv[0] not in _SUBCOMMANDS and not argv[0].startswith("-"):
        # install.py [global_root] [source_dir]
        new_argv: list[str] = ["--global-root", argv[0]]
        rest = argv[1:]
        if rest and not rest[0].startswith("-"):
            new_argv.extend(["--source-dir", rest[0]])
            rest = rest[1:]
        argv = [*new_argv, *rest]

    return install(argv)


def install_py_main(argv: list[str] | None = None) -> int:
    return _legacy_shim("install.py", argv)


def deploy_py_main(argv: list[str] | None = None) -> int:
    return _legacy_shim("deploy.py", argv)

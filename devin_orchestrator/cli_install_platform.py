#!/usr/bin/env python3
"""Platform-specific service installation helpers for devin-orchestrator."""

from __future__ import annotations

import getpass
import importlib.resources
import os
import re
import subprocess  # nosec
import sys
from pathlib import Path


def _smoke_test() -> bool:
    try:
        result = subprocess.run(  # nosec: S603 - uses sys.executable
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
    _validate_rendered(template_name, text)
    return text


def _validate_rendered(template_name: str, text: str) -> None:
    """Raise ValueError if the rendered template has obvious problems."""
    if re.search(r"\{\{\s*\w+\s*\}\}", text):
        raise ValueError(f"Unsubstituted placeholders left in {template_name}")

    if template_name.endswith(".service"):
        if "[Unit]" not in text or "[Service]" not in text or "ExecStart=" not in text:
            raise ValueError(
                f"systemd unit {template_name} missing required sections or ExecStart"
            )
        return

    if template_name.endswith(".plist"):
        try:
            import plistlib

            plistlib.loads(text.encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException) as e:
            raise ValueError(
                f"launchd plist {template_name} is not valid XML: {e}"
            ) from e
        return

    if template_name.endswith(".bat"):
        if not text.startswith("@echo off"):
            raise ValueError(
                f"batch wrapper {template_name} should start with '@echo off'"
            )
        return


def _platform() -> str:
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform == "win32":
        return "windows"
    return "systemd"


def _xml_escape(text: str) -> str:
    from xml.sax.saxutils import escape  # nosec

    return escape(text)


def _install_systemd(
    service_name: str,
    work_dir: Path,
    user: str,
    exec_start: str,
    system: bool,
    dry_run: bool,
    skip_smoke: bool,
) -> int:
    if system:
        unit_dir = Path("/etc/systemd/system")
    else:
        unit_dir = Path.home() / ".config" / "systemd" / "user"

    if not unit_dir.exists():
        unit_dir.mkdir(parents=True, exist_ok=True)

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

    if not skip_smoke and not dry_run and not _smoke_test():
        print(
            "Smoke test failed; run `devin-orchestrator doctor` for details.",
            file=sys.stderr,
        )

    if not dry_run and not system:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)  # noqa: S603,S607 - trusted platform service utility
        subprocess.run(["systemctl", "--user", "enable", service_name], check=False)  # noqa: S603,S607 - trusted platform service utility
        print(f"Enabled {service_name} for the current user.")
    elif not dry_run:
        subprocess.run(["systemctl", "daemon-reload"], check=False)  # noqa: S603,S607 - trusted platform service utility
        subprocess.run(["systemctl", "enable", service_name], check=False)  # noqa: S603,S607 - trusted platform service utility
        print(f"Enabled {service_name} system-wide.")

    return 0


def _uninstall_systemd(service_name: str, system: bool, dry_run: bool) -> int:
    if system:
        unit_dir = Path("/etc/systemd/system")
        systemctl = ["systemctl"]
    else:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        systemctl = ["systemctl", "--user"]

    unit_file = unit_dir / f"{service_name}.service"
    if not unit_file.exists():
        if dry_run:
            print(f"Would remove service unit: {unit_file} (not present)")
            return 0
        print(f"Service unit not found: {unit_file}")
        return 1
    if dry_run:
        print(f"Would remove service unit: {unit_file}")
    else:
        subprocess.run([*systemctl, "stop", service_name], check=False)  # noqa: S603,S607 - trusted platform service utility
        subprocess.run([*systemctl, "disable", service_name], check=False)  # noqa: S603,S607 - trusted platform service utility
        unit_file.unlink()
        subprocess.run([*systemctl, "daemon-reload"], check=False)  # noqa: S603,S607 - trusted platform service utility
        print(f"Removed {unit_file}")
    return 0


def _install_launchd(
    service_name: str,
    work_dir: Path,
    command: list[str],
    system: bool,
    dry_run: bool,
    skip_smoke: bool,
) -> int:
    if system:
        plist_dir = Path("/Library/LaunchDaemons")
        log_dir = Path("/var/log")
    else:
        plist_dir = Path.home() / "Library/LaunchAgents"
        log_dir = Path.home() / "Library/Logs"

    plist_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    plist_path = plist_dir / f"{service_name}.plist"
    program_arguments = "\n".join(
        f"        <string>{_xml_escape(str(c))}</string>" for c in command
    )
    rendered = _render_template(
        "devin-orchestrator.plist",
        {
            "service_name": service_name,
            "program_arguments": program_arguments,
            "work_dir": str(work_dir),
            "log_dir": str(log_dir),
        },
    )

    if dry_run:
        print(f"Would write launchd plist: {plist_path}")
    else:
        plist_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote launchd plist: {plist_path}")

    if not skip_smoke and not dry_run and not _smoke_test():
        print(
            "Smoke test failed; run `devin-orchestrator doctor` for details.",
            file=sys.stderr,
        )

    if not dry_run:
        subprocess.run(["launchctl", "load", "-w", str(plist_path)], check=False)  # noqa: S603,S607 - trusted platform service utility
        print(f"Loaded {service_name}")

    return 0


def _uninstall_launchd(service_name: str, system: bool, dry_run: bool) -> int:
    if system:
        plist_dir = Path("/Library/LaunchDaemons")
    else:
        plist_dir = Path.home() / "Library/LaunchAgents"

    plist_path = plist_dir / f"{service_name}.plist"
    if not plist_path.exists():
        if dry_run:
            print(f"Would remove launchd plist: {plist_path} (not present)")
            return 0
        print(f"Launchd plist not found: {plist_path}")
        return 1
    if dry_run:
        print(f"Would remove launchd plist: {plist_path}")
    else:
        subprocess.run(["launchctl", "unload", "-w", str(plist_path)], check=False)  # noqa: S603,S607 - trusted platform service utility
        plist_path.unlink()
        print(f"Removed {plist_path}")
    return 0


def _install_windows(
    service_name: str,
    work_dir: Path,
    command: list[str],
    system: bool,
    dry_run: bool,
    user: str,
    skip_smoke: bool,
) -> int:
    if system:
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    else:
        base = Path.home() / "AppData/Roaming"
    bat_dir = base / "devin-orchestrator"
    bat_path = bat_dir / f"{service_name}.bat"

    exec_start = subprocess.list2cmdline([str(c) for c in command])
    rendered = _render_template(
        "devin-orchestrator.bat",
        {
            "work_dir": str(work_dir),
            "exec_start": exec_start,
        },
    )

    if dry_run:
        print(f"Would write Windows batch wrapper: {bat_path}")
        print(f"Would create scheduled task: {service_name}")
    else:
        bat_dir.mkdir(parents=True, exist_ok=True)
        bat_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {bat_path}")

        if not skip_smoke and not _smoke_test():
            print(
                "Smoke test failed; run `devin-orchestrator doctor` for details.",
                file=sys.stderr,
            )

        task_args = [
            "schtasks",
            "/create",
            "/tn",
            service_name,
            "/tr",
            str(bat_path),
            "/sc",
            "onlogon",
            "/ru",
            "SYSTEM" if system else user,
            "/f",
        ]
        if system:
            task_args.extend(["/rl", "HIGHEST"])
        elif user == getpass.getuser():
            task_args.append("/np")
        result = subprocess.run(task_args, check=False)  # noqa: S603,S607 - trusted platform service utility
        if result.returncode != 0:
            print(
                "Failed to create scheduled task. "
                "Run as Administrator for a system install, "
                "or ensure the target user does not require a password if /np was rejected.",
                file=sys.stderr,
            )
        else:
            print(f"Created scheduled task {service_name}")

    return 0


def _uninstall_windows(service_name: str, system: bool, dry_run: bool) -> int:
    if dry_run:
        print(f"Would remove Windows scheduled task: {service_name}")
    else:
        subprocess.run(["schtasks", "/delete", "/tn", service_name, "/f"], check=False)  # noqa: S603,S607 - trusted platform service utility
        if system:
            bat_path = (
                Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
                / "devin-orchestrator"
                / f"{service_name}.bat"
            )
        else:
            bat_path = (
                Path.home()
                / "AppData/Roaming/devin-orchestrator"
                / f"{service_name}.bat"
            )
        bat_path.unlink(missing_ok=True)
        print(f"Removed scheduled task {service_name}")
    return 0

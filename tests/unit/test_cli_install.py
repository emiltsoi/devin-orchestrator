"""Unit tests for the install/uninstall/upgrade CLI subcommand."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from devin_orchestrator import cli_install

if TYPE_CHECKING:
    import pytest


class _FakeRun:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: Any) -> MagicMock:
        self.calls.append(cmd)
        mock = MagicMock()
        mock.returncode = self.returncode
        return mock


def test_render_template():
    rendered = cli_install._render_template(
        "devin-orchestrator.service",
        {
            "exec_start": "python -m devin_orchestrator.mcp_server",
            "work_dir": "/tmp",
            "user": "emil",
        },
    )
    assert "ExecStart=python -m devin_orchestrator.mcp_server" in rendered
    assert "WorkingDirectory=/tmp" in rendered
    assert "User=emil" in rendered


def test_install_service_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install, "_platform", lambda: "systemd")
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path / "work",
        user="emil",
        register=False,
    )

    assert result == 0
    unit_file = tmp_path / ".config" / "systemd" / "user" / "devin-orchestrator.service"
    assert unit_file.exists()
    assert "ExecStart=" in unit_file.read_text()
    assert any(
        call[0] == "systemctl" and call[1] == "--user" for call in fake_run.calls
    )


def test_install_service_smoke_failure_is_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_run = _FakeRun(returncode=1)
    monkeypatch.setattr(cli_install, "_platform", lambda: "systemd")
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path,
        user="emil",
        register=False,
    )
    assert result == 0


def test_uninstall_service_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install, "_platform", lambda: "systemd")
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit_file = unit_dir / "devin-orchestrator.service"
    unit_file.write_text("unit")

    result = cli_install._uninstall_service(
        system=False, service_name="devin-orchestrator"
    )
    assert result == 0
    assert not unit_file.exists()
    assert any(
        call == ["systemctl", "--user", "stop", "devin-orchestrator"]
        for call in fake_run.calls
    )


def test_uninstall_service_missing_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(cli_install, "_platform", lambda: "systemd")
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)
    result = cli_install._uninstall_service(
        system=False, service_name="devin-orchestrator"
    )
    assert result == 1


def test_install_cli_routes_uninstall(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[bool, str]] = []

    def fake_uninstall(system, service_name, **kwargs):
        calls.append((system, service_name))
        return 0

    monkeypatch.setattr(cli_install, "_uninstall_service", fake_uninstall)
    result = cli_install.install(["uninstall", "--system", "--service-name", "x"])
    assert result == 0
    assert calls == [(True, "x")]


def test_install_cli_routes_upgrade(monkeypatch: pytest.MonkeyPatch):
    calls: list[bool] = []

    def fake_upgrade(user):
        calls.append(user)
        return 0

    monkeypatch.setattr(cli_install, "_upgrade_package", fake_upgrade)
    result = cli_install.install(["upgrade", "--no-user"])
    assert result == 0
    assert calls == [False]


def test_install_cli_routes_install_bare_default(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    def fake_install(system, service_name, work_dir, user, command=None, **kwargs):
        calls.append(
            {
                "system": system,
                "service_name": service_name,
                "work_dir": str(work_dir),
                "user": user,
                "command": command,
            }
        )
        return 0

    monkeypatch.setattr(cli_install, "_install_service", fake_install)
    result = cli_install.install(
        ["--service-name", "x", "--work-dir", "/tmp", "--run-as", "bob"]
    )
    assert result == 0
    assert calls == [
        {
            "system": False,
            "service_name": "x",
            "work_dir": str(Path("/tmp")),
            "user": "bob",
            "command": None,
        }
    ]


def test_install_cli_routes_install_explicit(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    def fake_install(system, service_name, work_dir, user, command=None, **kwargs):
        calls.append(
            {
                "system": system,
                "service_name": service_name,
                "work_dir": str(work_dir),
                "user": user,
                "command": command,
            }
        )
        return 0

    monkeypatch.setattr(cli_install, "_install_service", fake_install)
    result = cli_install.install(
        ["install", "--service-name", "x", "--work-dir", "/tmp", "--run-as", "bob"]
    )
    assert result == 0
    assert calls == [
        {
            "system": False,
            "service_name": "x",
            "work_dir": str(Path("/tmp")),
            "user": "bob",
            "command": None,
        }
    ]


def test_install_py_main_deprecation_and_routing(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_install(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(cli_install, "install", fake_install)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = cli_install.install_py_main(["--uninstall"])
        assert result == 0
        assert calls == [["uninstall", "--deregister"]]
        assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_deploy_py_main_deprecation(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def fake_install(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(cli_install, "install", fake_install)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = cli_install.deploy_py_main(["--upgrade"])
        assert result == 0
        assert calls == [["upgrade"]]
        assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_install_launchd_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install, "_platform", lambda: "launchd")
    monkeypatch.setattr(cli_install, "_smoke_test", lambda: True)
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path / "work",
        user="emil",
        register=False,
        skip_smoke=True,
    )
    assert result == 0

    plist_path = tmp_path / "Library" / "LaunchAgents" / "devin-orchestrator.plist"
    assert plist_path.exists()
    plist_text = plist_path.read_text()
    assert "<string>devin_orchestrator.mcp_server</string>" in plist_text
    assert "<string>-m</string>" in plist_text
    assert any(
        call == ["launchctl", "load", "-w", str(plist_path)] for call in fake_run.calls
    )


def test_uninstall_launchd_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install, "_platform", lambda: "launchd")
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    plist_dir = tmp_path / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True)
    plist_path = plist_dir / "devin-orchestrator.plist"
    plist_path.write_text("plist")

    result = cli_install._uninstall_service(
        system=False, service_name="devin-orchestrator"
    )
    assert result == 0
    assert not plist_path.exists()
    assert any(
        call == ["launchctl", "unload", "-w", str(plist_path)]
        for call in fake_run.calls
    )


def test_install_windows_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install, "_platform", lambda: "windows")
    monkeypatch.setattr(cli_install, "_smoke_test", lambda: True)
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli_install.getpass, "getuser", lambda: "emil")
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path / "work",
        user="emil",
        register=False,
        skip_smoke=True,
    )
    assert result == 0

    bat_path = (
        tmp_path
        / "AppData"
        / "Roaming"
        / "devin-orchestrator"
        / "devin-orchestrator.bat"
    )
    assert bat_path.exists()
    bat_text = bat_path.read_text()
    assert "devin_orchestrator.mcp_server" in bat_text
    assert any(
        call[0] == "schtasks"
        and "/create" in call
        and "/ru" in call
        and "emil" in call
        and "/np" in call
        for call in fake_run.calls
    )


def test_uninstall_windows_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install, "_platform", lambda: "windows")
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))

    bat_dir = tmp_path / "AppData" / "Roaming" / "devin-orchestrator"
    bat_dir.mkdir(parents=True)
    bat_path = bat_dir / "devin-orchestrator.bat"
    bat_path.write_text("bat")

    result = cli_install._uninstall_service(
        system=False, service_name="devin-orchestrator"
    )
    assert result == 0
    assert not bat_path.exists()
    assert any(
        call == ["schtasks", "/delete", "/tn", "devin-orchestrator", "/f"]
        for call in fake_run.calls
    )


def test_install_service_routes_to_launchd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    calls: list[tuple[str, list[str]]] = []

    def fake_install(name, *args, **kwargs):
        calls.append((name, args))
        return 0

    monkeypatch.setattr(cli_install, "_platform", lambda: "launchd")
    monkeypatch.setattr(
        cli_install, "_install_launchd", lambda *a, **k: fake_install("launchd", a)
    )
    monkeypatch.setattr(
        cli_install, "_install_windows", lambda *a, **k: fake_install("windows", a)
    )
    monkeypatch.setattr(
        cli_install, "_install_systemd", lambda *a, **k: fake_install("systemd", a)
    )
    monkeypatch.setattr(cli_install, "_smoke_test", lambda: True)
    monkeypatch.setattr(cli_install.subprocess, "run", _FakeRun())
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(cli_install._register_mcp, "register", lambda **_: [])

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path,
        user="emil",
        register=False,
        skip_smoke=True,
    )
    assert result == 0
    assert calls and calls[0][0] == "launchd"


def test_install_service_routes_to_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    calls: list[tuple[str, list[str]]] = []

    def fake_install(name, *args, **kwargs):
        calls.append((name, args))
        return 0

    monkeypatch.setattr(cli_install, "_platform", lambda: "windows")
    monkeypatch.setattr(
        cli_install, "_install_launchd", lambda *a, **k: fake_install("launchd", a)
    )
    monkeypatch.setattr(
        cli_install, "_install_windows", lambda *a, **k: fake_install("windows", a)
    )
    monkeypatch.setattr(
        cli_install, "_install_systemd", lambda *a, **k: fake_install("systemd", a)
    )
    monkeypatch.setattr(cli_install, "_smoke_test", lambda: True)
    monkeypatch.setattr(cli_install.subprocess, "run", _FakeRun())
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    monkeypatch.setattr(cli_install._register_mcp, "register", lambda **_: [])

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path,
        user="emil",
        register=False,
        skip_smoke=True,
    )
    assert result == 0
    assert calls and calls[0][0] == "windows"


def test_install_cli_message_log_explicit(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    def fake_install(**kwargs):
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(cli_install, "_install_service", fake_install)
    result = cli_install.install(["install", "--message-log", "/tmp/mcp-server.jsonl"])
    assert result == 0
    assert calls[0]["extra_args"] == ["--message-log", "/tmp/mcp-server.jsonl"]


def test_install_cli_message_log_default(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    def fake_install(**kwargs):
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(cli_install, "_install_service", fake_install)
    result = cli_install.install(["install", "--message-log"])
    assert result == 0
    assert calls[0]["extra_args"][0] == "--message-log"
    assert calls[0]["extra_args"][1].endswith("mcp-server.jsonl")

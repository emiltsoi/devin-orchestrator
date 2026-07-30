"""Unit tests for the install/uninstall/upgrade CLI subcommand."""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from devin_orchestrator import cli_install

if TYPE_CHECKING:
    from pathlib import Path

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
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path / "work",
        user="emil",
    )

    assert result == 0
    unit_file = tmp_path / ".config" / "systemd" / "user" / "devin-orchestrator.service"
    assert unit_file.exists()
    assert "ExecStart=" in unit_file.read_text()
    assert any(call[0] == "systemctl" and call[1] == "--user" for call in fake_run.calls)


def test_install_service_smoke_failure_is_non_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun(returncode=1)
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    result = cli_install._install_service(
        system=False,
        service_name="devin-orchestrator",
        work_dir=tmp_path,
        user="emil",
    )
    assert result == 0


def test_uninstall_service_user_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_run = _FakeRun()
    monkeypatch.setattr(cli_install.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)

    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit_file = unit_dir / "devin-orchestrator.service"
    unit_file.write_text("unit")

    result = cli_install._uninstall_service(system=False, service_name="devin-orchestrator")
    assert result == 0
    assert not unit_file.exists()
    assert any(call == ["systemctl", "--user", "stop", "devin-orchestrator"] for call in fake_run.calls)


def test_uninstall_service_missing_unit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli_install.Path, "home", lambda: tmp_path)
    result = cli_install._uninstall_service(system=False, service_name="devin-orchestrator")
    assert result == 1


def test_install_cli_routes_uninstall(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[bool, str]] = []

    def fake_uninstall(system, service_name):
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

    def fake_install(system, service_name, work_dir, user, command=None):
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
            "work_dir": "/tmp",
            "user": "bob",
            "command": None,
        }
    ]


def test_install_cli_routes_install_explicit(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    def fake_install(system, service_name, work_dir, user, command=None):
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
            "work_dir": "/tmp",
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
        assert calls == [["uninstall"]]
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

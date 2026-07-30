"""Unit tests for devin_orchestrator.cli."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from devin_orchestrator import cli


class TestCliMain:
    def test_help(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main(["devin-orchestrator", "--help"])
        assert exc.value.code == 0

    def test_no_subcommand_prints_help(self, capsys):
        code = cli.main(["devin-orchestrator"])
        assert code == 0

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main(["devin-orchestrator", "--version"])
        assert exc.value.code == 0


class TestCliDoctor:
    def test_doctor(self):
        with patch("devin_orchestrator.doctor.main") as doctor_main:
            doctor_main.return_value = 0
            code = cli.main(["devin-orchestrator", "doctor"])
        assert code == 0
        doctor_main.assert_called_once()


class TestCliHealth:
    def test_health(self):
        with patch("devin_orchestrator.health_cli.main") as health_main:
            health_main.return_value = 0
            code = cli.main(["devin-orchestrator", "health"])
        assert code == 0
        health_main.assert_called_once_with([])

    def test_health_with_work_dir(self):
        with patch("devin_orchestrator.health_cli.main") as health_main:
            health_main.return_value = 0
            cli.main(["devin-orchestrator", "health", "--work-dir", "/tmp"])
        assert health_main.call_args[0][0] == ["--work-dir", "/tmp"]


class TestCliDispatch:
    def test_dispatch_devin(self):
        with (
            patch("devin_orchestrator.dispatch_devin.main") as dispatch_main,
            patch("devin_orchestrator.dispatch_skill.main") as skill_main,
        ):
            dispatch_main.return_value = 0
            code = cli.main(
                [
                    "devin-orchestrator",
                    "dispatch",
                    "--role",
                    "coder",
                    "--prompt-file",
                    "/tmp/p.md",
                ]
            )
        assert code == 0
        dispatch_main.assert_called_once_with(
            ["--role", "coder", "--prompt-file", "/tmp/p.md"]
        )
        skill_main.assert_not_called()

    def test_dispatch_skill(self):
        with (
            patch("devin_orchestrator.dispatch_devin.main") as dispatch_main,
            patch("devin_orchestrator.dispatch_skill.main") as skill_main,
        ):
            skill_main.return_value = 0
            code = cli.main(
                [
                    "devin-orchestrator",
                    "dispatch",
                    "--skill-name",
                    "coder",
                    "--session-id",
                    "s1",
                    "--workspace",
                    "/tmp",
                ]
            )
        assert code == 0
        skill_main.assert_called_once()
        dispatch_main.assert_not_called()

    def test_dispatch_skill_positional(self):
        with (
            patch("devin_orchestrator.dispatch_devin.main") as dispatch_main,
            patch("devin_orchestrator.dispatch_skill.main") as skill_main,
        ):
            skill_main.return_value = 0
            code = cli.main(["devin-orchestrator", "dispatch", "coder", "s1", "/tmp"])
        assert code == 0
        skill_main.assert_called_once()
        dispatch_main.assert_not_called()

    def test_dispatch_empty(self):
        code = cli.main(["devin-orchestrator", "dispatch"])
        assert code == 2


class TestCliMcp:
    def test_mcp(self):
        with patch("devin_orchestrator.mcp_server.main") as mcp_main:
            mcp_main.return_value = None
            code = cli.main(["devin-orchestrator", "mcp", "--workspace", "/tmp"])
        assert code == 0
        mcp_main.assert_called_once_with(["--workspace", "/tmp"])


class TestLegacyShims:
    def test_dispatch_devin_legacy_routes_and_warns(self):
        with (
            patch("devin_orchestrator.dispatch_devin.main") as dispatch_main,
            patch("warnings.warn") as warn,
        ):
            dispatch_main.return_value = 0
            code = cli.main(
                ["dispatch-devin", "--role", "coder", "--prompt-file", "/tmp/p.md"]
            )
        assert code == 0
        warn.assert_called_once()
        dispatch_main.assert_called_once()

    def test_dispatch_skill_legacy_routes_and_warns(self):
        with (
            patch("devin_orchestrator.dispatch_skill.main") as skill_main,
            patch("warnings.warn") as warn,
        ):
            skill_main.return_value = 0
            code = cli.main(["dispatch-skill", "coder", "s1", "/tmp"])
        assert code == 0
        warn.assert_called_once()
        skill_main.assert_called_once()

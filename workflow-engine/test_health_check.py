"""
Tests for health_check.py

Covers HealthChecker routines with mocked ConfigLoader and subprocess so
no real Devin CLI invocation or filesystem dependency on the host is
required.
"""

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from health_check import HealthChecker, HealthCheckResult


@dataclass
class _FakeConfig:
    global_root: Path
    skills_dir: Path
    workflows_dir: Path
    workflow_engine_dir: Path
    devin_cli_path: str
    default_model: str = "swe-1.6"
    default_permission_mode: str = "dangerous"


def _make_checker_with_config(tmp_path: Path, *, skills=True, workflows=True) -> HealthChecker:
    checker = HealthChecker()
    checker.config = _FakeConfig(
        global_root=tmp_path / "root",
        skills_dir=tmp_path / "skills",
        workflows_dir=tmp_path / "workflows",
        workflow_engine_dir=tmp_path / "engine",
        devin_cli_path=str(tmp_path / "devin.exe"),
    )
    if skills:
        (tmp_path / "skills" / "demo").mkdir(parents=True)
    if workflows:
        (tmp_path / "workflows").mkdir(parents=True)
        (tmp_path / "workflows" / "demo.yaml").write_text("name: demo\n", encoding="utf-8")
    return checker


class TestCheckConfigFile:
    def test_healthy_config(self, tmp_path):
        checker = HealthChecker()
        fake_cfg = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(tmp_path / "devin.exe"),
        )
        config_path = tmp_path / "config.yaml"
        config_path.write_text("name: x\n", encoding="utf-8")
        with patch("health_check.ConfigLoader.load", return_value=fake_cfg), patch(
            "health_check.ConfigLoader.DEFAULT_CONFIG_PATH", config_path
        ):
            result = checker.check_config_file()
        assert result.component == "config_file"
        assert result.status == "healthy"
        assert result.details["default_permission_mode"] == "dangerous"

    def test_missing_config_file(self, tmp_path):
        checker = HealthChecker()
        fake_cfg = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(tmp_path / "devin.exe"),
        )
        missing = tmp_path / "missing.yaml"
        with patch("health_check.ConfigLoader.load", return_value=fake_cfg), patch(
            "health_check.ConfigLoader.DEFAULT_CONFIG_PATH", missing
        ), patch("health_check.ConfigLoader.FALLBACK_CONFIG_PATH", missing):
            result = checker.check_config_file()
        assert result.status == "error"
        assert "Config file not found" in result.message

    def test_load_exception_returns_error(self, tmp_path):
        checker = HealthChecker()
        with patch("health_check.ConfigLoader.load", side_effect=RuntimeError("boom")):
            result = checker.check_config_file()
        assert result.status == "error"
        assert "boom" in result.message


class TestCheckSkillsDirectory:
    def test_no_config_returns_error(self):
        checker = HealthChecker()
        result = checker.check_skills_directory()
        assert result.status == "error"
        assert "Config not loaded" in result.message

    def test_missing_directory(self, tmp_path):
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        result = checker.check_skills_directory()
        assert result.status == "error"
        assert "does not exist" in result.message

    def test_empty_directory_is_warning(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=skills,
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        result = checker.check_skills_directory()
        assert result.status == "warning"
        assert result.details["skill_count"] == 0

    def test_populated_directory_is_healthy(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        (skills / "skill_a").mkdir()
        (skills / "skill_b").mkdir()
        (skills / "file.txt").write_text("not a dir", encoding="utf-8")
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=skills,
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        result = checker.check_skills_directory()
        assert result.status == "healthy"
        assert result.details["skill_count"] == 2

    def test_permission_error_returns_error(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir()
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=skills,
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            result = checker.check_skills_directory()
        assert result.status == "error"
        assert "permission denied" in result.message


class TestCheckWorkflowsDirectory:
    def test_no_config_returns_error(self):
        checker = HealthChecker()
        result = checker.check_workflows_directory()
        assert result.status == "error"

    def test_missing_directory(self, tmp_path):
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        result = checker.check_workflows_directory()
        assert result.status == "error"
        assert "does not exist" in result.message

    def test_empty_directory_is_warning(self, tmp_path):
        wf = tmp_path / "workflows"
        wf.mkdir()
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=wf,
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        result = checker.check_workflows_directory()
        assert result.status == "warning"
        assert result.details["workflow_count"] == 0

    def test_directory_with_yaml_files_healthy(self, tmp_path):
        wf = tmp_path / "workflows"
        wf.mkdir()
        (wf / "a.yaml").write_text("name: a\n", encoding="utf-8")
        (wf / "b.yml").write_text("name: b\n", encoding="utf-8")
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=wf,
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path="x",
        )
        result = checker.check_workflows_directory()
        assert result.status == "healthy"
        assert result.details["workflow_count"] == 2


class TestCheckDevinCli:
    def test_no_config_returns_error(self):
        checker = HealthChecker()
        result = checker.check_devin_cli()
        assert result.status == "error"

    def test_missing_cli_returns_error(self, tmp_path):
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(tmp_path / "nope.exe"),
        )
        result = checker.check_devin_cli()
        assert result.status == "error"
        assert "not found" in result.message

    def test_cli_path_is_directory_returns_error(self, tmp_path):
        cli_dir = tmp_path / "cli_dir"
        cli_dir.mkdir()
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(cli_dir),
        )
        result = checker.check_devin_cli()
        assert result.status == "error"
        assert "not a file" in result.message

    def test_cli_version_ok(self, tmp_path):
        cli = tmp_path / "devin.exe"
        cli.write_text("fake", encoding="utf-8")
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(cli),
        )
        with patch("health_check.subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "devin 1.2.3\n", "stderr": ""}
            )()
            result = checker.check_devin_cli()
        assert result.status == "healthy"
        assert result.details["version"] == "devin 1.2.3"

    def test_cli_version_nonzero_returncode_is_warning(self, tmp_path):
        cli = tmp_path / "devin.exe"
        cli.write_text("fake", encoding="utf-8")
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(cli),
        )
        with patch("health_check.subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 2, "stdout": "", "stderr": "oops"}
            )()
            result = checker.check_devin_cli()
        assert result.status == "warning"

    def test_cli_timeout_is_error(self, tmp_path):
        cli = tmp_path / "devin.exe"
        cli.write_text("fake", encoding="utf-8")
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(cli),
        )
        with patch(
            "health_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="devin", timeout=10),
        ):
            result = checker.check_devin_cli()
        assert result.status == "error"
        assert "timed out" in result.message

    def test_cli_subprocess_exception_is_error(self, tmp_path):
        cli = tmp_path / "devin.exe"
        cli.write_text("fake", encoding="utf-8")
        checker = HealthChecker()
        checker.config = _FakeConfig(
            global_root=tmp_path / "root",
            skills_dir=tmp_path / "skills",
            workflows_dir=tmp_path / "workflows",
            workflow_engine_dir=tmp_path / "engine",
            devin_cli_path=str(cli),
        )
        with patch("health_check.subprocess.run", side_effect=OSError("boom")):
            result = checker.check_devin_cli()
        assert result.status == "error"
        assert "boom" in result.message


class TestRunAllChecks:
    def test_overall_status_error_when_any_error(self, tmp_path):
        checker = HealthChecker()
        # No config file -> error path
        with patch.object(HealthChecker, "check_config_file") as cfg, patch.object(
            HealthChecker, "check_skills_directory"
        ) as skills, patch.object(
            HealthChecker, "check_workflows_directory"
        ) as wf, patch.object(HealthChecker, "check_devin_cli") as cli:
            cfg.return_value = HealthCheckResult("config_file", "error", "boom", {})
            skills.return_value = HealthCheckResult("skills", "healthy", "ok", {})
            wf.return_value = HealthCheckResult("workflows", "healthy", "ok", {})
            cli.return_value = HealthCheckResult("devin_cli", "healthy", "ok", {})
            report = checker.run_all_checks()
        assert report["overall_status"] == "error"
        assert report["summary"]["error"] == 1

    def test_overall_status_warning_when_only_warnings(self):
        checker = HealthChecker()
        with patch.object(HealthChecker, "check_config_file") as cfg, patch.object(
            HealthChecker, "check_skills_directory"
        ) as skills, patch.object(
            HealthChecker, "check_workflows_directory"
        ) as wf, patch.object(HealthChecker, "check_devin_cli") as cli:
            cfg.return_value = HealthCheckResult("config_file", "warning", "w", {})
            skills.return_value = HealthCheckResult("skills", "healthy", "ok", {})
            wf.return_value = HealthCheckResult("workflows", "healthy", "ok", {})
            cli.return_value = HealthCheckResult("devin_cli", "healthy", "ok", {})
            report = checker.run_all_checks()
        assert report["overall_status"] == "warning"
        assert report["summary"]["warning"] == 1

    def test_overall_status_healthy(self):
        checker = HealthChecker()
        with patch.object(HealthChecker, "check_config_file") as cfg, patch.object(
            HealthChecker, "check_skills_directory"
        ) as skills, patch.object(
            HealthChecker, "check_workflows_directory"
        ) as wf, patch.object(HealthChecker, "check_devin_cli") as cli:
            for m in (cfg, skills, wf, cli):
                m.return_value = HealthCheckResult("c", "healthy", "ok", {})
            report = checker.run_all_checks()
        assert report["overall_status"] == "healthy"
        assert report["summary"]["healthy"] == 4

    def test_print_report_outputs_all_sections(self, capsys):
        checker = HealthChecker()
        report = {
            "timestamp": "2026-01-01T00:00:00",
            "overall_status": "healthy",
            "summary": {"healthy": 1, "warning": 0, "error": 0, "total": 1},
            "checks": [
                {
                    "component": "config_file",
                    "status": "healthy",
                    "message": "ok",
                    "details": {"path": "/tmp/config.yaml", "list_field": ["a", "b"]},
                }
            ],
        }
        checker.print_report(report)
        out = capsys.readouterr().out
        assert "Health Check Report" in out
        assert "CONFIG_FILE" in out
        assert "list_field: a, b" in out

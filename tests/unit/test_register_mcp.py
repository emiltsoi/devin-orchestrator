"""Unit tests for devin_orchestrator.register_mcp."""

from __future__ import annotations

import json
import sys
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from devin_orchestrator import register_mcp


@pytest.fixture
def fake_console_script(tmp_path: Path) -> Path:
    """Return a fake devin-orchestrator console script."""
    script = tmp_path / "devin-orchestrator"
    script.write_text('#!/bin/sh\nexec python -m devin_orchestrator.cli "$@"\n')
    script.chmod(0o755)
    return script


@pytest.fixture
def fake_legacy_wrapper(tmp_path: Path) -> Path:
    """Return a fake legacy install.py wrapper around mcp_server.py."""
    script = tmp_path / "devin-orchestrator"
    script.write_text(
        "#!/bin/sh\n# devin-orchestrator MCP server launcher\n"
        'exec "/usr/bin/python3" "/home/user/.devin-orchestrator/mcp_server.py" "$@"\n'
    )
    script.chmod(0o755)
    return script


def test_devin_mcp_config_console_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_console_script: Path
):
    def _which(cmd: str) -> str | None:
        return str(fake_console_script) if cmd == "devin-orchestrator" else None

    monkeypatch.setattr(register_mcp.shutil, "which", _which)
    config = register_mcp.devin_mcp_config()
    assert config["command"] == str(fake_console_script)
    assert config.get("args") == ["mcp"]
    assert "instructions" in config


def test_devin_mcp_config_legacy_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_legacy_wrapper: Path
):
    def _which(cmd: str) -> str | None:
        return str(fake_legacy_wrapper) if cmd == "devin-orchestrator" else None

    monkeypatch.setattr(register_mcp.shutil, "which", _which)
    config = register_mcp.devin_mcp_config()
    assert config["command"] == str(fake_legacy_wrapper)
    assert "args" not in config
    assert "instructions" in config


def test_devin_mcp_config_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(register_mcp.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(register_mcp, "_launcher_path", lambda _gr=None: "/nonexistent")
    config = register_mcp.devin_mcp_config()
    assert config["command"] == sys.executable
    assert config.get("args") == ["-m", "devin_orchestrator.mcp_server"]
    assert "instructions" in config


def test_devin_mcp_config_with_extra_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    script = tmp_path / "devin-orchestrator"
    script.write_text('#!/bin/sh\nexec python -m devin_orchestrator.cli "$@"\n')
    script.chmod(0o755)

    monkeypatch.setattr(
        register_mcp.shutil,
        "which",
        lambda cmd: str(script) if cmd == "devin-orchestrator" else None,
    )
    config = register_mcp.devin_mcp_config(extra_args=["--message-log", "/tmp/mcp.log"])
    assert config["args"] == ["mcp", "--message-log", "/tmp/mcp.log"]


def test_print_snippet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_console_script: Path,
    capsys: pytest.CaptureFixture,
):
    monkeypatch.setattr(
        register_mcp.shutil,
        "which",
        lambda cmd: str(fake_console_script) if cmd == "devin-orchestrator" else None,
    )
    register_mcp.print_snippet()
    captured = capsys.readouterr()
    snippet = json.loads(captured.out)
    assert "mcpServers" in snippet
    assert "devin-orchestrator" in snippet["mcpServers"]
    assert snippet["mcpServers"]["devin-orchestrator"]["command"] == str(
        fake_console_script
    )


@pytest.fixture
def fake_targets(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        {
            "name": "devin",
            "path": tmp_path / "devin" / "mcp_config.json",
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
        {
            "name": "claude",
            "path": tmp_path / "claude.json",
            "format": "json",
            "root_key": "mcpServers",
            "default": {"mcpServers": {}},
            "create_if_missing": True,
        },
    ]


def test_register_create_and_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_targets: list[dict[str, Any]],
    fake_console_script: Path,
):
    def _which(cmd: str) -> str | None:
        return str(fake_console_script) if cmd == "devin-orchestrator" else None

    monkeypatch.setattr(register_mcp.shutil, "which", _which)
    monkeypatch.setattr(register_mcp, "_targets", lambda: fake_targets)

    results = register_mcp.register(keep_backups=0)
    names = {target["name"] for target, changed in results if changed}
    assert names == {"devin", "claude"}

    for target in fake_targets:
        data = json.loads(target["path"].read_text())
        assert "devin-orchestrator" in data["mcpServers"]
        assert data["mcpServers"]["devin-orchestrator"]["args"] == ["mcp"]

    # Second call should report no change.
    results = register_mcp.register(keep_backups=0)
    assert all(not changed for _, changed in results)


def test_register_respects_create_missing_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_targets: list[dict[str, Any]],
    fake_console_script: Path,
):
    monkeypatch.setattr(
        register_mcp.shutil,
        "which",
        lambda cmd: str(fake_console_script) if cmd == "devin-orchestrator" else None,
    )
    monkeypatch.setattr(register_mcp, "_targets", lambda: fake_targets)

    results = register_mcp.register(create_missing=False, keep_backups=0)
    for target, changed in results:
        assert not changed
        assert not target["path"].exists()


def test_remove_deletes_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_targets: list[dict[str, Any]],
    fake_console_script: Path,
):
    monkeypatch.setattr(
        register_mcp.shutil,
        "which",
        lambda cmd: str(fake_console_script) if cmd == "devin-orchestrator" else None,
    )
    monkeypatch.setattr(register_mcp, "_targets", lambda: fake_targets)

    # First register, then remove.
    register_mcp.register(keep_backups=0)
    results = register_mcp.remove(keep_backups=0)
    changed = {target["name"] for target, c in results if c}
    assert changed == {"devin", "claude"}

    for target in fake_targets:
        data = json.loads(target["path"].read_text())
        assert "devin-orchestrator" not in data["mcpServers"]

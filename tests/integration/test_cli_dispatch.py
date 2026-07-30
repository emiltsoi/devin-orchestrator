"""Integration tests for the unified CLI dispatch path."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from devin_orchestrator import cli

pytestmark = pytest.mark.integration


def test_cli_dispatch_devin():
    with patch("devin_orchestrator.dispatch_devin.main") as devin_main:
        devin_main.return_value = 0
        code = cli.main(
            [
                "devin-orchestrator",
                "dispatch",
                "--role",
                "coder",
                "--prompt-file",
                "/tmp/prompt.md",
            ]
        )
    assert code == 0
    devin_main.assert_called_once()
    args = devin_main.call_args[0][0]
    assert "--role" in args
    assert "--prompt-file" in args


def test_cli_dispatch_skill():
    with patch("devin_orchestrator.dispatch_skill.main") as skill_main:
        skill_main.return_value = 0
        code = cli.main(
            [
                "devin-orchestrator",
                "dispatch",
                "--skill-name",
                "coder",
                "--session-id",
                "SESSION-001",
                "--workspace",
                "/tmp/ws",
            ]
        )
    assert code == 0
    skill_main.assert_called_once()

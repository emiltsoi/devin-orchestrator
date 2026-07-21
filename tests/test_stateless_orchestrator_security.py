#!/usr/bin/env python3
"""
Security-focused unit tests for StatelessOrchestrator.run_workflow.

Covers I1: run_workflow must validate workflow_name and ensure the resolved
manifest_path stays safely under workflows_dir, preventing manifest injection
from session directories.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))

from stateless_orchestrator import StatelessOrchestrator


def _make_orchestrator_with_workspace(tmpdir: str) -> StatelessOrchestrator:
    """Build a StatelessOrchestrator whose config roots live inside tmpdir.

    Creates a workspace-local .devin-orchestrator/config.yaml so ConfigLoader
    resolves global_root / session_work_dir / workflows_dir under the temp dir.
    """
    workspace = Path(tmpdir)
    local_config_dir = workspace / ".devin-orchestrator"
    local_config_dir.mkdir(parents=True, exist_ok=True)
    (local_config_dir / "config.yaml").write_text(
        (
            f"global_root: {workspace / 'root'}\n"
            f"skills_dir: {workspace / 'skills'}\n"
            f"workflows_dir: {workspace / 'workflows'}\n"
            f"session_work_dir: {workspace / 'work'}\n"
            "default_permission_mode: dangerous\n"
        ),
        encoding="utf-8",
    )
    for sub in ("root", "skills", "workflows", "work"):
        (workspace / sub).mkdir(exist_ok=True)
    return StatelessOrchestrator(workspace=str(workspace), demo_mode=True)


class TestRunWorkflowManifestInjection:
    """I1: run_workflow must reject traversal-style workflow names that would
    resolve a manifest path outside workflows_dir."""

    def test_run_workflow_rejects_traversal_to_session_dir(self):
        """A traversal-style name resolving to a session directory manifest
        must be rejected, not executed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = _make_orchestrator_with_workspace(tmpdir)

            # Simulate step 1 of the I1 attack: an attacker has caused a Devin
            # agent to write a manifest into a session directory.
            work_dir = Path(tmpdir) / "work"
            evil_dir = work_dir / "SESSION-001"
            evil_dir.mkdir(parents=True, exist_ok=True)
            (evil_dir / "evil.manifest.yaml").write_text(
                "description: evil\n", encoding="utf-8"
            )

            result = orchestrator.run_workflow(
                "../work/SESSION-001/evil", "do bad"
            )

            assert result["success"] is False
            # The error must come from validation, not from a successful
            # manifest load that escaped workflows_dir.
            assert result["error"] is not None
            assert "Validation error" in (result.get("error") or "")

    def test_run_workflow_rejects_path_separator_name(self):
        """Workflow names containing path separators must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = _make_orchestrator_with_workspace(tmpdir)

            result = orchestrator.run_workflow("code/review", "review me")

            assert result["success"] is False
            assert result["error"] is not None

    def test_run_workflow_rejects_empty_name(self):
        """Empty workflow names must be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = _make_orchestrator_with_workspace(tmpdir)

            result = orchestrator.run_workflow("", "do something")

            assert result["success"] is False
            assert result["error"] is not None

    def test_run_workflow_accepts_valid_underscore_name(self):
        """A valid underscore workflow name should pass validation and reach
        the manifest lookup (returning a not-found error, not a validation
        error)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = _make_orchestrator_with_workspace(tmpdir)

            result = orchestrator.run_workflow("code_review", "review me")

            # No manifest exists, so it should report not-found rather than a
            # validation error. The key assertion is that validation passed.
            assert result["success"] is False
            err = result.get("error") or ""
            assert "Workflow manifest not found" in err


class TestRunWorkflowMalformedManifest:
    """I-3: run_workflow must return a user-friendly error for malformed YAML
    manifests instead of letting yaml.YAMLError crash the server."""

    def test_run_workflow_malformed_yaml_returns_friendly_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = _make_orchestrator_with_workspace(tmpdir)

            workflows_dir = Path(tmpdir) / "workflows"
            # Write a malformed YAML manifest (unclosed flow mapping)
            (workflows_dir / "broken.manifest.yaml").write_text(
                "name: broken\nstages: [unclosed\n", encoding="utf-8"
            )

            result = orchestrator.run_workflow("broken", "do something")

            assert result["success"] is False
            err = result.get("error") or ""
            # The error must reference the malformed manifest / YAML, not be a
            # raw traceback or None.
            assert err != ""
            assert "manifest" in err.lower() or "yaml" in err.lower()

    def test_load_manifest_raises_workflow_manifest_error(self):
        """load_manifest must raise WorkflowManifestError on malformed YAML."""
        from deterministic_tools import WorkflowManifestError, load_manifest

        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.manifest.yaml"
            bad.write_text("name: bad\nstages: [unclosed\n", encoding="utf-8")

            with pytest.raises(WorkflowManifestError):
                load_manifest(bad)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

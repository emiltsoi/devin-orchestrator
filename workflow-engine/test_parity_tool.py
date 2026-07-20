"""
Tests for parity_tool.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parity_tool import check_audit_run_jsonl_parity, check_manifest_runbook_parity


def test_audit_run_jsonl_parity():
    """Should detect matching audit and run.jsonl entries"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        audit = session_dir / "session-audit.md"
        run_jsonl = session_dir / "run.jsonl"

        audit.write_text(
            "## Stage: brainstorming\n## Stage: implementation\n", encoding="utf-8"
        )
        run_jsonl.write_text(
            json.dumps({"stage": "brainstorming"})
            + "\n"
            + json.dumps({"stage": "implementation"})
            + "\n",
            encoding="utf-8",
        )

        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is True
        assert sorted(report["matched"]) == ["brainstorming", "implementation"]


def test_audit_run_jsonl_parity_missing():
    """Should detect stage missing in run.jsonl"""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        audit = session_dir / "session-audit.md"
        run_jsonl = session_dir / "run.jsonl"

        audit.write_text(
            "## Stage: brainstorming\n## Stage: implementation\n", encoding="utf-8"
        )
        run_jsonl.write_text(
            json.dumps({"stage": "brainstorming"}) + "\n", encoding="utf-8"
        )

        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is False
        assert "implementation" in str(report["errors"])


def test_manifest_runbook_parity():
    """Should validate manifest and runbook stage parity"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows_dir = Path(tmpdir)
        manifest = workflows_dir / "feature.manifest.yaml"
        runbook = workflows_dir / "feature.runbook.md"

        manifest.write_text(
            "schema_version: 1\nname: feature\nstages:\n  - name: brainstorming\n  - name: implementation\n",
            encoding="utf-8",
        )
        runbook.write_text(
            "# Feature Runbook\n\nStage: brainstorming\nStage: implementation\n",
            encoding="utf-8",
        )

        report = check_manifest_runbook_parity(workflows_dir)
        assert report["valid"] is True


def test_manifest_runbook_parity_missing_runbook():
    """Should report missing runbook"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows_dir = Path(tmpdir)
        manifest = workflows_dir / "feature.manifest.yaml"
        manifest.write_text("schema_version: 1\nname: feature\n", encoding="utf-8")

        report = check_manifest_runbook_parity(workflows_dir)
        assert report["valid"] is False
        assert "Missing runbook" in str(report["errors"])


def test_audit_run_jsonl_parity_no_files():
    """Empty session dir should produce a valid (empty) parity report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is True
        assert report["audit_stages"] == set()
        assert report["run_stages"] == set()
        assert report["matched"] == []


def test_audit_run_jsonl_parity_only_audit_file():
    """Audit file with no run.jsonl should report missing-in-run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        (session_dir / "session-audit.md").write_text(
            "## Stage: brainstorming\n", encoding="utf-8"
        )
        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is False
        assert "brainstorming" in str(report["errors"])


def test_audit_run_jsonl_parity_only_run_file():
    """run.jsonl with no audit should report missing-in-audit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        (session_dir / "run.jsonl").write_text(
            json.dumps({"stage": "implementation"}) + "\n", encoding="utf-8"
        )
        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is False
        assert "implementation" in str(report["errors"])


def test_audit_run_jsonl_parity_invalid_json():
    """Invalid JSON lines in run.jsonl should be reported as errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        (session_dir / "run.jsonl").write_text(
            "not-json-at-all\n", encoding="utf-8"
        )
        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is True  # No stages to mismatch
        assert any("Invalid JSON" in e for e in report["errors"])


def test_audit_run_jsonl_parity_extra_stage_in_run():
    """Stage in run.jsonl but not audit should be flagged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        (session_dir / "session-audit.md").write_text(
            "## Stage: brainstorming\n", encoding="utf-8"
        )
        (session_dir / "run.jsonl").write_text(
            json.dumps({"stage": "brainstorming"}) + "\n"
            + json.dumps({"stage": "implementation"}) + "\n",
            encoding="utf-8",
        )
        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is False
        assert "implementation" in str(report["errors"])


def test_audit_run_jsonl_parity_entry_without_stage_ignored():
    """Entries without a 'stage' key should be silently ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir)
        (session_dir / "session-audit.md").write_text(
            "## Stage: brainstorming\n", encoding="utf-8"
        )
        (session_dir / "run.jsonl").write_text(
            json.dumps({"event": "no_stage"}) + "\n"
            + json.dumps({"stage": "brainstorming"}) + "\n",
            encoding="utf-8",
        )
        report = check_audit_run_jsonl_parity(session_dir)
        assert report["valid"] is True
        assert report["matched"] == ["brainstorming"]


def test_manifest_runbook_parity_missing_workflows_dir():
    """Missing workflows directory should be reported as invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows_dir = Path(tmpdir) / "does-not-exist"
        report = check_manifest_runbook_parity(workflows_dir)
        assert report["valid"] is False
        assert "Workflows directory not found" in str(report["errors"])


def test_manifest_runbook_parity_no_manifests():
    """Empty workflows dir should produce a soft warning, not invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows_dir = Path(tmpdir)
        report = check_manifest_runbook_parity(workflows_dir)
        assert report["valid"] is True
        assert any("No manifest files" in e for e in report["errors"])


def test_manifest_runbook_parity_stage_missing_in_runbook():
    """Manifest stage missing from runbook should be flagged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows_dir = Path(tmpdir)
        manifest = workflows_dir / "feature.manifest.yaml"
        runbook = workflows_dir / "feature.runbook.md"
        manifest.write_text(
            "schema_version: 1\nname: feature\nstages:\n"
            "  - name: brainstorming\n  - name: implementation\n",
            encoding="utf-8",
        )
        # Runbook only mentions brainstorming.
        runbook.write_text("# Runbook\n\nStage: brainstorming\n", encoding="utf-8")
        report = check_manifest_runbook_parity(workflows_dir)
        assert report["valid"] is False
        assert "implementation" in str(report["errors"])


def test_manifest_runbook_parity_normalizes_stage_names():
    """Stage names with underscores/spaces should normalize to hyphens."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflows_dir = Path(tmpdir)
        manifest = workflows_dir / "feature.manifest.yaml"
        runbook = workflows_dir / "feature.runbook.md"
        manifest.write_text(
            "schema_version: 1\nname: feature\nstages:\n"
            "  - name: writing_plans\n",
            encoding="utf-8",
        )
        # Runbook uses spaces; normalization should make them match.
        runbook.write_text("# Runbook\n\nStage: writing plans\n", encoding="utf-8")
        report = check_manifest_runbook_parity(workflows_dir)
        assert report["valid"] is True


def test_main_cli_dispatches_to_audit_parity(tmp_path, capsys, monkeypatch):
    """main() should dispatch to audit parity when session files exist."""
    from parity_tool import main

    (tmp_path / "session-audit.md").write_text(
        "## Stage: s1\n", encoding="utf-8"
    )
    (tmp_path / "run.jsonl").write_text(
        json.dumps({"stage": "s1"}) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["parity_tool.py", str(tmp_path)])
    rc = main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "valid" in out


def test_main_cli_dispatches_to_manifest_parity(tmp_path, capsys, monkeypatch):
    """main() should dispatch to manifest parity when no session files exist."""
    from parity_tool import main

    monkeypatch.setattr(sys, "argv", ["parity_tool.py", str(tmp_path)])
    rc = main()
    # No manifests -> valid=True -> rc 0
    assert rc == 0


def test_main_cli_no_args_returns_usage_error(capsys, monkeypatch):
    """main() with no args should print usage and return 1."""
    from parity_tool import main

    monkeypatch.setattr(sys, "argv", ["parity_tool.py"])
    rc = main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "Usage" in out


def test_main_cli_invalid_parity_returns_nonzero(tmp_path, capsys, monkeypatch):
    """main() should return 1 when parity check finds mismatches."""
    from parity_tool import main

    (tmp_path / "session-audit.md").write_text(
        "## Stage: only_in_audit\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["parity_tool.py", str(tmp_path)])
    rc = main()
    assert rc == 1

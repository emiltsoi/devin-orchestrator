"""Integration test for the full workflow lifecycle with gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from devin_orchestrator.orchestration_engine import OrchestrationEngine
from devin_orchestrator.skill_invoker import SkillInvocationResult, SkillInvoker
from devin_orchestrator.stage_skill_dispatcher import StageSkillDispatcher

pytestmark = pytest.mark.integration


def _write_manifest(
    workflows_dir: Path, max_gate_request_changes: int | None = None
) -> Path:
    max_line = ""
    if max_gate_request_changes is not None:
        max_line = f"    max_gate_request_changes: {max_gate_request_changes}\n"
    manifest = f"""\
name: integration-gated
version: 1.0.0
schema_version: 1
session_shape: feature
description: Test workflow for integration

stages:
  - step: 0
    name: design
    skill: coder
    description: Design the feature
    required_artifacts: []
    output_artifacts: [design.md]
{max_line}    gate: g1
  - step: 1
    name: implement
    skill: coder
    description: Implement the feature
    required_artifacts: [design.md]
    output_artifacts: [impl.md]
    gate: none

gates:
  - id: g1
    name: Approval
    type: human
    description: Approve the design
"""
    workflows_dir.mkdir(parents=True, exist_ok=True)
    path = workflows_dir / "integration-gated.manifest.yaml"
    path.write_text(manifest, encoding="utf-8")
    return path


def _mock_invoke_skill(manifest_path: Path, outputs: dict[str, Any]):
    """Return a patched invoke_skill method that writes artifacts and reviewer output."""

    def invoke(self, skill_name, context, workspace=None, **kwargs):
        stage = context.get("stage", "unknown")
        session_id = context.get("session_id", "unknown")
        effective_id = f"{skill_name}-{session_id}"

        if skill_name == "swe-compliance" or kwargs.get("is_reviewer"):
            return SkillInvocationResult(
                success=True,
                session_id=effective_id,
                output="verdict: PASS\nconfidence: HIGH",
                error=None,
            )

        ws = Path(workspace or ".")
        expected = outputs.get(stage, [])
        for artifact in expected:
            (ws / artifact).write_text(f"# {stage} output\n", encoding="utf-8")

        return SkillInvocationResult(
            success=True,
            session_id=effective_id,
            output=f"Completed {stage}",
            error=None,
        )

    return invoke


def _make_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    max_gate_request_changes: int | None = None,
) -> OrchestrationEngine:
    workflows_dir = tmp_path / "workflows"
    manifest_path = _write_manifest(workflows_dir, max_gate_request_changes)

    monkeypatch.setattr(
        SkillInvoker,
        "invoke_skill",
        _mock_invoke_skill(
            manifest_path,
            {"design": ["design.md"], "implement": ["impl.md"]},
        ),
    )
    monkeypatch.setattr(StageSkillDispatcher, "load_stage_skill", lambda *a, **k: None)

    engine = OrchestrationEngine(
        work_dir=tmp_path,
        config={
            "workflows_dir": str(workflows_dir),
            "gate_mode": "signal",
            "skills_dir": str(tmp_path / "skills"),
        },
    )
    return engine


def test_workflow_approve_and_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = _make_engine(tmp_path, monkeypatch)
    manifest_path = (
        Path(engine.config["workflows_dir"]) / "integration-gated.manifest.yaml"
    )

    results = engine.execute_workflow(manifest_path, "INT-001", "Build a feature")
    assert results["final_status"] == "waiting_for_input"
    assert len(results["stages"]) == 1

    # Write an approve decision and continue.
    session_dir = tmp_path / "INT-001"
    decision_file = session_dir / "gate-g1-decision.md"
    decision_file.write_text("verdict: approve\nnotes: looks good\n", encoding="utf-8")

    results = engine.continue_workflow("INT-001", gate_verdict="approve")
    assert results["final_status"] == "completed"
    assert len(results["stages"]) == 2

    design = session_dir / "design.md"
    impl = session_dir / "impl.md"
    assert design.is_file()
    assert impl.is_file()


def test_workflow_request_changes_escalates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    engine = _make_engine(tmp_path, monkeypatch, max_gate_request_changes=0)
    manifest_path = (
        Path(engine.config["workflows_dir"]) / "integration-gated.manifest.yaml"
    )

    results = engine.execute_workflow(manifest_path, "INT-002", "Build a feature")
    assert results["final_status"] == "waiting_for_input"

    # Without a revised decision, repeated request_changes exhausts the limit and escalates.
    results = engine.continue_workflow("INT-002", gate_verdict="request_changes")
    assert results["final_status"] == "escalated"


def test_workflow_block_ends_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = _make_engine(tmp_path, monkeypatch)
    manifest_path = (
        Path(engine.config["workflows_dir"]) / "integration-gated.manifest.yaml"
    )

    results = engine.execute_workflow(manifest_path, "INT-003", "Build a feature")
    assert results["final_status"] == "waiting_for_input"

    results = engine.continue_workflow("INT-003", gate_verdict="block")
    assert results["final_status"] == "blocked"

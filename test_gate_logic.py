#!/usr/bin/env python3
"""
Unit-style tests for gate bypass evaluation and gate handling modes.
Does not invoke Devin subagents; runs only local orchestration logic.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
WORKFLOW_ENGINE = REPO / "workflow-engine"
sys.path.insert(0, str(WORKFLOW_ENGINE))

from orchestration_engine import OrchestrationEngine
from deterministic_tools import session_init

SESSION_ID = "GATELOGIC-001"
GATE_ID = "g1_approval_decision"


def make_engine(gate_mode: str = "auto", demo_mode: bool = False) -> OrchestrationEngine:
    work_dir = Path.home() / ".devin-orchestrator" / "work"
    return OrchestrationEngine(
        work_dir=work_dir,
        config={
            "gate_mode": gate_mode,
            "demo_mode": demo_mode,
            "workflows_dir": str(Path.home() / ".devin-orchestrator" / "workflows"),
            "dispatch_timeout_seconds": 60,
        },
    )


def setup_session() -> Path:
    work_dir = Path.home() / ".devin-orchestrator" / "work"
    session_dir = work_dir / SESSION_ID
    if session_dir.exists():
        # Clean up for idempotency
        import shutil

        shutil.rmtree(session_dir)
    session_init(SESSION_ID, work_dir, "test request")
    return session_dir


def write_decision(session_dir: Path, verdict: str, notes: str = "") -> Path:
    path = session_dir / f"gate-{GATE_ID}-decision.md"
    path.write_text(f"verdict: {verdict}\nnotes: {notes}\n", encoding="utf-8")
    return path


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_bypass_conditions(engine: OrchestrationEngine, session_dir: Path) -> None:
    print("\n--- Bypass condition tests ---")

    manifest = {"gates": [{"id": GATE_ID}]}
    gate_file = session_dir / f"gate-{GATE_ID}-decision.md"

    # No triggers -> approve
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "output": "Everything looks good."},
    )
    assert_eq(result["verdict"], "approve", "no triggers")
    print("  no triggers -> approve")

    # demo_mode -> approve
    demo_engine = make_engine(demo_mode=True)
    result = demo_engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "output": ""},
    )
    assert_eq(result["verdict"], "approve", "demo_mode")
    print("  demo_mode -> approve")

    # mandatory gate -> block
    mandatory_manifest = {"gates": [{"id": GATE_ID, "mandatory": True}]}
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, mandatory_manifest,
        {"success": True, "output": ""},
    )
    assert_eq(result["verdict"], "block", "mandatory gate")
    print("  mandatory gate -> block")

    # stage failure -> block
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": False, "output": "failed"},
    )
    assert_eq(result["verdict"], "block", "stage failure")
    print("  stage failure -> block")

    # reviewer rejected -> request_changes
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "reviewer_verdict": "FAIL", "output": ""},
    )
    assert_eq(result["verdict"], "request_changes", "reviewer rejected")
    print("  reviewer rejected -> request_changes")

    # low confidence -> request_changes
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "confidence": "LOW", "output": ""},
    )
    assert_eq(result["verdict"], "request_changes", "low confidence")
    print("  low confidence -> request_changes")

    # critical/security keywords -> block
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "output": "Critical security vulnerability found"},
    )
    assert_eq(result["verdict"], "block", "critical/security keywords")
    print("  critical/security keywords -> block")

    # warnings/medium confidence -> request_changes
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "confidence": "MEDIUM", "output": ""},
    )
    assert_eq(result["verdict"], "request_changes", "medium confidence")
    print("  medium confidence -> request_changes")

    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "output": "Minor warning: naming could be clearer"},
    )
    assert_eq(result["verdict"], "request_changes", "warning keyword")
    print("  warning keyword -> request_changes")

    # missing/empty output -> request_changes
    result = engine._evaluate_gate_bypass_conditions(
        GATE_ID, "compile_findings", session_dir, gate_file, manifest,
        {"success": True, "output": ""},
    )
    assert_eq(result["verdict"], "request_changes", "empty output")
    print("  empty output -> request_changes")


def test_gate_handling_modes(engine: OrchestrationEngine, session_dir: Path) -> None:
    print("\n--- Gate handling mode tests ---")

    manifest = {"gates": [{"id": GATE_ID}]}
    stage_result = {"success": True, "output": "All good"}

    # auto with pre-existing approve
    write_decision(session_dir, "approve", "pre-approved")
    result = engine._handle_gate(GATE_ID, "compile_findings", session_dir, manifest, stage_result)
    assert_eq(result["verdict"], "approve", "auto honors pre-existing approve")
    print("  auto + pre-existing approve -> approve")

    # signal with pre-existing block
    signal_engine = make_engine("signal")
    write_decision(session_dir, "block", "blocking")
    result = signal_engine._handle_gate(GATE_ID, "compile_findings", session_dir, manifest, stage_result)
    assert_eq(result["verdict"], "block", "signal honors pre-existing block")
    assert_eq(result["blocked"], True, "blocked flag")
    print("  signal + pre-existing block -> block")

    # auto with pre-existing request_changes
    write_decision(session_dir, "request_changes", "needs work")
    result = engine._handle_gate(GATE_ID, "compile_findings", session_dir, manifest, stage_result)
    assert_eq(result["verdict"], "request_changes", "auto honors pre-existing request_changes")
    print("  auto + pre-existing request_changes -> request_changes")

    # signal with no decision -> requires input
    no_decision_path = session_dir / f"gate-{GATE_ID}-decision.md"
    if no_decision_path.exists():
        no_decision_path.unlink()
    result = signal_engine._handle_gate(GATE_ID, "compile_findings", session_dir, manifest, stage_result)
    assert_eq(result.get("requires_input"), True, "signal requires_input")
    assert_eq(result["verdict"], "block", "signal default verdict")
    print("  signal + no decision -> requires_input")

    # auto with no decision and no triggers -> auto-approve
    if no_decision_path.exists():
        no_decision_path.unlink()
    result = engine._handle_gate(GATE_ID, "compile_findings", session_dir, manifest, stage_result)
    assert_eq(result["verdict"], "approve", "auto with no triggers -> auto-approve")
    assert_eq(result.get("auto_approved"), True, "auto_approved flag")
    print("  auto + no triggers -> auto-approve")


def main() -> int:
    session_dir = setup_session()
    engine = make_engine("auto")

    test_bypass_conditions(engine, session_dir)
    test_gate_handling_modes(engine, session_dir)

    print("\nAll gate logic tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

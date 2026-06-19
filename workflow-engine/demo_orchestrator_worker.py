#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration of the orchestrator-worker pattern for Stage 1 (brainstorming).

This script demonstrates the full protocol from ORCHESTRATION-RUNBOOK.md:
- Dispatch to stateless Devin worker with focused context
- Validate structural floor
- Dispatch neutral reviewer
- Cascade triage decision
- Record to audit ledger and run.jsonl

This is a demonstration of the contracts, not a full production orchestrator.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Import the deterministic tools
from floor_validator import validate_structural, validate_iron_law, validate_format
from audit_helpers import append_audit, record_gate, write_run_jsonl
from skill_invoker import SkillInvoker
from devin_cli_adapter import DevinCLIAdapter


def demo_stage_1_brainstorming(harness_root, session_id, request_content):
    """
    Demonstrate Stage 1 (brainstorming) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")
        request_content: Content for request.md

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_1",
        "skill": "brainstorming",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 1 configuration from feature.runbook.md
    skill_name = "brainstorming"
    required_artifacts = ["requirement.md"]
    gate_id = "g1_requirement_approval"
    injected_context = ["request.md"]

    # Session directory
    session_dir = harness_root / "work" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    summary["steps_executed"].append("session_dir_created")

    # Step 1: Create request.md (simulating session_init)
    request_path = session_dir / "request.md"
    request_path.write_text(request_content, encoding="utf-8")
    summary["steps_executed"].append("request.md_created")

    # Step 2: Dispatch to stateless Devin worker (simulated)
    # In production, this would call skill_invoker.invoke_skill with focused_context
    # For demo, we'll create a placeholder requirement.md
    requirement_path = session_dir / "requirement.md"
    requirement_content = "# Requirement for " + session_id + "\n\n## Overview\nThis is a demonstration requirement.md produced by the brainstorming skill.\n\n## Acceptance Criteria\n- [ ] Criterion 1\n- [ ] Criterion 2\n\n## Notes\nThis is a placeholder for demonstration purposes.\n"
    requirement_path.write_text(requirement_content, encoding="utf-8")
    summary["steps_executed"].append("worker_dispatch_completed")

    # Step 3: Validate structural floor (deterministic tool)
    structural_result = validate_structural([requirement_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 4: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_1-1.md"
    review_content = "# Review of requirement.md\n\n## Verdict: PASS\n\n## Assessment\nThe requirement.md artifact is complete and addresses the user's request.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 5: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Requirement.md is complete, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 6: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_1",
        skill=skill_name,
        injected_context=injected_context,
        structural_result=structural_result["result"],
        reviewer_verdict="PASS",
        confidence=confidence,
        rationale=rationale,
        triage_decision=triage_decision,
        retry_count=0,
        gate_verdict="none"
    )
    summary["steps_executed"].append("audit_recorded")

    # Step 7: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_1",
        "skill": skill_name,
        "injected_context": injected_context,
        "structural_result": structural_result["result"],
        "reviewer_verdict": "PASS",
        "confidence": confidence,
        "rationale": rationale,
        "triage_decision": triage_decision,
        "retry_count": 0,
        "gate_verdict": "none"
    }
    write_run_jsonl(session_dir, run_jsonl_entry)
    summary["steps_executed"].append("run_jsonl_recorded")

    # Step 8: Gate protocol (simulated - would be hard stop in production)
    # For demo, we'll record an approved gate
    record_gate(session_dir, gate_id, "approved")
    summary["steps_executed"].append("gate_recorded")
    summary["gate_verdict"] = "approved"

    summary["final_state"] = "COMPLETE"
    return summary


def demo_resumability(session_dir):
    """
    Demonstrate resumability by reconstructing state from run.jsonl + artifacts.

    Args:
        session_dir: Session directory containing run.jsonl and artifacts

    Returns:
        Reconstructed state summary
    """
    run_jsonl_path = session_dir / "run.jsonl"

    if not run_jsonl_path.exists():
        return {"error": "run.jsonl not found"}

    # Read run.jsonl
    with open(run_jsonl_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        return {"error": "run.jsonl is empty"}

    # Parse last entry
    last_entry = json.loads(lines[-1])

    reconstructed_state = {
        "last_stage": last_entry["stage"],
        "last_skill": last_entry["skill"],
        "last_confidence": last_entry["confidence"],
        "last_triage_decision": last_entry["triage_decision"],
        "last_gate_verdict": last_entry["gate_verdict"],
        "retry_count": last_entry["retry_count"],
        "artifacts_present": [],
        "correction_artifacts": [],
        "review_artifacts": []
    }

    # Check for artifacts
    for artifact_path in session_dir.glob("*.md"):
        artifact_name = artifact_path.name
        reconstructed_state["artifacts_present"].append(artifact_name)

        if artifact_name.startswith("correction-"):
            reconstructed_state["correction_artifacts"].append(artifact_name)
        elif artifact_name.startswith("review-"):
            reconstructed_state["review_artifacts"].append(artifact_name)

    # Check for gate decision artifacts
    for gate_path in session_dir.glob("gate-*.md"):
        reconstructed_state["artifacts_present"].append(gate_path.name)

    return reconstructed_state


def main():
    """Run the demonstration."""
    harness_root = Path(__file__).parent.parent
    session_id = "DEMO-001"
    request_content = """# Request for DEMO-001

## Description
Demonstration of the orchestrator–worker pattern.

## Requirements
Implement a feature that demonstrates the new orchestration contracts.
"""

    print("=" * 60)
    print("Demonstration: Orchestrator-Worker Pattern (Stage 1)")
    print("=" * 60)
    print()

    # Run Stage 1 demonstration
    print("Running Stage 1 (brainstorming) demonstration...")
    summary = demo_stage_1_brainstorming(harness_root, session_id, request_content)
    print()

    print("Summary:")
    print(json.dumps(summary, indent=2))
    print()

    # Demonstrate resumability
    print("Demonstrating resumability...")
    session_dir = harness_root / "work" / session_id
    reconstructed_state = demo_resumability(session_dir)
    print()

    print("Reconstructed State:")
    print(json.dumps(reconstructed_state, indent=2))
    print()

    print("=" * 60)
    print("Demonstration Complete")
    print("=" * 60)
    print()
    print("Artifacts created:")
    session_dir = harness_root / "work" / session_id
    for artifact in sorted(session_dir.glob("*")):
        print("  - " + artifact.name)


if __name__ == "__main__":
    main()

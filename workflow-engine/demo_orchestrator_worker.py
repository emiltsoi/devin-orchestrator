#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration of the orchestrator-worker pattern for all 8 stages of the feature workflow.

This script demonstrates the full protocol from feature.runbook.md:
- Stage 0: session_init (scaffolding)
- Stage 1: brainstorming (requirement.md)
- Stage 2: test-driven-development (baseline.md)
- Stage 3: writing-plans (design.md, g2 gate)
- Stage 4: subagent-driven-development (implementation.md)
- Stage 5: verification-before-completion (verification.md)
- Stage 6: code-review (review-spec.md, review-quality.md, human-verdict.md)
- Stage 7: final summary (summary.md, metrics.json, retro.md, g3 gate)

Each stage demonstrates:
- Dispatch to stateless Devin worker with focused context
- Validate structural floor
- Dispatch neutral reviewer
- Cascade triage decision
- Record to audit ledger and run.jsonl
- Gate protocol for gated stages (g1, g2, g3)

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
from devin_cli_adapter import DevinCliAdapter


def demo_stage_0_session_init(harness_root, session_id, request_content):
    """
    Demonstrate Stage 0 (session_init) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")
        request_content: Content for request.md

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_0",
        "skill": "none",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 0 configuration from feature.runbook.md
    skill_name = "none"
    required_artifacts = ["request.md", "status.md", "session-audit.md"]
    gate_id = "none"
    injected_context = []

    # Session directory
    session_dir = harness_root / "work" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    summary["steps_executed"].append("session_dir_created")

    # Step 1: Create request.md (session_init deterministic tool)
    request_path = session_dir / "request.md"
    request_path.write_text(request_content, encoding="utf-8")
    summary["steps_executed"].append("request.md_created")

    # Step 2: Create status.md (session_init deterministic tool)
    status_path = session_dir / "status.md"
    status_content = "# Status for " + session_id + "\n\n## Current Stage\nstep_0\n\n## Status\nInitialized\n\n## Timestamp\n" + datetime.utcnow().isoformat() + "Z\n"
    status_path.write_text(status_content, encoding="utf-8")
    summary["steps_executed"].append("status.md_created")

    # Step 3: Create session-audit.md (session_init deterministic tool)
    audit_path = session_dir / "session-audit.md"
    audit_content = "# Session Audit: " + session_id + "\n\n## Session Initialization\n- Session ID: " + session_id + "\n- Timestamp: " + datetime.utcnow().isoformat() + "Z\n- Stage: step_0\n\n## Audit Entries\n\n"
    audit_path.write_text(audit_content, encoding="utf-8")
    summary["steps_executed"].append("session-audit.md_created")

    # Step 4: No worker dispatch for stage 0 (scaffolding only)
    summary["steps_executed"].append("no_worker_dispatch")

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_0",
        skill=skill_name,
        injected_context=injected_context,
        structural_result="N/A",
        reviewer_verdict="N/A",
        confidence="N/A",
        rationale="Session initialization - scaffolding only",
        triage_decision="proceed",
        retry_count=0,
        gate_verdict="none"
    )
    summary["steps_executed"].append("audit_recorded")

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_0",
        "skill": skill_name,
        "injected_context": injected_context,
        "structural_result": "N/A",
        "reviewer_verdict": "N/A",
        "confidence": "N/A",
        "rationale": "Session initialization - scaffolding only",
        "triage_decision": "proceed",
        "retry_count": 0,
        "gate_verdict": "none"
    }
    write_run_jsonl(session_dir, run_jsonl_entry)
    summary["steps_executed"].append("run_jsonl_recorded")

    summary["final_state"] = "COMPLETE"
    return summary


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
    requirement_content = "# Requirement for " + session_id + "\n\n## Overview\nThis is a demonstration requirement.md produced by the brainstorming skill.\n\n## Acceptance Criteria\n- [ ] Criterion 1\n- [ ] Criterion 2\n\n## Notes\nThis is a sample for demonstration purposes.\n"
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


def demo_stage_2_test_driven_development(harness_root, session_id):
    """
    Demonstrate Stage 2 (test-driven-development) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_2",
        "skill": "test-driven-development",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 2 configuration from feature.runbook.md
    skill_name = "test-driven-development"
    required_artifacts = ["baseline.md"]
    gate_id = "none"
    injected_context = ["requirement.md"]

    # Session directory
    session_dir = harness_root / "work" / session_id

    summary["steps_executed"].append("session_dir_verified")

    # Step 1: Dispatch to stateless Devin worker (simulated)
    # In production, this would call skill_invoker.invoke_skill with focused_context
    # For demo, we'll create a placeholder baseline.md
    baseline_path = session_dir / "baseline.md"
    baseline_content = "# Baseline Tests for " + session_id + "\n\n## Test Suite\nThis is a demonstration baseline.md produced by the test-driven-development skill.\n\n## Red Tests\n- [ ] Test 1: Requirement criterion 1\n- [ ] Test 2: Requirement criterion 2\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    baseline_path.write_text(baseline_content, encoding="utf-8")
    summary["steps_executed"].append("worker_dispatch_completed")

    # Step 2: Validate structural floor (deterministic tool)
    structural_result = validate_structural([baseline_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 3: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_2-1.md"
    review_content = "# Review of baseline.md\n\n## Verdict: PASS\n\n## Assessment\nThe baseline.md artifact is complete and captures the requirement acceptance criteria.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 4: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Baseline.md is complete, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_2",
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

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_2",
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

    # No gate for this stage
    summary["final_state"] = "COMPLETE"
    return summary


def demo_stage_3_writing_plans(harness_root, session_id):
    """
    Demonstrate Stage 3 (writing-plans) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_3",
        "skill": "writing-plans",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 3 configuration from feature.runbook.md
    skill_name = "writing-plans"
    required_artifacts = ["design.md"]
    gate_id = "g2_design_approval"
    injected_context = ["requirement.md", "baseline.md"]

    # Session directory
    session_dir = harness_root / "work" / session_id

    summary["steps_executed"].append("session_dir_verified")

    # Step 1: Dispatch to stateless Devin worker (simulated)
    # In production, this would call skill_invoker.invoke_skill with focused_context
    # For demo, we'll create a placeholder design.md
    design_path = session_dir / "design.md"
    design_content = "# Design for " + session_id + "\n\n## Overview\nThis is a demonstration design.md produced by the writing-plans skill.\n\n## Architecture\n- Component 1\n- Component 2\n\n## Implementation Plan\n1. Step 1\n2. Step 2\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    design_path.write_text(design_content, encoding="utf-8")
    summary["steps_executed"].append("worker_dispatch_completed")

    # Step 2: Validate structural floor (deterministic tool)
    structural_result = validate_structural([design_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 3: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_3-1.md"
    review_content = "# Review of design.md\n\n## Verdict: PASS\n\n## Assessment\nThe design.md artifact is complete and addresses the requirement. It is coherent with the baseline tests.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 4: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Design.md is complete, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_3",
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

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_3",
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

    # Step 7: Gate protocol (simulated - would be hard stop in production)
    # For demo, we'll record an approved gate
    record_gate(session_dir, gate_id, "approved")
    summary["steps_executed"].append("gate_recorded")
    summary["gate_verdict"] = "approved"

    summary["final_state"] = "COMPLETE"
    return summary


def demo_stage_4_subagent_driven_development(harness_root, session_id):
    """
    Demonstrate Stage 4 (subagent-driven-development) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_4",
        "skill": "subagent-driven-development",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 4 configuration from feature.runbook.md
    skill_name = "subagent-driven-development"
    required_artifacts = ["implementation.md"]
    gate_id = "none"
    injected_context = ["design.md"]

    # Session directory
    session_dir = harness_root / "work" / session_id

    summary["steps_executed"].append("session_dir_verified")

    # Step 1: Dispatch to stateless Devin worker (simulated)
    # In production, this would call skill_invoker.invoke_skill with focused_context
    # For demo, we'll create a placeholder implementation.md
    implementation_path = session_dir / "implementation.md"
    implementation_content = "# Implementation for " + session_id + "\n\n## Overview\nThis is a demonstration implementation.md produced by the subagent-driven-development skill.\n\n## Code Changes\n- File 1: Added function X\n- File 2: Modified class Y\n\n## Implementation Notes\nThis is a sample for demonstration purposes.\n"
    implementation_path.write_text(implementation_content, encoding="utf-8")
    summary["steps_executed"].append("worker_dispatch_completed")

    # Step 2: Validate structural floor (deterministic tool)
    structural_result = validate_structural([implementation_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 3: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_4-1.md"
    review_content = "# Review of implementation.md\n\n## Verdict: PASS\n\n## Assessment\nThe implementation.md follows the design and is complete and correct.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 4: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Implementation.md follows the design, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_4",
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

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_4",
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

    # No gate for this stage
    summary["final_state"] = "COMPLETE"
    return summary


def demo_stage_5_verification_before_completion(harness_root, session_id):
    """
    Demonstrate Stage 5 (verification-before-completion) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_5",
        "skill": "verification-before-completion",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 5 configuration from feature.runbook.md
    skill_name = "verification-before-completion"
    required_artifacts = ["verification.md"]
    gate_id = "none"
    injected_context = ["design.md", "implementation.md"]

    # Session directory
    session_dir = harness_root / "work" / session_id

    summary["steps_executed"].append("session_dir_verified")

    # Step 1: Dispatch to stateless Devin worker (simulated)
    # In production, this would call skill_invoker.invoke_skill with focused_context
    # For demo, we'll create a placeholder verification.md
    verification_path = session_dir / "verification.md"
    verification_content = "# Verification for " + session_id + "\n\n## Build Status\nPASS\n\n## Test Results\nAll tests passing.\n\n## Acceptance Criteria\n- [ ] Criterion 1: Met\n- [ ] Criterion 2: Met\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    verification_path.write_text(verification_content, encoding="utf-8")
    summary["steps_executed"].append("worker_dispatch_completed")

    # Step 2: Validate structural floor (deterministic tool)
    structural_result = validate_structural([verification_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 3: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_5-1.md"
    review_content = "# Review of verification.md\n\n## Verdict: PASS\n\n## Assessment\nThe verification.md confirms build+tests pass and all acceptance criteria are met.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 4: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Verification.md confirms build+tests pass, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_5",
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

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_5",
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

    # No gate for this stage
    summary["final_state"] = "COMPLETE"
    return summary


def demo_stage_6_code_review(harness_root, session_id):
    """
    Demonstrate Stage 6 (code-review) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_6",
        "skill": "code-review",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 6 configuration from feature.runbook.md
    skill_name = "code-review"
    required_artifacts = ["review-spec.md", "review-quality.md", "human-verdict.md"]
    gate_id = "none"
    injected_context = ["requirement.md", "design.md", "diff"]

    # Session directory
    session_dir = harness_root / "work" / session_id

    summary["steps_executed"].append("session_dir_verified")

    # Step 1: Dispatch to stateless Devin worker (simulated)
    # In production, this would call skill_invoker.invoke_skill with focused_context
    # For demo, we'll create placeholder artifacts
    review_spec_path = session_dir / "review-spec.md"
    review_spec_content = "# Review Spec for " + session_id + "\n\n## Spec Compliance\nThe implementation follows the design specification.\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    review_spec_path.write_text(review_spec_content, encoding="utf-8")

    review_quality_path = session_dir / "review-quality.md"
    review_quality_content = "# Review Quality for " + session_id + "\n\n## Code Quality\nThe code follows best practices and is well-structured.\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    review_quality_path.write_text(review_quality_content, encoding="utf-8")

    human_verdict_path = session_dir / "human-verdict.md"
    human_verdict_content = "# Human Verdict for " + session_id + "\n\n## Verdict\nAPPROVED\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    human_verdict_path.write_text(human_verdict_content, encoding="utf-8")

    summary["steps_executed"].append("worker_dispatch_completed")

    # Step 2: Validate structural floor (deterministic tool)
    structural_result = validate_structural([review_spec_path, review_quality_path, human_verdict_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 3: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_6-1.md"
    review_content = "# Review of code-review artifacts\n\n## Verdict: PASS\n\n## Assessment\nThe reviews capture spec compliance and code quality. The human verdict is documented.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 4: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Reviews capture spec compliance and code quality, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_6",
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

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_6",
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

    # No gate for this stage
    summary["final_state"] = "COMPLETE"
    return summary


def demo_stage_7_final_summary(harness_root, session_id):
    """
    Demonstrate Stage 7 (final summary) following the orchestrator–worker pattern.

    Args:
        harness_root: Root directory of the harness
        session_id: Session identifier (e.g., "FEATURE-001")

    Returns:
        Summary of the demonstration execution
    """
    summary = {
        "session_id": session_id,
        "stage": "step_7",
        "skill": "none",
        "steps_executed": [],
        "final_state": "unknown"
    }

    # Stage 7 configuration from feature.runbook.md
    skill_name = "none"
    required_artifacts = ["summary.md", "metrics.json", "retro.md"]
    gate_id = "g3_final_approval"
    injected_context = []

    # Session directory
    session_dir = harness_root / "work" / session_id

    summary["steps_executed"].append("session_dir_verified")

    # Step 1: Cascade synthesizes final artifacts directly (no worker dispatch)
    # For demo, we'll create placeholder artifacts
    summary_path = session_dir / "summary.md"
    summary_content = "# Summary for " + session_id + "\n\n## Overview\nThis is a demonstration summary.md synthesized by Cascade.\n\n## Workflow Completion\nAll stages completed successfully.\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    summary_path.write_text(summary_content, encoding="utf-8")

    metrics_path = session_dir / "metrics.json"
    metrics_content = json.dumps({
        "session_id": session_id,
        "total_stages": 8,
        "stages_completed": 8,
        "total_attempts": 8,
        "total_time_seconds": 0,
        "gates_approved": 3,
        "confidence_history": ["HIGH", "HIGH", "HIGH", "HIGH", "HIGH", "HIGH", "HIGH"]
    }, indent=2)
    metrics_path.write_text(metrics_content, encoding="utf-8")

    retro_path = session_dir / "retro.md"
    retro_content = "# Retrospective for " + session_id + "\n\n## What Went Well\n- All stages completed on first attempt\n- High confidence throughout\n\n## What Could Be Improved\n- Add more detailed metrics\n- Improve artifact quality\n\n## Notes\nThis is a sample for demonstration purposes.\n"
    retro_path.write_text(retro_content, encoding="utf-8")

    summary["steps_executed"].append("cascade_synthesis_completed")

    # Step 2: Validate structural floor (deterministic tool)
    structural_result = validate_structural([summary_path, metrics_path, retro_path])
    summary["steps_executed"].append("structural_validation")
    summary["structural_result"] = structural_result

    if structural_result["result"] == "FAIL":
        summary["final_state"] = "CORRECTION_LOOP"
        return summary

    # Step 3: Dispatch neutral reviewer (simulated)
    # In production, this would be a separate devin-cli dispatch
    # For demo, we'll create a placeholder review artifact
    review_path = session_dir / "review-step_7-1.md"
    review_content = "# Review of final artifacts\n\n## Verdict: PASS\n\n## Assessment\nThe final artifacts are complete and accurate.\n\n## Confidence: HIGH\n"
    review_path.write_text(review_content, encoding="utf-8")
    summary["steps_executed"].append("neutral_reviewer_dispatch")
    summary["reviewer_verdict"] = "PASS"

    # Step 4: Cascade triage decision (simulated)
    # In production, Cascade would reason about the reviewer verdict + floor result
    confidence = "HIGH"
    rationale = "Final artifacts are complete and accurate, structural floor passes, reviewer passes."
    triage_decision = "proceed"
    summary["steps_executed"].append("cascade_triage")
    summary["confidence"] = confidence
    summary["rationale"] = rationale
    summary["triage_decision"] = triage_decision

    # Step 5: Record to audit ledger (deterministic tool)
    append_audit(
        session_dir=session_dir,
        stage="step_7",
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

    # Step 6: Write run.jsonl entry (deterministic tool)
    run_jsonl_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "stage": "step_7",
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

    # Step 7: Gate protocol (simulated - would be hard stop in production)
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
    print("Demonstration: Orchestrator-Worker Pattern (All 8 Stages)")
    print("=" * 60)
    print()

    # Run Stage 0 demonstration
    print("Running Stage 0 (session_init) demonstration...")
    summary_0 = demo_stage_0_session_init(harness_root, session_id, request_content)
    print()
    print("Stage 0 Summary:")
    print(json.dumps(summary_0, indent=2))
    print()

    # Run Stage 1 demonstration
    print("Running Stage 1 (brainstorming) demonstration...")
    summary_1 = demo_stage_1_brainstorming(harness_root, session_id, request_content)
    print()
    print("Stage 1 Summary:")
    print(json.dumps(summary_1, indent=2))
    print()

    # Run Stage 2 demonstration
    print("Running Stage 2 (test-driven-development) demonstration...")
    summary_2 = demo_stage_2_test_driven_development(harness_root, session_id)
    print()
    print("Stage 2 Summary:")
    print(json.dumps(summary_2, indent=2))
    print()

    # Run Stage 3 demonstration
    print("Running Stage 3 (writing-plans) demonstration...")
    summary_3 = demo_stage_3_writing_plans(harness_root, session_id)
    print()
    print("Stage 3 Summary:")
    print(json.dumps(summary_3, indent=2))
    print()

    # Run Stage 4 demonstration
    print("Running Stage 4 (subagent-driven-development) demonstration...")
    summary_4 = demo_stage_4_subagent_driven_development(harness_root, session_id)
    print()
    print("Stage 4 Summary:")
    print(json.dumps(summary_4, indent=2))
    print()

    # Run Stage 5 demonstration
    print("Running Stage 5 (verification-before-completion) demonstration...")
    summary_5 = demo_stage_5_verification_before_completion(harness_root, session_id)
    print()
    print("Stage 5 Summary:")
    print(json.dumps(summary_5, indent=2))
    print()

    # Run Stage 6 demonstration
    print("Running Stage 6 (code-review) demonstration...")
    summary_6 = demo_stage_6_code_review(harness_root, session_id)
    print()
    print("Stage 6 Summary:")
    print(json.dumps(summary_6, indent=2))
    print()

    # Run Stage 7 demonstration
    print("Running Stage 7 (final summary) demonstration...")
    summary_7 = demo_stage_7_final_summary(harness_root, session_id)
    print()
    print("Stage 7 Summary:")
    print(json.dumps(summary_7, indent=2))
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

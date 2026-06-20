#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration of the orchestrator-worker pattern for the superpower workflow.

This script demonstrates the full protocol from superpower.runbook.md using the orchestrator_executor.
The orchestrator (Cascade) drives the workflow by:
- Loading the manifest
- Executing stages with skill_invoker
- Reasoning through results
- Handling gates with triage decisions

This is a demonstration of the contracts, not a full production orchestrator.
"""

from pathlib import Path
from orchestrator_executor import OrchestratorExecutor


def demo_superpower_workflow(session_id, request_content):
    """
    Demonstrate the superpower workflow using orchestrator_executor.

    Args:
        session_id: Session identifier (e.g., "SUPERPOWER-001")
        request_content: Content for request.md

    Returns:
        Summary of the workflow execution
    """
    executor = OrchestratorExecutor()
    
    result = executor.execute_workflow(
        session_id=session_id,
        request_content=request_content
    )
    
    return result


if __name__ == "__main__":
    # Test the superpower workflow
    session_id = "SUPERPOWER-TEST-001"
    request_content = "# Request\n\nImplement a caching layer for skill loading."
    
    result = demo_superpower_workflow(session_id, request_content)
    
    print("=== Superpower Workflow Demo ===")
    print("Success:", result.get("success"))
    if not result.get("success"):
        print("Error:", result.get("error"))
    print("Stages executed:", len(result.get("results", [])))
    
    for stage_result in result.get("results", []):
        print(f"\nStage: {stage_result.stage_name}")
        print(f"  Skill: {stage_result.skill}")
        print(f"  Success: {stage_result.success}")
        print(f"  Structural: {stage_result.structural_result}")
        print(f"  Triage: {stage_result.triage_decision}")
        if stage_result.gate_verdict:
            print(f"  Gate: {stage_result.gate_verdict}")

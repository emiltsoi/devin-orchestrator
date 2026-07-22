#!/usr/bin/env python3
"""
Test MCP gate_decision and continue_workflow tools directly.
Uses the existing CODEREVIEW-009 session so no subagent dispatches are needed.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "workflow-engine"))

from mcp_server import McpServer

SESSION_ID = "CODEREVIEW-009"
GATE_ID = "g1_approval_decision"


def print_header(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def parse_engine(resp: list[dict]) -> dict:
    """Return the engine result nested inside the StatelessOrchestrator output."""
    wrapper = json.loads(resp[0]["text"])
    return json.loads(wrapper["output"])


def main() -> int:
    server = McpServer(workspace=str(REPO))
    decision_path = (
        Path.home()
        / ".devin-orchestrator"
        / "work"
        / SESSION_ID
        / f"gate-{GATE_ID}-decision.md"
    )

    # Test 1: gate_decision writes a request_changes verdict
    print_header("Test 1: _tool_gate_decision (request_changes)")
    resp = server._tool_gate_decision(
        {
            "session_id": SESSION_ID,
            "gate_id": GATE_ID,
            "verdict": "request_changes",
            "notes": "MCP gate_decision test",
        }
    )
    print("Response:", resp[0]["text"])
    print("Decision file content:")
    print(decision_path.read_text(encoding="utf-8"))

    # Test 2: continue_workflow with block verdict
    print_header("Test 2: _tool_continue_workflow (block)")
    resp = server._tool_continue_workflow(
        {
            "session_id": SESSION_ID,
            "gate_verdict": "block",
            "gate_id": GATE_ID,
            "gate_mode": "auto",
        }
    )
    engine = parse_engine(resp)
    print("engine final_status:", engine.get("final_status"))
    print("wrapper success:", json.loads(resp[0]["text"]).get("success"))
    print("Decision file content:")
    print(decision_path.read_text(encoding="utf-8"))
    if engine.get("final_status") != "blocked":
        print("FAIL: expected final_status 'blocked'")
        return 1

    # Test 3: gate_decision writes approve and continue_workflow completes
    print_header("Test 3: _tool_gate_decision + _tool_continue_workflow (approve)")
    resp = server._tool_gate_decision(
        {
            "session_id": SESSION_ID,
            "gate_id": GATE_ID,
            "verdict": "approve",
            "notes": "MCP continue_workflow test",
        }
    )
    print("Response:", resp[0]["text"])

    resp = server._tool_continue_workflow(
        {
            "session_id": SESSION_ID,
            "gate_verdict": "approve",
            "gate_id": GATE_ID,
            "gate_mode": "auto",
        }
    )
    engine = parse_engine(resp)
    print("engine final_status:", engine.get("final_status"))
    print("wrapper success:", json.loads(resp[0]["text"]).get("success"))
    if engine.get("final_status") != "completed":
        print("FAIL: expected final_status 'completed'")
        return 1

    for stage in engine.get("stages", []):
        print(
            f"  - {stage['stage']}: {stage.get('triage_decision')}"
            f" ({'resumed' if 'resumed' in stage.get('output', '') else 'executed'})"
        )

    print("\nAll MCP gate tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

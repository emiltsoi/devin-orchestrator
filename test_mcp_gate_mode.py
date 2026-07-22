#!/usr/bin/env python3
"""
Verify that MCP workflow/review tools forward the `gate_mode` parameter to
StatelessOrchestrator. Uses a spy class to avoid real Devin dispatches.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
WORKFLOW_ENGINE = REPO / "workflow-engine"
sys.path.insert(0, str(WORKFLOW_ENGINE))

import stateless_orchestrator as so_mod


class SpyOrchestrator:
    """Records the constructor kwargs and gate_mode for each call."""

    calls: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        SpyOrchestrator.calls.append(kwargs)

    def review(self, request: str):
        return self._canned("review")

    def implement(self, request: str):
        return self._canned("implement")

    def investigate(self, request: str):
        return self._canned("investigate")

    def plan(self, request: str):
        return self._canned("plan")

    def run_workflow(self, workflow_name: str, request: str):
        return self._canned("run_workflow", workflow_name=workflow_name)

    def run_skill(self, skill: str, request: str):
        return self._canned("run_skill", skill=skill)

    def continue_workflow(self, **kwargs):
        return self._canned("continue_workflow")

    def _canned(self, method: str, **extra):
        return {
            "session_id": "SPY-001",
            "workspace": str(REPO),
            "success": True,
            "output": json.dumps(
                {"method": method, "kwargs": self.kwargs, "extra": extra},
                default=str,
            ),
            "error": None,
        }


so_mod.StatelessOrchestrator = SpyOrchestrator

# Import after monkey-patching the module attribute
from mcp_server import McpServer


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def last_call() -> dict:
    return SpyOrchestrator.calls[-1]


def main() -> int:
    server = McpServer(workspace=str(REPO))
    SpyOrchestrator.calls.clear()

    print("\n--- MCP gate_mode forwarding tests ---")

    server._tool_review(
        {"request": "test review", "gate_mode": "signal", "timeout": 30}
    )
    assert_eq(last_call().get("gate_mode"), "signal", "_tool_review gate_mode")
    print("  _tool_review forwards gate_mode=signal")

    server._tool_implement(
        {"request": "test implement", "gate_mode": "interactive", "timeout": 30}
    )
    assert_eq(last_call().get("gate_mode"), "interactive", "_tool_implement gate_mode")
    print("  _tool_implement forwards gate_mode=interactive")

    server._tool_investigate(
        {"request": "test investigate", "gate_mode": "auto", "timeout": 30}
    )
    assert_eq(last_call().get("gate_mode"), "auto", "_tool_investigate gate_mode")
    print("  _tool_investigate forwards gate_mode=auto")

    server._tool_run_workflow(
        {
            "workflow": "code_review",
            "request": "test workflow",
            "gate_mode": "signal",
            "timeout": 30,
        }
    )
    assert_eq(last_call().get("gate_mode"), "signal", "_tool_run_workflow gate_mode")
    print("  _tool_run_workflow forwards gate_mode=signal")

    server._tool_continue_workflow(
        {
            "session_id": "CODEREVIEW-009",
            "gate_verdict": "approve",
            "gate_mode": "interactive",
        }
    )
    assert_eq(
        last_call().get("gate_mode"), "interactive", "_tool_continue_workflow gate_mode"
    )
    print("  _tool_continue_workflow forwards gate_mode=interactive")

    # Default when omitted
    server._tool_review({"request": "test default"})
    assert_eq(last_call().get("gate_mode"), "auto", "default gate_mode is auto")
    print("  default gate_mode is auto")

    print("\nAll MCP gate_mode forwarding tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

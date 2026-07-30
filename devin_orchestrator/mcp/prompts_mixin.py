# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class McpPromptsMixin:

    def _prompts_list(self, request: dict) -> dict:
        """Return the list of available MCP prompts."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "prompts": [
                    {
                        "name": "devin-orchestrator-usage",
                        "description": "Usage guide for the devin-orchestrator MCP server.",
                    }
                ]
            },
        }

    def _prompts_get(self, request: dict) -> dict:
        """Return the devin-orchestrator usage prompt content."""
        params = request.get("params", {})
        prompt_name = params.get("name")
        if prompt_name != "devin-orchestrator-usage":
            return self._error(request, -32602, f"Unknown prompt: {prompt_name}")

        usage_text = """# Devin Orchestrator MCP Usage

Pick the highest-level tool that matches your task. All workflow and skill tools now start in the background and return a session_id; use query_workflow_status to poll.

1. execute — main entry point; auto-routes by intent.
2. implement — full superpower workflow for feature/bug-fix implementation.
3. review — code_review workflow for code or PR review.
4. investigate — rca workflow for root-cause analysis (read-only).
5. plan — writing-plans skill to produce an implementation plan.
6. run_workflow — run a specific named workflow.
7. run_skill — process skills only (brainstorming, writing-plans, systematic-debugging).
8. gate_decision — write a verdict for a waiting gate.
9. continue_workflow — resume a workflow after a gate decision.
10. query_workflow_status — poll status and result for any session_id.
11. list_sessions — list sessions with status, type, and last update.
12. cancel_session — request cancellation of a running session.
13. dispatch_devin — focused single-shot worker with prompt_file, focused_context, model, output_file.

Do NOT use run_skill for implementation tasks. It has no focused_context and bypasses the workflow gates. For coding work, use implement, run_workflow, or dispatch_devin.
"""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": usage_text},
                    }
                ]
            },
        }

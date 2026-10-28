from __future__ import annotations

from devin_orchestrator.mcp._base import McpServerBase


class McpServerToolsMixin(McpServerBase):
    """Mixin providing the list of MCP tool definitions."""

    # Tool definitions (exposed via tools/list)
    # --------------------------------------------------------------------- #
    @staticmethod
    def _tool_specs() -> list[dict]:
        return [
            {
                "name": "list_skills",
                "description": "List all available devin-orchestrator skills.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_skill",
                "description": "Get the YAML definition and markdown narrative for a skill.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill name (must match a directory under skills/)",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "list_workflows",
                "description": "List all available workflow manifests.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_workflow",
                "description": "Get a workflow manifest and its runbook.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Workflow name (e.g. code_review, pr_review, rca)",
                        }
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "dispatch_devin",
                "description": "MCP tool: dispatch a focused, single-shot Devin worker. Best for targeted implementation fixes or reviews where you specify exact acceptance criteria, focused files, and an output file. For full feature development prefer `implement` or `run_workflow`; for process skills prefer `run_skill`. Do not run `dispatch_devin.py` directly; use this tool.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "description": "Role name (coder, reviewer, etc.) or path to role markdown",
                        },
                        "prompt_file": {
                            "type": "string",
                            "description": "Absolute or workspace-relative path to the prompt markdown file",
                        },
                        "work_dir": {
                            "type": "string",
                            "description": "Workspace directory where Devin runs and writes outputs",
                        },
                        "model": {
                            "type": "string",
                            "description": "Model to use for the worker (e.g. swe-1.6). Overrides default routing.",
                        },
                        "agent": {
                            "type": "string",
                            "description": "Optional agent identifier or override.",
                        },
                        "phase": {
                            "type": "string",
                            "description": "Optional workflow phase context.",
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path where the worker writes a structured execution report.",
                        },
                        "focused_context": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Paths to include as focused context",
                        },
                        "permission_mode": {
                            "type": "string",
                            "description": "Devin permission mode (e.g. dangerous); defaults to config",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds",
                            "default": 600,
                        },
                    },
                    "required": ["role", "prompt_file", "work_dir"],
                },
            },
            {
                "name": "dispatch_skill",
                "description": "MCP tool: invoke a named skill as a Devin worker in a target workspace. This dispatches a fresh subagent to follow the skill; prefer `execute`, `implement`, or `dispatch_devin` for most tasks. Do not run `dispatch_skill.py` directly; use this tool.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "session_id": {"type": "string"},
                        "workspace": {"type": "string"},
                        "is_reviewer": {"type": "boolean", "default": False},
                        "demo_mode": {"type": "boolean", "default": False},
                        "config_overrides": {"type": "object", "default": {}},
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds",
                            "default": 600,
                        },
                    },
                    "required": ["skill_name", "session_id", "workspace"],
                },
            },
            {
                "name": "read_artifact",
                "description": "Read a file from a workspace or session directory. Text files support optional line offset/limit and are truncated to a max size. Binary files are returned as base64 (images as MCP image content).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "offset": {
                            "type": "integer",
                            "description": "1-based starting line for text files",
                            "default": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of lines to return for text files",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "list_directory",
                "description": "List files and directories under a validated workspace or session path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "recursive": {"type": "boolean", "default": False},
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum directory depth when recursive",
                            "default": 3,
                        },
                    },
                },
            },
            {
                "name": "list_artifacts",
                "description": "List files recursively in a session directory or workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "recursive": {"type": "boolean", "default": True},
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum directory depth when recursive",
                            "default": 10,
                        },
                    },
                },
            },
            {
                "name": "write_artifact",
                "description": "Write or overwrite a text or base64 file under a validated workspace or session path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                        "encoding": {
                            "type": "string",
                            "description": "'utf-8' for text, 'base64' for binary",
                            "default": "utf-8",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "apply_patch",
                "description": "Apply a unified diff patch to a file under a validated workspace or session path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "patch": {"type": "string"},
                        "workspace": {"type": "string"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["path", "patch"],
                },
            },
            {
                "name": "execute",
                "description": "Main entry point. Execute a request with automatic intent routing, starting the matched workflow/skill in the background. Prefer this for general requests. Use query_workflow_status to poll for completion.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The user request to execute",
                        },
                        "intent": {
                            "type": "string",
                            "description": "Intent to use (auto, implement, review, investigate, plan)",
                            "default": "auto",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "implement",
                "description": "Implement a feature or fix with a single coder-role Devin dispatch. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The implementation request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "review",
                "description": "Review code changes using the `code_review` workflow. Use for code diff review, PR review, or general code quality evaluation. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The review request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "investigate",
                "description": "Investigate an incident, bug, or failure using the `rca` workflow. Read-only; no git write operations. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The investigation request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "plan",
                "description": "Create a detailed implementation plan using the `writing-plans` skill. Produces a plan.md with bite-sized tasks. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The planning request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["request"],
                },
            },
            {
                "name": "run_workflow",
                "description": "Run a named workflow (code_review, pr_review, rca) with a request. Starts in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "string",
                            "description": "Name of the workflow to run",
                        },
                        "request": {
                            "type": "string",
                            "description": "The user request",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["workflow", "request"],
                },
            },
            {
                "name": "gate_decision",
                "description": "Submit a human/agent decision for a workflow gate.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "gate_id": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "description": "approve | request_changes | block",
                        },
                        "notes": {"type": "string"},
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id", "gate_id", "verdict"],
                },
            },
            {
                "name": "continue_workflow",
                "description": "Resume a workflow that is paused at a gate. Optionally supply a gate verdict. The workflow resumes in the background; use query_workflow_status to poll.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "gate_verdict": {
                            "type": "string",
                            "description": "Optional verdict to write before resuming (approve | request_changes | block)",
                        },
                        "gate_notes": {"type": "string"},
                        "gate_id": {"type": "string"},
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "gate_mode": {
                            "type": "string",
                            "description": "Gate interaction mode (interactive, signal, auto). Defaults to auto for MCP.",
                            "default": "auto",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "query_workflow_status",
                "description": "Poll the status of a started or continued workflow. Returns session status, stages, and the final result once available.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID returned by run_workflow/continue_workflow/execute/implement/review/investigate/plan/run_skill",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "run_skill",
                "description": "Run a process skill (e.g. brainstorming, writing-plans, systematic-debugging) in a fresh session. Starts in the background; use query_workflow_status to poll. NOT for implementation or code-fix tasks; use `implement`, `run_workflow`, or `dispatch_devin` for those.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "description": "Name of the process skill to run (e.g. brainstorming, writing-plans, systematic-debugging). Avoid implementation skills like executing-plans here; prefer implement/run_workflow/dispatch_devin.",
                        },
                        "request": {
                            "type": "string",
                            "description": "The request to process. For broad implementation requests, the server may direct you to a more appropriate tool.",
                        },
                        "demo_mode": {
                            "type": "boolean",
                            "description": "If true, simulate Devin dispatches instead of running real agents",
                            "default": False,
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum seconds to wait for each Devin dispatch (defaults to config)",
                            "default": 300,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["skill", "request"],
                },
            },
            {
                "name": "list_sessions",
                "description": "List sessions in the configured session work directory. Returns session_id, type, status, and last update time.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_type": {
                            "type": "string",
                            "description": "Filter by session type: all, workflow, dispatch, skill",
                            "default": "all",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of sessions to return (0 for all)",
                            "default": 0,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                },
            },
            {
                "name": "cancel_session",
                "description": "Request cancellation of a running or waiting workflow, skill, or dispatch session.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID to cancel",
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional workspace path; overrides the server's pre-loaded workspace",
                        },
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "health",
                "description": "Return the health status of the devin-orchestrator installation and active sessions.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    # --------------------------------------------------------------------- #
    # JSON-RPC message handling
    # --------------------------------------------------------------------- #

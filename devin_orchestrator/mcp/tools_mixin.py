from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import yaml

from devin_orchestrator.config_loader import ConfigLoader  # noqa: E402
from devin_orchestrator.mcp.tools_skill_mixin import McpSkillToolsMixin
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_workflow_name,
)

logger = logging.getLogger(__name__)


class McpToolsMixin(McpSkillToolsMixin):
    # --------------------------------------------------------------------- #
    # Tool implementations
    # --------------------------------------------------------------------- #
    def _run_tool(self, name: str, arguments: dict) -> list[dict]:
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            raise ValueError(f"Unknown tool: {name}")
        return method(arguments)

    def _tool_list_workflows(self, _arguments: dict) -> list[dict]:
        """
        List all available workflow manifests with their metadata.

        Args:
            _arguments: Tool arguments (unused)

        Returns:
            List containing JSON-formatted workflow definitions
        """
        workflows_dir = self.config.workflows_dir
        workflows = []
        use_case_map: dict[str, list[dict]] = {}
        use_cases_file = workflows_dir / "use-cases.yaml"
        if use_cases_file.exists():
            try:
                use_cases_data = (
                    yaml.safe_load(use_cases_file.read_text(encoding="utf-8")) or {}
                )
                for uc in use_cases_data.get("use_cases", []):
                    wf_name = uc.get("workflow")
                    if not wf_name:
                        continue
                    use_case_map.setdefault(wf_name, []).append(
                        {
                            "id": uc.get("id"),
                            "name": uc.get("name"),
                            "type": uc.get("type"),
                            "description": uc.get("description"),
                            "slash_command": uc.get("slash_command"),
                            "git_operations": uc.get("git_operations"),
                            "session_id_format": uc.get("session_id_format"),
                        }
                    )
            except (FileNotFoundError, yaml.YAMLError, ValueError, TypeError) as e:
                # Malformed use-cases should not break workflow listing, but should be logged.
                logger.warning(
                    "Failed to parse use-cases file %s: %s", use_cases_file, e
                )
        if workflows_dir.exists():
            for manifest in sorted(workflows_dir.glob("*.manifest.yaml")):
                try:
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError as e:
                    # Skip malformed workflow manifests so a single corrupt
                    # file does not crash the listing operation.
                    logger.warning(
                        "Skipping malformed workflow manifest %s: %s",
                        manifest,
                        e,
                    )
                    continue
                wf_name = manifest.stem.replace(".manifest", "")
                workflows.append(
                    {
                        "name": wf_name,
                        "description": data.get("description", ""),
                        "schema_version": data.get("schema_version", ""),
                        "use_cases": use_case_map.get(wf_name, []),
                    }
                )
        return [self._text_content(json.dumps(workflows, indent=2))]

    def _tool_get_workflow(self, arguments: dict) -> list[dict]:
        """
        Get a workflow manifest and its runbook.

        Args:
            arguments: Tool arguments containing workflow name

        Returns:
            List containing workflow manifest and runbook

        Raises:
            FileNotFoundError: If workflow is not found
        """
        try:
            name = arguments["name"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid name parameter: {e}")]

        # Validate workflow name to prevent path traversal. Workflow names allow
        # underscores (e.g. code_review) unlike skill names which are hyphen-only.
        try:
            workflow_name = validate_workflow_name(name)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid workflow name: {e}")]

        # Workflow files are directly in workflows_dir. Resolve the manifest
        # path against workflows_dir before validation so relative names are
        # contained correctly (validate_path_safe resolves bare relative paths
        # against CWD, which would escape the base directory).
        try:
            manifest = validate_path_safe(
                self.config.workflows_dir,
                self.config.workflows_dir / f"{workflow_name}.manifest.yaml",
                allow_absolute=True,
            )
        except (InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Path validation failed: {e}")]

        runbook = manifest.parent / f"{workflow_name}.runbook.md"
        if not manifest.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_name}")
        parts = ["# Manifest\n", manifest.read_text(encoding="utf-8")]
        if runbook.exists():
            parts.extend(["\n# Runbook\n", runbook.read_text(encoding="utf-8")])
        return [self._text_content("".join(parts))]

    def _tool_execute(self, arguments: dict) -> list[dict]:
        """
        Execute a request with automatic or explicit intent routing.

        Starts the matched workflow/skill in a background thread and returns
        the session_id immediately. Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, intent, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        intent = arguments.get("intent", "auto")
        result = orchestrator.execute_async(request, intent)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_implement(self, arguments: dict) -> list[dict]:
        """
        Execute an implementation request using the superpower workflow.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.implement_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_review(self, arguments: dict) -> list[dict]:
        """
        Execute a review request using the code_review workflow.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.review_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_investigate(self, arguments: dict) -> list[dict]:
        """
        Execute an investigation request using the rca workflow.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        request = arguments["request"]
        result = orchestrator.investigate_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_plan(self, arguments: dict) -> list[dict]:
        """
        Execute a planning request using the writing-plans skill.

        Args:
            arguments: Tool arguments containing request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
        )
        request = arguments["request"]
        result = orchestrator.plan_async(request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_run_workflow(self, arguments: dict) -> list[dict]:
        """
        Run a specific workflow with a request.

        Starts the workflow in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing workflow, request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )

        # Validate workflow name to prevent path traversal / manifest injection.
        # Mirrors the pattern used in _tool_get_workflow. Workflow names allow
        # underscores (e.g. code_review) unlike skill names which are hyphen-only.
        try:
            workflow = arguments["workflow"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid workflow parameter: {e}")]
        try:
            workflow_name = validate_workflow_name(workflow)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid workflow name: {e}")]

        request = arguments["request"]
        result = orchestrator.run_workflow_async(workflow_name, request)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_gate_decision(self, arguments: dict) -> list[dict]:
        """
        Write a gate decision to the session's gate decision file.

        Args:
            arguments: Tool arguments containing session_id, gate_id, verdict, notes,
                and optional workspace

        Returns:
            List containing success message
        """
        from devin_orchestrator.session_manager import resolve_session

        session_id = arguments.get("session_id")
        gate_id = arguments.get("gate_id")
        verdict = arguments.get("verdict")
        notes = arguments.get("notes", "")

        if not all([session_id, gate_id, verdict]):
            return [self._text_content("session_id, gate_id, and verdict are required")]

        if not isinstance(session_id, str):
            return [self._text_content("session_id must be a string")]

        workspace = arguments.get("workspace") or self.workspace
        session_work_dir = (
            ConfigLoader.load(workspace=workspace).session_work_dir
            if workspace
            else self.config.session_work_dir
        )

        try:
            session_dir = resolve_session(session_work_dir, session_id)
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            return [self._text_content(f"Failed to resolve session: {e}")]

        decision_file = session_dir / f"gate-{gate_id}-decision.md"
        try:
            decision_file.write_text(
                f"verdict: {verdict}\nnotes: {notes}\n", encoding="utf-8"
            )
        except (OSError, PermissionError) as e:
            return [self._text_content(f"Failed to write gate decision: {e}")]

        return [
            self._text_content(
                f"Gate decision written for {gate_id}. "
                f"Call continue_workflow with session_id {session_id} to resume."
            )
        ]

    def _tool_continue_workflow(self, arguments: dict) -> list[dict]:
        """
        Resume a workflow that is paused at a gate.

        Starts the continuation in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing session_id, optional workspace,
                demo_mode, timeout, gate_mode, and optional gate verdict

        Returns:
            List containing session info with session_id and status
        """
        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
            gate_mode=arguments.get("gate_mode", "auto"),
        )
        result = orchestrator.continue_workflow_async(
            session_id=session_id,
            gate_verdict=arguments.get("gate_verdict"),
            gate_notes=arguments.get("gate_notes"),
            gate_id=arguments.get("gate_id"),
        )
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_query_workflow_status(self, arguments: dict) -> list[dict]:
        """
        Poll the status of a started or continued workflow/skill.

        Args:
            arguments: Tool arguments containing session_id and optional workspace

        Returns:
            List containing status, stages, and result
        """
        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        orchestrator = self._orchestrator_for_call(arguments)
        result = orchestrator.get_workflow_status(session_id)
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_list_sessions(self, arguments: dict) -> list[dict]:
        """
        List sessions in the configured session work directory.

        Args:
            arguments: Tool arguments containing optional session_type and limit

        Returns:
            List of session records
        """
        try:
            orchestrator = self._orchestrator_for_call(arguments)
            base = orchestrator.config.session_work_dir
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            return [self._text_content(f"Invalid workspace: {e}")]

        if not base.is_dir():
            return [self._text_content(f"Session directory not found: {base}")]

        session_type = arguments.get("session_type", "all")
        if session_type not in ("all", "workflow", "dispatch", "skill"):
            return [
                self._text_content(
                    "session_type must be all, workflow, dispatch, or skill"
                )
            ]

        try:
            limit = int(arguments.get("limit", 0))
        except (TypeError, ValueError):
            return [self._text_content("Invalid limit")]

        session_re = re.compile(r"^[A-Za-z0-9_-]+-\d+$")
        entries: list[dict[str, Any]] = []
        for entry in sorted(
            base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if not entry.is_dir() or not session_re.match(entry.name):
                continue
            entry_type = "workflow"
            if entry.name.startswith("DISPATCH-"):
                entry_type = "dispatch"
            elif entry.name.startswith("SKILL-"):
                entry_type = "skill"
            if session_type != "all" and entry_type != session_type:
                continue

            session_file = entry / "session.json"
            result_file = entry / "result.json"
            status = "unknown"
            last_update = entry.stat().st_mtime
            if session_file.exists():
                try:
                    data = json.loads(session_file.read_text(encoding="utf-8"))
                    status = data.get("status", status)
                    last_update = max(last_update, session_file.stat().st_mtime)
                except (OSError, json.JSONDecodeError):
                    pass
            if result_file.exists():
                last_update = max(last_update, result_file.stat().st_mtime)

            entries.append(
                {
                    "session_id": entry.name,
                    "type": entry_type,
                    "status": status,
                    "last_update": datetime.fromtimestamp(
                        last_update, tz=timezone.utc
                    ).isoformat(),
                    "workspace": str(entry),
                }
            )

        if limit > 0:
            entries = entries[:limit]

        return [self._text_content(json.dumps(entries, indent=2, default=str))]

    def _tool_cancel_session(self, arguments: dict) -> list[dict]:
        """
        Request cancellation of a session.

        Args:
            arguments: Tool arguments containing session_id and optional workspace

        Returns:
            JSON with session_id and status
        """
        session_id = arguments.get("session_id")
        if not session_id:
            return [self._text_content("session_id is required")]

        try:
            orchestrator = self._orchestrator_for_call(arguments)
            result = orchestrator.cancel_session(str(session_id))
            return [self._text_content(json.dumps(result, indent=2))]
        except (InvalidInputError, PathTraversalError, FileNotFoundError) as e:
            return [self._text_content(f"Failed to cancel session: {e}")]

    def _tool_health(self, _arguments: dict) -> list[dict]:
        """Return the JSON health report for this orchestrator installation."""
        from devin_orchestrator.health_check import health

        work_dir = getattr(self.config, "session_work_dir", None)
        report = health(work_dir=work_dir)
        return [self._text_content(json.dumps(report, indent=2, default=str))]

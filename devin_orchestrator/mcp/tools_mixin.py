# mypy: disable-error-code=attr-defined

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import yaml

from devin_orchestrator.config_loader import ConfigLoader  # noqa: E402
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_skill_name,
    validate_workflow_name,
)

logger = logging.getLogger(__name__)


MAX_OUTPUT_BYTES = 5 * 1024 * 1024  # keep in sync with McpServer


class McpToolsMixin:

    # --------------------------------------------------------------------- #
    # Tool implementations
    # --------------------------------------------------------------------- #
    def _run_tool(self, name: str, arguments: dict) -> list[dict]:
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            raise ValueError(f"Unknown tool: {name}")
        return method(arguments)

    def _tool_list_skills(self, _arguments: dict) -> list[dict]:
        """
        List all available skills with their metadata.

        Args:
            _arguments: Tool arguments (unused)

        Returns:
            List containing JSON-formatted skill definitions
        """
        skills_dir = self.config.skills_dir
        skills = []
        if skills_dir.exists():
            for entry in sorted(skills_dir.iterdir()):
                yaml_file = entry / f"{entry.name}.yaml"
                if entry.is_dir() and yaml_file.exists():
                    try:
                        data = (
                            yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
                        )
                    except yaml.YAMLError as e:
                        # Skip malformed skill YAML files so a single corrupt
                        # file does not crash the listing operation.
                        logger.warning(
                            "Skipping malformed skill YAML %s: %s",
                            yaml_file,
                            e,
                        )
                        continue
                    skills.append(
                        {
                            "name": entry.name,
                            "description": data.get("description", ""),
                            "iron_law": data.get("iron_law", ""),
                        }
                    )
        return [self._text_content(json.dumps(skills, indent=2))]

    def _tool_get_skill(self, arguments: dict) -> list[dict]:
        """
        Get the YAML definition and markdown narrative for a skill.

        Args:
            arguments: Tool arguments containing skill name

        Returns:
            List containing skill definition and narrative

        Raises:
            FileNotFoundError: If skill is not found
        """
        try:
            name = arguments["name"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid name parameter: {e}")]

        # Validate skill name to prevent path traversal
        try:
            skill_name = validate_skill_name(name)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid skill name: {e}")]

        # Resolve the skill directory against skills_dir before validation so
        # relative names are contained correctly (validate_path_safe resolves
        # bare relative paths against CWD, which would escape the base
        # directory). Mirrors the _tool_get_workflow pattern.
        try:
            skill_dir = validate_path_safe(
                self.config.skills_dir,
                self.config.skills_dir / skill_name,
                allow_absolute=True,
            )
        except (InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Path validation failed: {e}")]

        yaml_file = skill_dir / f"{skill_name}.yaml"
        md_file = skill_dir / f"{skill_name}.md"
        if not yaml_file.exists():
            raise FileNotFoundError(f"Skill not found: {skill_name}")
        parts = ["# YAML\n", yaml_file.read_text(encoding="utf-8")]
        if md_file.exists():
            parts.extend(["\n# Markdown\n", md_file.read_text(encoding="utf-8")])
        return [self._text_content("".join(parts))]

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
            except (FileNotFoundError, yaml.YAMLError, ValueError, KeyError):
                # Silently handle errors in use-cases file to avoid breaking workflow listing
                pass
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

    @staticmethod
    def _truncate_output(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
        """Truncate ``text`` to ``max_bytes`` UTF-8 bytes and append a marker."""
        if not text:
            return text
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        marker = "\n... [output truncated]\n"
        keep = max(0, max_bytes - len(marker.encode("utf-8")))
        truncated = encoded[:keep].decode("utf-8", errors="ignore")
        return truncated + marker

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

        assert isinstance(session_id, str)

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

    def _tool_run_skill(self, arguments: dict) -> list[dict]:
        """
        Run a specific skill with a request.

        Starts the skill in the background and returns the session_id.
        Use query_workflow_status to poll.

        Args:
            arguments: Tool arguments containing skill, request, demo_mode, timeout,
                and optional workspace

        Returns:
            List containing session info with session_id and status
        """
        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        # Validate skill name to prevent path traversal. This is the single
        # validation point at the MCP tool entry for the run_skill chain.
        try:
            skill = arguments["skill"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid skill parameter: {e}")]
        try:
            skill_name = validate_skill_name(skill)
        except InvalidInputError as e:
            return [self._text_content(f"Invalid skill name: {e}")]

        # run_skill is a low-level tool intended for process skills that do not
        # require project context or focused artifacts. Implementation, review,
        # and investigation skills should use the dedicated high-level tools or
        # focused dispatch_devin so the worker gets the right files and criteria.
        process_skills = {
            "brainstorming",
            "writing-plans",
            "systematic-debugging",
        }
        if skill_name not in process_skills:
            return [
                self._text_content(
                    json.dumps(
                        {
                            "success": False,
                            "error": (
                                f"run_skill is not the right tool for '{skill_name}'. "
                                "It is intended for process skills only. "
                                "For implementation use `implement`, `run_workflow`, or "
                                "`dispatch_devin`. For review use `review` or "
                                "`dispatch_devin` with a reviewer role. For investigation "
                                "use `investigate` or `dispatch_devin` with a reviewer role."
                            ),
                            "skill": skill_name,
                            "suggested_tools": [
                                "implement",
                                "run_workflow",
                                "dispatch_devin",
                                "review",
                                "investigate",
                            ],
                        },
                        indent=2,
                    )
                )
            ]

        orchestrator = self._orchestrator_for_call(
            arguments,
            demo_mode=arguments.get("demo_mode", False),
            timeout=timeout,
        )
        request = arguments["request"]
        result = orchestrator.run_skill_async(skill_name, request)
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
            return [self._text_content("session_type must be all, workflow, dispatch, or skill")]

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

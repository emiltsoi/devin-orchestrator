from __future__ import annotations

import json
import logging

import yaml

from devin_orchestrator.mcp._base import McpServerBase
from devin_orchestrator.mcp.constants import MAX_OUTPUT_BYTES  # noqa: E402
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_skill_name,
)

logger = logging.getLogger(__name__)


class McpSkillToolsMixin(McpServerBase):
    """Skill-related MCP tool implementations."""

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

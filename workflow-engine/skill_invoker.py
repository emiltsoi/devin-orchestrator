"""
Skill Invoker - Invokes skills using transport adapters
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from devin_cli_adapter import DevinCliAdapter
from metrics import get_metrics_collector
from security_utils import InvalidInputError, validate_skill_name

if TYPE_CHECKING:
    from metrics import MetricsCollector


@dataclass
class SkillInvocationResult:
    """Result of skill invocation"""

    success: bool
    session_id: str | None
    output: str | None
    error: str | None


class SkillInvoker:
    """
    Invokes skills using transport adapters

    Loads skill definitions and uses transport adapters to spawn
    agent sessions for skill execution.

    Caching: Skill definitions and narratives are cached in-memory
    after first load to avoid redundant file I/O. Cache is per-instance
    and can be cleared via clear_skill_cache() if needed.
    """

    def __init__(
        self,
        skills_dir: Path | None = None,
        devin_cli_path: str | None = None,
        model: str | None = None,
        permission_mode: str = "dangerous",
        demo_mode: bool = False,
        metrics: "MetricsCollector | None" = None,
    ):
        """
        Initialize skill invoker

        Args:
            skills_dir: Optional path to skills directory (defaults to global config)
            devin_cli_path: Optional path to devin.exe (for devin-cli adapter)
            model: Optional model to use (e.g., "claude-sonnet-4", "claude-opus-4.6")
            permission_mode: Permission mode (auto, smart, dangerous) - defaults to dangerous for automated dispatch
            demo_mode: If True, skip real Devin dispatches and simulate (for testing)
            metrics: Optional metrics collector (defaults to global instance)
        """
        from config_loader import ConfigLoader

        config = ConfigLoader.load()

        self.skills_dir = skills_dir if skills_dir is not None else config.skills_dir
        self.devin_cli_path = (
            devin_cli_path if devin_cli_path is not None else config.devin_cli_path
        )
        # If configured path does not exist, treat as unconfigured
        if self.devin_cli_path and not Path(self.devin_cli_path).exists():
            self.devin_cli_path = None
        self.model = model if model is not None else config.default_model
        self.permission_mode = (
            permission_mode
            if permission_mode is not None
            else config.default_permission_mode
        )
        self.demo_mode = demo_mode
        self.dispatch_timeout_seconds = getattr(
            config, "dispatch_timeout_seconds", 300
        )
        # Use provided metrics or fall back to global instance for backward compatibility
        self.metrics = metrics if metrics is not None else get_metrics_collector()

    def _parse_config_overrides(self, config_overrides: Any) -> dict:
        """
        Parse and validate config_overrides parameter.

        Args:
            config_overrides: Config overrides (can be dict, JSON string, or other types)

        Returns:
            Validated config overrides dictionary

        Raises:
            InvalidInputError: If config_overrides is invalid or malformed JSON
        """
        if config_overrides is None:
            return {}

        # If it's already a dict, validate and return it
        if isinstance(config_overrides, dict):
            return self._validate_config_overrides_dict(config_overrides)

        # If it's a string, try to parse as JSON
        if isinstance(config_overrides, str):
            try:
                parsed = json.loads(config_overrides)
                if not isinstance(parsed, dict):
                    raise InvalidInputError(
                        "config_overrides JSON must parse to an object/dictionary"
                    )
                return self._validate_config_overrides_dict(parsed)
            except json.JSONDecodeError as e:
                raise InvalidInputError(
                    f"config_overrides contains malformed JSON: {e}"
                ) from e

        # Any other type is invalid
        raise InvalidInputError(
            f"config_overrides must be a dictionary or JSON string, got {type(config_overrides).__name__}"
        )

    def _validate_config_overrides_dict(self, config_overrides: dict) -> dict:
        """
        Validate that config_overrides dictionary contains only safe values.

        Args:
            config_overrides: Dictionary to validate

        Returns:
            Validated dictionary

        Raises:
            InvalidInputError: If dictionary contains invalid keys or values
        """
        # Validate config_overrides keys are strings and values are basic types
        valid_types = (str, int, float, bool, type(None))
        for key, value in config_overrides.items():
            if not isinstance(key, str):
                raise InvalidInputError(
                    f"config_overrides key must be string, got {type(key).__name__}"
                )
            if not isinstance(value, valid_types):
                raise InvalidInputError(
                    f"config_overrides value for key '{key}' must be basic type (str, int, float, bool, None), got {type(value).__name__}"
                )

        return config_overrides

    def invoke_skill(
        self,
        skill_name: str,
        context: dict[str, Any],
        workspace: str | None = None,
        custom_prompt: str | None = None,
        focused_context: list | None = None,
        correction_artifact: str | None = None,
        is_reviewer: bool = False,
        config_overrides: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> SkillInvocationResult:
        """
        Invoke a skill using the devin-cli transport adapter

        Args:
            skill_name: Name of the skill to invoke
            context: Context data for the skill (e.g., session_id, step, artifacts)
            workspace: Optional workspace path
            custom_prompt: Optional custom prompt (for retry with feedback)
            focused_context: Optional list of artifact paths to inject into worker dispatch
            correction_artifact: Optional path to correction artifact for retry loops
            is_reviewer: Whether this is a reviewer dispatch (triggers swe-compliance skill)
            timeout: Optional per-call timeout in seconds (defaults to configured value)

        Returns:
            SkillInvocationResult with success status and output
        """
        # Validate the skill name before it is interpolated into any filesystem
        # path. This is the single choke point for the run_skill chain
        # (MCP _tool_run_skill -> StatelessOrchestrator.run_skill -> here ->
        # deterministic_tools.load_skill) and prevents path traversal via names
        # like "../../etc/passwd".
        try:
            validated_skill_name = validate_skill_name(skill_name)
        except InvalidInputError as e:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=f"Invalid skill name: {e}",
            )

        effective_timeout = timeout or self.dispatch_timeout_seconds
        if not self.devin_cli_path:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error="Devin CLI path not configured",
            )

        # Load skill definition and narrative using deterministic_tools
        from deterministic_tools import load_skill

        try:
            skill_data = load_skill(self.skills_dir, validated_skill_name)
        except FileNotFoundError as e:
            error_msg = str(e)
            if "markdown not found" in error_msg:
                return SkillInvocationResult(
                    success=False,
                    session_id=None,
                    output=None,
                    error=f"Skill narrative not found: {skill_name}",
                )
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=f"Skill definition not found: {skill_name}",
            )

        if not skill_data:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=f"Skill not found: {skill_name}",
            )

        skill_def = skill_data["definition"]
        skill_narrative = skill_data["narrative"]

        # Apply config overrides to skill definition with validation
        if config_overrides:
            try:
                overrides = self._parse_config_overrides(config_overrides)
            except InvalidInputError as e:
                return SkillInvocationResult(
                    success=False,
                    session_id=None,
                    output=None,
                    error=f"Invalid config_overrides: {str(e)}",
                )

            if "configuration" not in skill_def:
                skill_def["configuration"] = {}
            skill_def["configuration"].update(overrides)

        # Use custom prompt if provided (for retry), otherwise build standard prompt
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = self.build_skill_prompt(
                skill_name,
                skill_def,
                skill_narrative,
                context,
                focused_context,
                correction_artifact,
                is_reviewer,
            )

        # Generate session ID for tracking
        session_id = f"{skill_name}-{context.get('session_id', 'unknown')}"

        # Demo mode: skip real Devin dispatch and simulate success
        if self.demo_mode:
            return SkillInvocationResult(
                success=True,
                session_id=session_id,
                output=f"Simulated output for {skill_name} skill (demo mode)",
                error=None,
            )

        try:
            # Use simple adapter with --print mode
            # Disable skill injection since we load skills directly via skill_invoker
            adapter = DevinCliAdapter(
                self.devin_cli_path, workspace, self.model, self.permission_mode
            )
            result = adapter.invoke(
                prompt,
                timeout=effective_timeout,
                focused_context=focused_context,
                correction_artifact=correction_artifact,
                enable_skills=False,
            )

            return SkillInvocationResult(
                success=result.success,
                session_id=session_id,
                output=result.output,
                error=result.error,
            )

        except (InvalidInputError, ValueError) as e:
            return SkillInvocationResult(
                success=False, session_id=None, output=None, error=f"Validation error: {str(e)}"
            )
        except OSError as e:
            return SkillInvocationResult(
                success=False, session_id=None, output=None, error=f"File system error: {str(e)}"
            )
        except Exception as e:
            return SkillInvocationResult(
                success=False, session_id=None, output=None, error=f"Unexpected error: {str(e)}"
            )

    def build_skill_prompt(
        self,
        skill_name: str,
        skill_def: dict[str, Any],
        skill_narrative: str,
        context: dict[str, Any],
        focused_context: list | None = None,
        correction_artifact: str | None = None,
        is_reviewer: bool = False,
    ) -> str:
        """
        Build prompt for skill invocation

        Args:
            skill_name: Name of the skill
            skill_def: Skill YAML definition
            skill_narrative: Skill markdown narrative
            context: Context data
            focused_context: Optional list of artifact paths to inject into worker dispatch
            correction_artifact: Optional path to correction artifact for retry loops
            is_reviewer: Whether this is a reviewer dispatch (triggers swe-compliance skill)

        Returns:
            Prompt string
        """
        # Add skill trigger phrases for description matching
        # These trigger the ponytail and swe-compliance skills via description matching
        trigger_phrase = ""
        if is_reviewer:
            trigger_phrase = "This is a compliance review task, code verification, artifact audit, and quality check."
        else:
            trigger_phrase = "This is a coding dispatch and implementation task."

        prompt = f"""# Skill Invocation: {skill_name}

{trigger_phrase}

## Context
"""
        # Add context information
        for key, value in context.items():
            prompt += f"- {key}: {value}\n"

        # Add focused context artifacts if provided
        if focused_context:
            prompt += "\n## Focused Context Artifacts\n"
            for artifact_path in focused_context:
                prompt += f"- {artifact_path}\n"

        # Add correction artifact if provided
        if correction_artifact:
            prompt += f"\n## Correction Artifact\n- {correction_artifact}\n"

        prompt += f"""
## Skill Definition
**Iron Law:** {skill_def.get("iron_law", "N/A")}
**Announcement:** {skill_def.get("announcement", f"Using {skill_name} skill")}

## Skill Narrative
{skill_narrative}

## Instructions
Execute this skill according to its definition and narrative. Follow the iron law strictly.
"""

        return prompt

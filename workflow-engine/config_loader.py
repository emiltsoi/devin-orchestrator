#!/usr/bin/env python3
"""
Global Configuration Loader

Loads global configuration for devin-orchestrator.
Supports environment variables and config file.
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from security_utils import InvalidInputError

# Allowlist of valid devin-cli permission modes. Must match the allowlist
# enforced by DevinCliAdapter. Invalid configured values fall back to
# "dangerous" for automated dispatch.
ALLOWED_PERMISSION_MODES = frozenset({"dangerous", "smart", "auto"})

logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """Global configuration for devin-orchestrator"""

    global_root: Path
    skills_dir: Path
    workflows_dir: Path
    workflow_engine_dir: Path
    devin_cli_path: str
    default_model: str
    default_permission_mode: str
    session_work_dir: Path
    # Optional model routing fields. Empty dicts/strings mean "unset" and
    # resolve_model() falls back to default_model. These are populated from
    # config.yaml by ConfigLoader.load() with {} / "" defaults.
    model_profile: str = ""
    models: dict[str, str] | None = None
    model_overrides: dict[str, str] | None = None
    # Optional agent skill injection: maps agent name -> list of skill names.
    agent_skills: dict[str, list[str]] | None = None
    dispatch_timeout_seconds: int = 300
    gate_mode: str = "auto"
    gate_bypass_conditions: dict[str, Any] | None = None
    # Log rotation settings
    log_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    log_backup_count: int = 5


class ConfigLoader:
    """
    Loads global configuration from config file and environment variables.

    For new code, consider passing configuration explicitly rather than
    relying on global state via ConfigLoader.load().
    """

    DEFAULT_CONFIG_PATH = Path.home() / ".devin-orchestrator" / "config.yaml"
    FALLBACK_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

    @staticmethod
    def expand_env_vars(value: str) -> str:
        """
        Expand environment variables in a string.
        Supports ${VAR} and ${VAR:-default} syntax.

        Args:
            value: String that may contain environment variable references

        Returns:
            String with environment variables expanded

        Raises:
            InvalidInputError: If expanded value contains invalid characters
        """
        if not isinstance(value, str):
            return value

        # Pattern to match ${VAR} or ${VAR:-default}
        pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

        def replace_env_var(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""
            expanded = os.environ.get(var_name, default_value)

            # Validate expanded value
            if not isinstance(expanded, str):
                expanded = str(expanded)

            # Reject empty/whitespace-only results for required fields
            if expanded.strip() == "":
                logger.warning(
                    f"Environment variable {var_name} expanded to empty/whitespace-only string"
                )
                return ""

            # Remove control characters (except tab and newline which are sometimes legitimate)
            expanded = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]", "", expanded)

            return expanded

        return re.sub(pattern, replace_env_var, value)

    @staticmethod
    def _load_yaml_config(path: Path) -> dict:
        """Load a YAML config file and expand environment variables in scalars."""
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for key, value in list(data.items()):
            if isinstance(value, str):
                data[key] = ConfigLoader.expand_env_vars(value)
        return data

    @staticmethod
    def load(
        config_path: Path | None = None,
        workspace: Path | str | None = None,
    ) -> GlobalConfig:
        """
        Load global configuration, optionally merged with a workspace-local config.

        Args:
            config_path: Optional explicit path to the global config file.
            workspace: Optional workspace path. If a `.devin-orchestrator/config.yaml`
                exists inside the workspace, its values are merged on top of the
                global config, allowing per-workspace overrides of
                `session_work_dir`, `devin_cli_path`, model routing, etc.

        Returns:
            GlobalConfig object
        """
        # Determine global config file path
        if config_path is None:
            config_path = ConfigLoader.DEFAULT_CONFIG_PATH
            if not config_path.exists():
                config_path = ConfigLoader.FALLBACK_CONFIG_PATH

        config_data = ConfigLoader._load_yaml_config(config_path)

        # If a workspace is specified and contains a local config, merge it over
        # the global config so workspaces can override session-specific settings.
        if workspace is not None:
            workspace_path = Path(workspace)
            workspace_config = workspace_path / ".devin-orchestrator" / "config.yaml"
            workspace_data = ConfigLoader._load_yaml_config(workspace_config)
            if workspace_data:
                config_data = {**config_data, **workspace_data}
                # The workspace config is authoritative for session_work_dir if
                # it was not explicitly provided; otherwise path expansion below
                # will use the merged value as-is.

        # Expand paths (support ~ for home directory)
        def expand_path(path_str: str) -> Path:
            path = Path(path_str).expanduser()
            if not path.is_absolute():
                path = Path.home() / path
            return path

        # Validate that expanded paths don't escape intended boundaries
        def validate_expanded_path(path: Path, context: str) -> Path:
            """
            Validate that an expanded path doesn't escape safe boundaries.

            For path-context fields, ensure the result stays within reasonable
            directories (home directory or current directory tree).
            """
            try:
                # Allow paths under home directory or current directory
                home_dir = Path.home()
                current_dir = Path.cwd()

                # Resolve to absolute path
                resolved = path.resolve()

                # Check if path is under home or current directory
                try:
                    resolved.relative_to(home_dir)
                    return resolved  # Safe: under home directory
                except ValueError:
                    pass

                try:
                    resolved.relative_to(current_dir)
                    return resolved  # Safe: under current directory
                except ValueError:
                    pass

                # If neither, raise an error - unsafe path
                raise InvalidInputError(
                    f"Path {context}={resolved} is not under home or current directory; "
                    "this is unsafe and not allowed"
                )

            except (OSError, RuntimeError) as e:
                raise InvalidInputError(f"Path validation failed for {context}={path}: {e}") from e

        # Build configuration with environment variable overrides
        try:
            global_root = validate_expanded_path(
                expand_path(
                    os.getenv(
                        "DEVIN_ORCHESTRATOR_ROOT",
                        config_data.get("global_root", "~/.devin-orchestrator"),
                    )
                ),
                "global_root"
            )
        except InvalidInputError as e:
            raise InvalidInputError(f"Invalid global_root configuration: {e}") from e

        try:
            skills_dir = validate_expanded_path(
                expand_path(
                    os.getenv(
                        "DEVIN_ORCHESTRATOR_SKILLS_DIR",
                        config_data.get("skills_dir", "~/.devin-orchestrator/skills"),
                    )
                ),
                "skills_dir"
            )
        except InvalidInputError as e:
            raise InvalidInputError(f"Invalid skills_dir configuration: {e}") from e

        try:
            workflows_dir = validate_expanded_path(
                expand_path(
                    os.getenv(
                        "DEVIN_ORCHESTRATOR_WORKFLOWS_DIR",
                        config_data.get("workflows_dir", "~/.devin-orchestrator/workflows"),
                    )
                ),
                "workflows_dir"
            )
        except InvalidInputError as e:
            raise InvalidInputError(f"Invalid workflows_dir configuration: {e}") from e

        try:
            workflow_engine_dir = validate_expanded_path(
                expand_path(
                    os.getenv(
                        "DEVIN_ORCHESTRATOR_WORKFLOW_ENGINE_DIR",
                        config_data.get(
                            "workflow_engine_dir", "~/.devin-orchestrator/workflow-engine"
                        ),
                    )
                ),
                "workflow_engine_dir"
            )
        except InvalidInputError as e:
            raise InvalidInputError(f"Invalid workflow_engine_dir configuration: {e}") from e

        try:
            devin_cli_path = str(
                validate_expanded_path(
                    expand_path(
                        os.getenv(
                            "DEVIN_CLI_PATH",
                            config_data.get(
                                "devin_cli_path", "~/AppData/Local/devin/cli/bin/devin.exe"
                        ),
                    )
                ),
                "devin_cli_path"
            )
        )
        except InvalidInputError as e:
            raise InvalidInputError(f"Invalid devin_cli_path configuration: {e}") from e

        default_model = os.getenv(
            "DEVIN_DEFAULT_MODEL", config_data.get("default_model", "swe-1.6")
        )
        default_permission_mode = os.getenv(
            "DEVIN_DEFAULT_PERMISSION_MODE",
            config_data.get("default_permission_mode", "dangerous"),
        )
        # Validate the permission mode against the allowlist. An invalid value
        # (e.g. a typo in config or env) is logged and falls back to "dangerous"
        # so automated dispatch never forwards an unvalidated string to the CLI.
        if (
            not isinstance(default_permission_mode, str)
            or default_permission_mode == ""
            or default_permission_mode not in ALLOWED_PERMISSION_MODES
        ):
            logger.warning(
                "Invalid default_permission_mode %r; falling back to "
                "'dangerous'. Allowed values: %s",
                default_permission_mode,
                sorted(ALLOWED_PERMISSION_MODES),
            )
            default_permission_mode = "dangerous"

        try:
            session_work_dir = validate_expanded_path(
                expand_path(
                    os.getenv(
                        "DEVIN_SESSION_WORK_DIR",
                        config_data.get("session_work_dir", "~/.devin-orchestrator/work"),
                    )
                ),
                "session_work_dir"
            )
        except InvalidInputError as e:
            raise InvalidInputError(f"Invalid session_work_dir configuration: {e}") from e

        # Dispatch timeout for devin-cli calls; prevents hung agents from blocking
        # the orchestrator indefinitely.
        raw_timeout = os.getenv(
            "DEVIN_DISPATCH_TIMEOUT_SECONDS",
            config_data.get("dispatch_timeout_seconds", 300),
        )
        try:
            dispatch_timeout_seconds = int(raw_timeout)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid dispatch_timeout_seconds %r; falling back to 300",
                raw_timeout,
            )
            dispatch_timeout_seconds = 300

        # Gate interaction mode: controls whether workflow gates block, signal,
        # or auto-bypass when used from MCP or CLI.
        gate_mode = os.getenv(
            "DEVIN_GATE_MODE",
            config_data.get("gate_mode", "auto"),
        )
        if gate_mode not in {"interactive", "signal", "auto"}:
            logger.warning(
                "Invalid gate_mode %r; falling back to 'auto'",
                gate_mode,
            )
            gate_mode = "auto"

        gate_bypass_conditions = config_data.get("gate_bypass_conditions")
        if not isinstance(gate_bypass_conditions, dict):
            gate_bypass_conditions = None

        # Fallback to current directory for testing (if global paths don't exist)
        if not skills_dir.exists():
            skills_dir = Path(__file__).parent.parent / "skills"
        if not workflows_dir.exists():
            workflows_dir = Path(__file__).parent.parent / "workflows"
        if not workflow_engine_dir.exists():
            workflow_engine_dir = Path(__file__).parent
        if not session_work_dir.exists():
            session_work_dir = Path(__file__).parent / "work"

        # Optional model routing + agent skill injection fields. Defaults are
        # empty so resolve_model() falls back to default_model and dispatch
        # skips skill injection when nothing is configured.
        raw_model_profile = config_data.get("model_profile", "")
        if not isinstance(raw_model_profile, str):
            raw_model_profile = ""
        # Expand env vars in the profile string for consistency with other
        # scalar config values.
        raw_model_profile = ConfigLoader.expand_env_vars(raw_model_profile)

        raw_models = config_data.get("models", {})
        models = (
            {
                str(k): ConfigLoader.expand_env_vars(v)
                for k, v in raw_models.items()
                if isinstance(v, str)
            }
            if isinstance(raw_models, dict)
            else {}
        )

        raw_model_overrides = config_data.get("model_overrides", {})
        model_overrides = (
            {
                str(k): ConfigLoader.expand_env_vars(v)
                for k, v in raw_model_overrides.items()
                if isinstance(v, str)
            }
            if isinstance(raw_model_overrides, dict)
            else {}
        )

        raw_agent_skills = config_data.get("agent_skills", {})
        agent_skills = (
            {
                str(k): list(v) if isinstance(v, list) else [v]
                for k, v in raw_agent_skills.items()
            }
            if isinstance(raw_agent_skills, dict)
            else {}
        )

        # Log rotation settings with sensible defaults
        raw_log_max_bytes = config_data.get("log_max_bytes", 10 * 1024 * 1024)
        try:
            log_max_bytes = int(raw_log_max_bytes)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid log_max_bytes %r; falling back to 10MB",
                raw_log_max_bytes,
            )
            log_max_bytes = 10 * 1024 * 1024

        raw_log_backup_count = config_data.get("log_backup_count", 5)
        try:
            log_backup_count = int(raw_log_backup_count)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid log_backup_count %r; falling back to 5",
                raw_log_backup_count,
            )
            log_backup_count = 5

        return GlobalConfig(
            global_root=global_root,
            skills_dir=skills_dir,
            workflows_dir=workflows_dir,
            workflow_engine_dir=workflow_engine_dir,
            devin_cli_path=devin_cli_path,
            default_model=default_model,
            default_permission_mode=default_permission_mode,
            session_work_dir=session_work_dir,
            model_profile=raw_model_profile,
            models=models,
            model_overrides=model_overrides,
            agent_skills=agent_skills,
            dispatch_timeout_seconds=dispatch_timeout_seconds,
            gate_mode=gate_mode,
            gate_bypass_conditions=gate_bypass_conditions,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
        )


if __name__ == "__main__":
    # Test config loader
    config = ConfigLoader.load()
    print("=== Global Configuration ===")
    print(f"Global Root: {config.global_root}")
    print(f"Skills Dir: {config.skills_dir}")
    print(f"Workflows Dir: {config.workflows_dir}")
    print(f"Workflow Engine Dir: {config.workflow_engine_dir}")
    print(f"Devin CLI Path: {config.devin_cli_path}")
    print(f"Default Model: {config.default_model}")
    print(f"Default Permission Mode: {config.default_permission_mode}")
    print(f"Session Work Dir: {config.session_work_dir}")

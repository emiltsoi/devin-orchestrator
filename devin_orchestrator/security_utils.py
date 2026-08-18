#!/usr/bin/env python3
"""Security Utilities - Security hardening functions for devin-orchestrator

Provides:
- Path validation and traversal protection
- Input sanitization (re-exported from security_sanitizers)
- File permission checks (re-exported from security_sanitizers)
- Secrets management helpers (re-exported from security_sanitizers)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from devin_orchestrator.security_exceptions import (
    InvalidInputError,
    PathTraversalError,
    PermissionError,
    SecurityError,
)
from devin_orchestrator.security_sanitizers import (
    check_directory_permissions,
    check_file_permissions,
    get_secret_from_env,
    parse_config_overrides,
    redact_sensitive_data,
    sanitize_filename,
    sanitize_string,
    validate_backup_name,
    validate_session_id,
    validate_skill_name,
    validate_workflow_name,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SecurityError",
    "PathTraversalError",
    "InvalidInputError",
    "PermissionError",
    "validate_path_safe",
    "validate_workspace_path",
    "resolve_command",
    "sanitize_filename",
    "sanitize_string",
    "check_file_permissions",
    "check_directory_permissions",
    "validate_session_id",
    "validate_skill_name",
    "validate_workflow_name",
    "validate_backup_name",
    "get_secret_from_env",
    "redact_sensitive_data",
    "parse_config_overrides",
]


def validate_path_safe(
    base_path: Path, target_path: Path, allow_absolute: bool = False
) -> Path:
    """
    Validate that a target path is safe and doesn't escape the base path.

    Args:
        base_path: The base directory that paths should be contained within
        target_path: The target path to validate
        allow_absolute: Whether to allow absolute paths (default: False)

    Returns:
        The resolved, validated absolute path

    Raises:
        PathTraversalError: If the path attempts to escape the base directory
        InvalidInputError: If the path is invalid
    """
    # Reject empty path objects (e.g. Path("") or Path(".")) and string forms
    # that contain null bytes before any resolution to avoid ambiguous behavior.
    # Note: Path("") normalizes to Path(".") in Python, so treat both as empty.
    target_str = str(target_path)
    if not target_str or target_str.strip() in ("", "."):
        raise InvalidInputError("Target path cannot be empty")
    if "\x00" in target_str:
        raise InvalidInputError("Target path contains null bytes")

    base_str = str(base_path)
    if not base_str or base_str.strip() in ("", "."):
        raise InvalidInputError("Base path cannot be empty")
    if "\x00" in base_str:
        raise InvalidInputError("Base path contains null bytes")

    try:
        # Resolve the base path to its canonical absolute form. Using
        # os.path.realpath ensures symlinks are resolved and containment cannot
        # be bypassed via symlink chains pointing outside the base.
        resolved_base = Path(os.path.realpath(base_str))

        # Resolve the target. Relative targets are interpreted relative to the
        # base directory; absolute targets are resolved as-is. This lets callers
        # pass either form while still enforcing containment.
        if target_path.is_absolute():
            resolved_target = Path(os.path.realpath(target_str))
        else:
            resolved_target = Path(os.path.realpath(resolved_base / target_str))

        # Check if the resolved target is within the base path. Absolute paths
        # that resolve inside the base are safe; absolute (or relative) paths
        # that escape the base are always rejected, regardless of allow_absolute.
        try:
            resolved_target.relative_to(resolved_base)
            return resolved_target
        except ValueError:
            raise PathTraversalError(
                f"Path traversal detected: {target_path} resolves to {resolved_target} "
                f"which is outside base directory {resolved_base}"
            ) from None

    except (OSError, RuntimeError) as e:
        raise InvalidInputError(f"Invalid path {target_path}: {e}") from e


def validate_workspace_path(
    workspace: str, base_allowed_dir: Path | None = None
) -> Path:
    """
    Validate and sanitize a workspace path.

    Args:
        workspace: The workspace path to validate
        base_allowed_dir: Optional base directory that workspaces must be within

    Returns:
        Validated workspace path

    Raises:
        InvalidInputError: If the workspace path is invalid
        PathTraversalError: If the workspace path attempts to escape allowed directory
    """
    if not workspace:
        raise InvalidInputError("Workspace path cannot be empty")

    # Reject null bytes and control characters up front.
    if "\x00" in workspace:
        raise InvalidInputError("Workspace path contains null bytes")
    if re.search(r"[\x00-\x1f\x7f-\x9f]", workspace):
        raise InvalidInputError("Workspace path contains control characters")

    # base_allowed_dir is mandatory: without a containment boundary a workspace
    # path could point anywhere on the filesystem, defeating traversal
    # protection. Reject explicitly rather than silently resolving.
    if base_allowed_dir is None:
        raise InvalidInputError(
            "base_allowed_dir is required for workspace path validation"
        )

    workspace_path = Path(workspace)

    # Ensure workspace is within the allowed base directory. Absolute paths are
    # permitted so callers can pass fully-qualified workspace paths, but they
    # must still resolve inside base_allowed_dir.
    return validate_path_safe(base_allowed_dir, workspace_path, allow_absolute=True)


def resolve_command(command: str | Path) -> str:
    """
    Resolve an external command to an absolute, executable path.

    Accepts either a bare command name (searched for on the system PATH using
    ``shutil.which``) or an absolute/relative file path. The resolved path must
    exist and be executable, otherwise an ``InvalidInputError`` is raised so that
    a missing or unsafe command never reaches ``subprocess.run``.

    Args:
        command: Command name or path to resolve.

    Returns:
        Absolute path to the resolved executable.

    Raises:
        InvalidInputError: If the command cannot be resolved or is not executable.
    """
    command_str = str(command)
    command_path = Path(command_str)
    if command_path.is_absolute() and command_path.is_file():
        return command_str
    resolved = shutil.which(command_str)
    if resolved is None:
        raise InvalidInputError(f"Command not found or not executable: {command_str!r}")
    return resolved

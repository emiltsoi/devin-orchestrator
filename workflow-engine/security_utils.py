#!/usr/bin/env python3
"""
Security Utilities - Security hardening functions for devin-orchestrator

Provides:
- Path validation and traversal protection
- Input sanitization
- File permission checks
- Secrets management helpers
"""

import logging
import os
import re
import stat
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Base exception for security-related errors"""

    pass


class PathTraversalError(SecurityError):
    """Raised when path traversal is detected"""

    pass


class InvalidInputError(SecurityError):
    """Raised when input validation fails"""

    pass


class PermissionError(SecurityError):
    """Raised when file permission checks fail"""

    pass


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


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to prevent directory traversal and other attacks.

    Hardened against sophisticated evasion techniques including:
    - URL encoding (%2e%2e for "..", %2f for "/", etc.)
    - Null-byte injection
    - Double extensions (e.g., "file.txt.exe")
    - Leading/trailing whitespace
    - Unicode normalization attacks
    - Control characters

    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed length for the filename

    Returns:
        Sanitized filename

    Raises:
        InvalidInputError: If the filename is invalid after sanitization
    """
    if not filename:
        raise InvalidInputError("Filename cannot be empty")

    # Strip leading/trailing whitespace first
    sanitized = filename.strip()

    # Reject leading/trailing dots before sanitization
    if sanitized.startswith(".") or sanitized.endswith("."):
        raise InvalidInputError(f"Filename cannot start or end with dot: {filename}")

    # Decode URL-encoded strings (e.g., %2e%2e -> ..)
    try:
        from urllib.parse import unquote
        sanitized = unquote(sanitized)
    except Exception:
        # If URL decoding fails, continue with original string
        pass

    # Remove null bytes and other dangerous characters
    sanitized = sanitized.replace("\x00", "")

    # Remove control characters (except tab and newline which are sometimes legitimate)
    sanitized = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]", "", sanitized)

    # Remove path separators and parent directory references. We repeatedly
    # strip ".." so that sequences like "...." cannot collapse back into a
    # traversal segment after a single pass.
    sanitized = sanitized.replace("/", "").replace("\\", "")
    while ".." in sanitized:
        sanitized = sanitized.replace("..", "")

    # Strip leading/trailing dots again after URL decoding
    sanitized = sanitized.strip(".")

    # After stripping, check again for leading/trailing dots
    if sanitized.startswith(".") or sanitized.endswith("."):
        raise InvalidInputError(f"Filename cannot start or end with dot after sanitization: {filename}")

    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    # Ensure filename is not empty after sanitization
    if not sanitized:
        raise InvalidInputError(f"Filename is invalid after sanitization: {filename}")

    # Ensure filename contains only safe characters (alphanumeric, hyphen, underscore, dot)
    if not re.match(r"^[a-zA-Z0-9._-]+$", sanitized):
        raise InvalidInputError(f"Filename contains invalid characters after sanitization: {filename}")

    return sanitized


def sanitize_string(
    input_string: str, max_length: int = 10000, allowed_chars: str | None = None
) -> str:
    """
    Sanitize a string input to prevent injection attacks.

    Args:
        input_string: The string to sanitize
        max_length: Maximum allowed length
        allowed_chars: Optional regex pattern of allowed characters (None = allow most printable)

    Returns:
        Sanitized string

    Raises:
        InvalidInputError: If the input is invalid
    """
    if not isinstance(input_string, str):
        raise InvalidInputError("Input must be a string")

    if len(input_string) > max_length:
        raise InvalidInputError(f"Input exceeds maximum length of {max_length}")

    # Remove null bytes
    sanitized = input_string.replace("\x00", "")

    # If allowed_chars pattern is provided, validate against it
    if allowed_chars and not re.match(f"^[{allowed_chars}]*$", sanitized):
        raise InvalidInputError("Input contains invalid characters")

    return sanitized


def check_file_permissions(
    file_path: Path,
    required_read: bool = True,
    required_write: bool = False,
    required_execute: bool = False,
) -> bool:
    """
    Check if a file has the required permissions.

    Args:
        file_path: Path to the file to check
        required_read: Whether read permission is required
        required_write: Whether write permission is required
        required_execute: Whether execute permission is required

    Returns:
        True if permissions are sufficient, False otherwise
    """
    try:
        if not file_path.exists():
            return False

        file_stat = file_path.stat()
        mode = file_stat.st_mode

        # Check read permission
        if required_read and not (mode & stat.S_IRUSR):  # Owner read
            return False

        # Check write permission
        if required_write and not (mode & stat.S_IWUSR):  # Owner write
            return False

        # Check execute permission
        return not (required_execute and not (mode & stat.S_IXUSR))

    except OSError as e:
        logger.warning(f"Error checking file permissions for {file_path}: {e}")
        return False


def check_directory_permissions(
    dir_path: Path,
    required_read: bool = True,
    required_write: bool = False,
    required_execute: bool = True,
) -> bool:
    """
    Check if a directory has the required permissions.

    Args:
        dir_path: Path to the directory to check
        required_read: Whether read permission is required
        required_write: Whether write permission is required
        required_execute: Whether execute permission is required (needed for directory access)

    Returns:
        True if permissions are sufficient, False otherwise
    """
    try:
        if not dir_path.exists() or not dir_path.is_dir():
            return False

        dir_stat = dir_path.stat()
        mode = dir_stat.st_mode

        # Check read permission
        if required_read and not (mode & stat.S_IRUSR):
            return False

        # Check write permission
        if required_write and not (mode & stat.S_IWUSR):
            return False

        # Check execute permission (required for directory traversal)
        return not (required_execute and not (mode & stat.S_IXUSR))

    except OSError as e:
        logger.warning(f"Error checking directory permissions for {dir_path}: {e}")
        return False


def validate_session_id(session_id: str) -> str:
    """
    Validate and sanitize a session ID.

    Args:
        session_id: The session ID to validate

    Returns:
        Sanitized session ID

    Raises:
        InvalidInputError: If the session ID is invalid
    """
    if not session_id:
        raise InvalidInputError("Session ID cannot be empty")

    # Reject leading/trailing whitespace, dots, and control characters before
    # sanitization. These cannot form any valid session identifier and are
    # common vectors for traversal or injection.
    if session_id != session_id.strip():
        raise InvalidInputError(
            f"Session ID contains leading/trailing whitespace: {session_id!r}"
        )
    if session_id.startswith(".") or session_id.endswith("."):
        raise InvalidInputError(f"Session ID contains leading/trailing dot: {session_id!r}")
    if re.search(r"[\x00-\x1f\x7f-\x9f]", session_id):
        raise InvalidInputError(f"Session ID contains control characters: {session_id!r}")

    # Reject path separators and traversal sequences before sanitization
    if "/" in session_id or "\\" in session_id or ".." in session_id:
        raise InvalidInputError(f"Session ID contains invalid characters: {session_id}")

    # Sanitize the session ID
    sanitized = sanitize_filename(session_id, max_length=100)

    # Ensure it contains only safe characters (alphanumeric, hyphen, underscore)
    # Relaxed from original to allow underscores for more flexibility
    if not re.match(r"^[a-zA-Z0-9_-]+$", sanitized):
        raise InvalidInputError(f"Session ID contains invalid characters: {session_id}")

    return sanitized


def validate_skill_name(skill_name: str) -> str:
    """
    Validate and sanitize a skill name.

    Args:
        skill_name: The skill name to validate

    Returns:
        Sanitized skill name

    Raises:
        InvalidInputError: If the skill name is invalid
    """
    if not skill_name:
        raise InvalidInputError("Skill name cannot be empty")

    # Reject leading/trailing whitespace, dots, and control characters before
    # sanitization. These cannot form any valid skill name and are common
    # vectors for traversal or injection.
    if skill_name != skill_name.strip():
        raise InvalidInputError(
            f"Skill name contains leading/trailing whitespace: {skill_name!r}"
        )
    if skill_name.startswith(".") or skill_name.endswith("."):
        raise InvalidInputError(f"Skill name contains leading/trailing dot: {skill_name!r}")
    if re.search(r"[\x00-\x1f\x7f-\x9f]", skill_name):
        raise InvalidInputError(f"Skill name contains control characters: {skill_name!r}")

    # Reject path separators and traversal sequences before sanitization
    if "/" in skill_name or "\\" in skill_name or ".." in skill_name:
        raise InvalidInputError(f"Skill name contains invalid characters: {skill_name}")

    # Sanitize the skill name
    sanitized = sanitize_filename(skill_name, max_length=100)

    # Ensure it contains only safe characters (alphanumeric, hyphen)
    if not re.match(r"^[a-zA-Z0-9-]+$", sanitized):
        raise InvalidInputError(f"Skill name contains invalid characters: {skill_name}")

    return sanitized


def validate_workflow_name(workflow_name: str) -> str:
    """
    Validate and sanitize a workflow name.

    Workflow names follow the same safety rules as skill names but also allow
    underscores, since shipped workflows such as ``code_review`` use them.

    Args:
        workflow_name: The workflow name to validate

    Returns:
        Sanitized workflow name

    Raises:
        InvalidInputError: If the workflow name is invalid
    """
    if not workflow_name:
        raise InvalidInputError("Workflow name cannot be empty")

    # Reject leading/trailing whitespace, dots, and control characters before
    # sanitization. These cannot form any valid workflow name and are common
    # vectors for traversal or injection.
    if workflow_name != workflow_name.strip():
        raise InvalidInputError(
            f"Workflow name contains leading/trailing whitespace: {workflow_name!r}"
        )
    if workflow_name.startswith(".") or workflow_name.endswith("."):
        raise InvalidInputError(
            f"Workflow name contains leading/trailing dot: {workflow_name!r}"
        )
    if re.search(r"[\x00-\x1f\x7f-\x9f]", workflow_name):
        raise InvalidInputError(
            f"Workflow name contains control characters: {workflow_name!r}"
        )

    # Reject path separators and traversal sequences before sanitization
    if "/" in workflow_name or "\\" in workflow_name or ".." in workflow_name:
        raise InvalidInputError(
            f"Workflow name contains invalid characters: {workflow_name}"
        )

    # Sanitize the workflow name
    sanitized = sanitize_filename(workflow_name, max_length=100)

    # Ensure it contains only safe characters (alphanumeric, hyphen, underscore)
    if not re.match(r"^[a-zA-Z0-9_-]+$", sanitized):
        raise InvalidInputError(
            f"Workflow name contains invalid characters: {workflow_name}"
        )

    return sanitized


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


def get_secret_from_env(secret_name: str, default: str | None = None) -> str:
    """
    Safely retrieve a secret from environment variables.

    Args:
        secret_name: Name of the environment variable
        default: Optional default value if not found

    Returns:
        The secret value

    Raises:
        SecurityError: If the secret is not found and no default is provided
    """
    secret_value = os.environ.get(secret_name)

    if secret_value is None:
        if default is not None:
            return default
        raise SecurityError(f"Required secret not found in environment: {secret_name}")

    return secret_value


def redact_sensitive_data(data: str, patterns: list[str]) -> str:
    """
    Redact sensitive data from a string based on patterns.

    Args:
        data: The data to redact
        patterns: List of regex patterns to match and redact

    Returns:
        Data with sensitive information redacted
    """
    redacted = data
    for pattern in patterns:
        redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


def validate_backup_name(backup_name: str) -> str:
    """
    Validate and sanitize a backup name to prevent directory traversal and injection.

    Args:
        backup_name: The backup name to validate

    Returns:
        Sanitized backup name

    Raises:
        InvalidInputError: If the backup name is invalid
    """
    if not backup_name:
        raise InvalidInputError("Backup name cannot be empty")

    # Remove path separators and parent directory references
    sanitized = backup_name.replace("/", "").replace("\\", "").replace("..", "")

    # Remove null bytes and other dangerous characters
    sanitized = sanitized.replace("\x00", "")

    # Remove control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", sanitized)

    # Ensure backup name is not empty after sanitization
    if not sanitized:
        raise InvalidInputError(
            f"Backup name is invalid after sanitization: {backup_name}"
        )

    return sanitized

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Security Utilities - Security hardening functions for devin-orchestrator

Provides:
- Path validation and traversal protection
- Input sanitization
- File permission checks
- Secrets management helpers
"""

import os
import re
import stat
from pathlib import Path
from typing import Optional, List, Any
import logging

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


def validate_path_safe(base_path: Path, target_path: Path, allow_absolute: bool = False) -> Path:
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
    try:
        # Resolve the target path to its absolute form
        resolved_target = target_path.resolve()
        
        # If not allowing absolute paths, check if target is absolute
        if not allow_absolute and target_path.is_absolute():
            raise PathTraversalError(f"Absolute paths not allowed: {target_path}")
        
        # Resolve base path
        resolved_base = base_path.resolve()
        
        # Check if the resolved target is within the base path
        try:
            resolved_target.relative_to(resolved_base)
        except ValueError:
            raise PathTraversalError(
                f"Path traversal detected: {target_path} resolves to {resolved_target} "
                f"which is outside base directory {resolved_base}"
            )
        
        return resolved_target
        
    except (OSError, RuntimeError) as e:
        raise InvalidInputError(f"Invalid path {target_path}: {e}")


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to prevent directory traversal and other attacks.
    
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
    
    # Remove path separators and parent directory references
    sanitized = filename.replace('/', '').replace('\\', '').replace('..', '')
    
    # Remove null bytes and other dangerous characters
    sanitized = sanitized.replace('\x00', '')
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    # Ensure filename is not empty after sanitization
    if not sanitized:
        raise InvalidInputError(f"Filename is invalid after sanitization: {filename}")
    
    return sanitized


def sanitize_string(input_string: str, max_length: int = 10000, 
                   allowed_chars: Optional[str] = None) -> str:
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
    sanitized = input_string.replace('\x00', '')
    
    # If allowed_chars pattern is provided, validate against it
    if allowed_chars:
        if not re.match(f'^[{allowed_chars}]*$', sanitized):
            raise InvalidInputError(f"Input contains invalid characters")
    
    return sanitized


def check_file_permissions(file_path: Path, 
                          required_read: bool = True,
                          required_write: bool = False,
                          required_execute: bool = False) -> bool:
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
        if required_read:
            if not (mode & stat.S_IRUSR):  # Owner read
                return False
        
        # Check write permission
        if required_write:
            if not (mode & stat.S_IWUSR):  # Owner write
                return False
        
        # Check execute permission
        if required_execute:
            if not (mode & stat.S_IXUSR):  # Owner execute
                return False
        
        return True
        
    except OSError as e:
        logger.warning(f"Error checking file permissions for {file_path}: {e}")
        return False


def check_directory_permissions(dir_path: Path,
                                required_read: bool = True,
                                required_write: bool = False,
                                required_execute: bool = True) -> bool:
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
        if required_read:
            if not (mode & stat.S_IRUSR):
                return False
        
        # Check write permission
        if required_write:
            if not (mode & stat.S_IWUSR):
                return False
        
        # Check execute permission (required for directory traversal)
        if required_execute:
            if not (mode & stat.S_IXUSR):
                return False
        
        return True
        
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
    
    # Sanitize the session ID
    sanitized = sanitize_filename(session_id, max_length=100)
    
    # Ensure it contains only safe characters (alphanumeric, hyphen, underscore)
    if not re.match(r'^[a-zA-Z0-9_-]+$', sanitized):
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
    
    # Sanitize the skill name
    sanitized = sanitize_filename(skill_name, max_length=100)
    
    # Ensure it contains only safe characters (alphanumeric, hyphen)
    if not re.match(r'^[a-zA-Z0-9-]+$', sanitized):
        raise InvalidInputError(f"Skill name contains invalid characters: {skill_name}")
    
    return sanitized


def validate_workspace_path(workspace: str, base_allowed_dir: Optional[Path] = None) -> Path:
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
    
    workspace_path = Path(workspace)
    
    # If base_allowed_dir is specified, ensure workspace is within it
    if base_allowed_dir:
        return validate_path_safe(base_allowed_dir, workspace_path, allow_absolute=True)
    
    # Otherwise, just resolve and return
    try:
        return workspace_path.resolve()
    except OSError as e:
        raise InvalidInputError(f"Invalid workspace path: {e}")


def get_secret_from_env(secret_name: str, default: Optional[str] = None) -> str:
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


def redact_sensitive_data(data: str, patterns: List[str]) -> str:
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
        redacted = re.sub(pattern, '[REDACTED]', redacted, flags=re.IGNORECASE)
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
    sanitized = backup_name.replace('/', '').replace('\\', '').replace('..', '')
    
    # Remove null bytes and other dangerous characters
    sanitized = sanitized.replace('\x00', '')
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
    
    # Ensure backup name is not empty after sanitization
    if not sanitized:
        raise InvalidInputError(f"Backup name is invalid after sanitization: {backup_name}")
    
    return sanitized
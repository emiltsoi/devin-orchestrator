#!/usr/bin/env python3
"""
Session Manager - Manages session directory creation and resolution

Provides stateless session management for the orchestrator:
- create_session: Generate sequential session IDs based on a format pattern
- resolve_session: Locate an existing session directory
"""

import contextlib
import logging
import re
from pathlib import Path

from security_utils import InvalidInputError, validate_path_safe, validate_session_id

logger = logging.getLogger(__name__)


def create_session(work_dir: Path, session_format: str) -> tuple[str, Path]:
    """
    Create a new session directory with a sequential ID based on the format pattern.

    Args:
        work_dir: Base work directory where sessions are created
        session_format: Format string like "SUPERPOWER-NNN" where N represents digits

    Returns:
        Tuple of (session_id, session_dir) for the created session

    Raises:
        InvalidInputError: If the format is invalid or session creation fails
        PathTraversalError: If path validation fails
    """
    # Parse the format string to extract prefix and numeric width
    # Format: "PREFIX-NNN" where N is the digit placeholder
    match = re.match(r"^([A-Za-z0-9_-]+)-([N]+)$", session_format)
    if not match:
        raise InvalidInputError(f"Invalid session format: {session_format}. Expected format: PREFIX-NNN")

    prefix = match.group(1)
    num_width = len(match.group(2))

    # Validate the prefix contains only safe characters
    if not re.match(r"^[a-zA-Z0-9_-]+$", prefix):
        raise InvalidInputError(f"Invalid prefix in session format: {prefix}")

    # Atomically claim a session directory. Start from the next available
    # number based on a scan, then retry with incrementing candidates using
    # an exclusive mkdir. This avoids a TOCTOU race where two concurrent
    # callers both pick the same number and both succeed with exist_ok=True.
    start_number = _find_next_available_number(work_dir, prefix, num_width)

    session_dir = None
    session_id = None
    number = start_number
    while True:
        candidate_id = f"{prefix}-{number:0{num_width}d}"
        # Validate the generated session ID
        candidate_id = validate_session_id(candidate_id)
        candidate_dir = work_dir / candidate_id
        try:
            # exist_ok=False makes creation atomic and exclusive: only one
            # caller can win the race for a given number.
            candidate_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            # Lost the race for this number; try the next one.
            number += 1
            continue
        except OSError as e:
            # Clean up partially created directory if creation failed
            if candidate_dir.exists():
                with contextlib.suppress(OSError):
                    candidate_dir.rmdir()
            raise InvalidInputError(
                f"Failed to create session directory {candidate_dir}: {e}"
            ) from e
        session_id = candidate_id
        session_dir = candidate_dir
        logger.info(f"Created session directory: {session_dir}")
        break

    return session_id, session_dir


def _find_next_available_number(work_dir: Path, prefix: str, num_width: int) -> int:
    """
    Scan existing directories to find the next available sequential number.

    Args:
        work_dir: Base work directory to scan
        prefix: Session ID prefix (e.g., "SUPERPOWER")
        num_width: Number of digits for the numeric portion

    Returns:
        Next available number (starting from 1 if no existing sessions)
    """
    if not work_dir.exists():
        return 1

    # Pattern to match existing session directories
    pattern = re.compile(rf"^{prefix}-([0-9]{{{num_width}}})$")

    existing_numbers = []
    for entry in work_dir.iterdir():
        if entry.is_dir():
            match = pattern.match(entry.name)
            if match:
                number = int(match.group(1))
                existing_numbers.append(number)

    if not existing_numbers:
        return 1

    # Find the next available number
    max_number = max(existing_numbers)
    return max_number + 1


def resolve_session(work_dir: Path, session_id: str) -> Path:
    """
    Resolve an existing session directory path.

    Args:
        work_dir: Base work directory where sessions are located
        session_id: Session ID to resolve

    Returns:
        Path to the session directory

    Raises:
        InvalidInputError: If the session ID is invalid
        PathTraversalError: If path validation fails
        FileNotFoundError: If the session directory does not exist
    """
    # Validate session ID
    session_id = validate_session_id(session_id)

    # Build the session directory path
    session_dir = work_dir / session_id

    # Validate the path is safe and within work_dir
    session_dir = validate_path_safe(work_dir, session_dir, allow_absolute=False)

    # Check if the session directory exists
    if not session_dir.exists():
        raise FileNotFoundError(f"Session directory not found: {session_dir}")

    if not session_dir.is_dir():
        raise InvalidInputError(f"Session path is not a directory: {session_dir}")

    return session_dir

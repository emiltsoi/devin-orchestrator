#!/usr/bin/env python3
"""
Prompt Builder - Builds prompt files for sessions

Provides utilities for writing prompt files with user requests and context.
"""

import logging
from pathlib import Path

from security_utils import InvalidInputError

logger = logging.getLogger(__name__)


def write_request_prompt(
    session_dir: Path,
    request: str,
    role: str | None = None,
    context_blocks: list[str] | None = None,
) -> Path:
    """
    Write a prompt.md file in the session directory with the user request.

    Args:
        session_dir: Session directory where the prompt file will be written
        request: The user request to include in the prompt
        role: Optional role name to include in the prompt
        context_blocks: Optional list of context blocks to prepend to the request

    Returns:
        Path to the written prompt file

    Raises:
        InvalidInputError: If inputs are invalid
        PathTraversalError: If path validation fails
    """
    # Validate session_dir is a valid directory
    if not session_dir.exists():
        raise InvalidInputError(f"Session directory does not exist: {session_dir}")
    if not session_dir.is_dir():
        raise InvalidInputError(f"Session path is not a directory: {session_dir}")

    # Validate request is not empty
    if not request or not request.strip():
        raise InvalidInputError("Request cannot be empty")

    # Build the prompt content
    prompt_parts = []

    # Add role if provided
    if role:
        prompt_parts.append(f"# Role\n{role}\n")

    # Add context blocks if provided
    if context_blocks:
        prompt_parts.append("# Context\n")
        for block in context_blocks:
            prompt_parts.append(f"{block}\n")

    # Add the user request
    prompt_parts.append("# Request\n")
    prompt_parts.append(request)

    # Join all parts
    prompt_content = "\n".join(prompt_parts)

    # Write the prompt file
    prompt_file = session_dir / "prompt.md"
    try:
        prompt_file.write_text(prompt_content, encoding="utf-8")
        logger.info(f"Wrote prompt file: {prompt_file}")
    except OSError as e:
        raise InvalidInputError(f"Failed to write prompt file {prompt_file}: {e}") from e

    return prompt_file

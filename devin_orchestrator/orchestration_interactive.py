#!/usr/bin/env python3
# mypy: disable-error-code="attr-defined"
"""Interactive pause handling for the OrchestrationEngine."""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
)
from devin_orchestrator.triage_evaluator import TriageDecision

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class OrchestrationInteractiveMixin:
    """Mixin for interactive pause and user-input handling."""

    def _handle_interactive_pause(
        self, stage_name: str, skill_name: str, session_dir: Path
    ) -> dict[str, Any] | None:
        """
        Create a pause file for interactive input and wait for user modification.

        Args:
            stage_name: Name of the stage
            skill_name: Name of the skill being invoked
            session_dir: Session directory

        Returns:
            Error dict if pause file creation fails, None on success
        """
        try:
            pause_file = self._validate_artifact_path(
                f"pause-{stage_name}.md", session_dir
            )
            pause_file.write_text(f"""# Interactive Pause: {stage_name}

The workflow is paused for interactive input.

## Context
Stage: {stage_name}
Skill: {skill_name}

## Instructions
Review the current state and provide any input or feedback needed before proceeding.

## Input Format
```
input: [your input here]
```

Edit this file with your input, then save to continue.
""")
            logger.info(f"Created pause file for interactive mode: {pause_file}")
        except PermissionError as e:
            logger.error(f"Permission error creating pause file: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"Permission error creating pause file: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"Permission error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }
        except (OSError, InvalidInputError, PathTraversalError) as e:
            logger.error(f"IO error creating pause file: {e}")
            return {
                "stage": stage_name,
                "skill": skill_name,
                "success": False,
                "output": None,
                "error": f"IO error creating pause file: {str(e)}",
                "validation": {
                    "valid": False,
                    "errors": [f"IO error: {str(e)}"],
                    "artifact_results": {},
                },
                "triage_decision": TriageDecision.ESCALATE,
            }

        # Wait for pause file to be modified
        self._wait_for_pause_input(pause_file, stage_name, session_dir)
        return None

    def _wait_for_pause_input(
        self, pause_file: Path, stage_name: str, session_dir: Path
    ) -> None:
        """
        Wait for the pause file to be modified with user input.

        Uses filesystem events instead of polling.

        Args:
            pause_file: Path to the pause file
            stage_name: Name of the stage
            session_dir: Session directory
        """
        try:
            max_wait_seconds = self.config.get("pause_timeout_seconds", 3600)
            deadline = time.time() + max_wait_seconds
            initial_content = pause_file.read_text(encoding="utf-8")

            # If the file already contains a valid input, use it immediately.
            initial_input = self._extract_user_input(initial_content)
            if initial_input is not None:
                self.update_status(
                    session_dir,
                    stage_name,
                    "paused",
                    f"User input received: {initial_input[:50]}...",
                )
                return

            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break

                # Block until the pause file changes or the timeout expires.
                if not self.wait_for_file_change(pause_file, timeout=remaining):
                    break

                current_content = pause_file.read_text(encoding="utf-8")
                if current_content != initial_content:
                    # Use structured extraction with regex for robust parsing
                    user_input = self._extract_user_input(current_content)

                    if user_input is not None:
                        # Input found and successfully parsed
                        self.update_status(
                            session_dir,
                            stage_name,
                            "paused",
                            f"User input received: {user_input[:50]}...",
                        )
                        break
                    # If user_input is None, no valid input found yet, continue waiting

            if time.time() >= deadline:
                self.update_status(
                    session_dir,
                    stage_name,
                    "timeout",
                    f"Interactive pause timeout after {max_wait_seconds} seconds",
                )
        except PermissionError as e:
            logger.error(f"Permission error reading pause file: {e}")
            self.update_status(
                session_dir,
                stage_name,
                "error",
                f"Permission error reading pause file: {str(e)}",
            )
        except OSError as e:
            logger.error(f"IO error reading pause file: {e}")
            self.update_status(
                session_dir,
                stage_name,
                "error",
                f"IO error reading pause file: {str(e)}",
            )

    def _extract_user_input(self, content: str) -> str | None:
        """
        Extract user input from pause file content using structured parsing.

        Args:
            content: The pause file content

        Returns:
            Extracted user input, or None if no valid input found
        """
        # Try multiple patterns to extract input, in order of preference
        patterns = [
            # Pattern 1: "input: value" on its own line
            r"^input:\s*(.+)$",
            # Pattern 2: "input: value" anywhere in content (take first match)
            r"input:\s*(.+)",
            # Pattern 3: Markdown code block format
            r"```\s*input:\s*(.+?)\s*```",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                user_input = match.group(1).strip()
                # Validate that we got non-empty input
                if user_input:
                    return user_input

        # No valid input found
        return None

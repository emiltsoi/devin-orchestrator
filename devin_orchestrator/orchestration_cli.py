#!/usr/bin/env python3
"""Command-line entry point for the orchestration engine."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, NoReturn

from devin_orchestrator.config_loader import ConfigLoader
from devin_orchestrator.orchestration_engine import OrchestrationEngine
from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
)

logger = logging.getLogger(__name__)


def _print_cli_error(
    message: str, error_type: str, details: str | None = None
) -> NoReturn:
    """Print a CLI error as JSON and exit with code 1."""
    error_data: dict[str, Any] = {"error": message, "error_type": error_type}
    if details is not None:
        error_data["details"] = details
    print(json.dumps(error_data, indent=2))
    sys.exit(1)


def _parse_cli_args() -> tuple:
    """Parse and validate CLI arguments, exiting on usage error."""
    if len(sys.argv) < 4:
        print(
            "Usage: orchestration_engine.py <manifest_path> <session_id> "
            "<request_content> [skip_brainstorming]"
        )
        sys.exit(1)

    manifest_path = Path(sys.argv[1])
    session_id = sys.argv[2]
    request_content = sys.argv[3]
    skip_brainstorming = len(sys.argv) > 4 and sys.argv[4].lower() == "true"
    return manifest_path, session_id, request_content, skip_brainstorming


def _load_cli_config() -> tuple:
    """Load CLI configuration, exiting on error.

    Returns (config, work_dir) on success.
    """
    try:
        config = ConfigLoader.load()
        work_dir = Path(config.session_work_dir)
        logger.info(f"Loaded config, work_dir: {work_dir}")
        return config, work_dir
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        _print_cli_error("Configuration file not found", "FileNotFoundError", str(e))
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        _print_cli_error(
            "Invalid JSON in configuration file", "JSONDecodeError", str(e)
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        InvalidInputError,
        PathTraversalError,
    ) as e:
        logger.error(f"Error loading configuration: {e}")
        _print_cli_error("Error loading configuration", type(e).__name__, str(e))


def _create_cli_engine(work_dir: Path, config: Any) -> OrchestrationEngine:
    """Create orchestration engine, exiting on error."""
    try:
        return OrchestrationEngine(work_dir, config.__dict__)
    except (
        OSError,
        RuntimeError,
        ValueError,
        InvalidInputError,
        PathTraversalError,
    ) as e:
        logger.error(f"Error initializing orchestration engine: {e}")
        _print_cli_error(
            "Error initializing orchestration engine", type(e).__name__, str(e)
        )


def _run_cli_workflow(
    engine: OrchestrationEngine,
    manifest_path: Path,
    session_id: str,
    request_content: str,
    skip_brainstorming: bool,
) -> None:
    """Execute workflow and print results, exiting on error."""
    try:
        results = engine.execute_workflow(
            manifest_path, session_id, request_content, skip_brainstorming
        )
        print(json.dumps(results, indent=2, default=str))
    except (
        OSError,
        RuntimeError,
        ValueError,
        InvalidInputError,
        PathTraversalError,
    ) as e:
        logger.error(f"Error executing workflow: {e}")
        _print_cli_error("Error executing workflow", type(e).__name__, str(e))


def main():
    """CLI entry point for orchestration engine"""
    try:
        manifest_path, session_id, request_content, skip_brainstorming = (
            _parse_cli_args()
        )

        config, work_dir = _load_cli_config()

        engine = _create_cli_engine(work_dir, config)

        _run_cli_workflow(
            engine, manifest_path, session_id, request_content, skip_brainstorming
        )
    except KeyboardInterrupt:
        logger.info("Workflow execution interrupted by user")
        print(
            json.dumps(
                {
                    "error": "Workflow execution interrupted",
                    "error_type": "KeyboardInterrupt",
                },
                indent=2,
            )
        )
        sys.exit(130)
    except (
        OSError,
        RuntimeError,
        ValueError,
        InvalidInputError,
        PathTraversalError,
    ) as e:
        logger.error(f"Error in main: {e}")
        print(
            json.dumps(
                {
                    "error": "Error",
                    "error_type": type(e).__name__,
                    "details": str(e),
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

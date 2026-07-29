#!/usr/bin/env python3
"""
MCP call and dispatch artifact logging.

Provides a lightweight, append-only trace log for every MCP tool call and a
helper to capture the command, stdout, stderr, and result of a dispatched
worker into a session directory.  These artifacts are intended for replay and
troubleshooting.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess  # nosec B404
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from devin_orchestrator.session_manager import resolve_session

logger = logging.getLogger(__name__)


class McpCallLogger:
    """
    Append-only JSONL logger for MCP tool calls.

    Writes every call to a server-level log (default
    ``~/.devin-orchestrator/logs/mcp-calls.jsonl``) and, when a session_id is
    known, appends a copy to ``<session_dir>/mcp-calls.jsonl`` for localized
    debugging.
    """

    DEFAULT_LOG_DIR = Path.home() / ".devin-orchestrator" / "logs"

    def __init__(self, log_path: str | Path | None = None) -> None:
        if log_path is None:
            log_path = self.DEFAULT_LOG_DIR / "mcp-calls.jsonl"
        self.log_path = Path(log_path).expanduser()
        self._log_file: IO[str] | None = None
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_file = open(  # noqa: SIM115
                self.log_path, "a", encoding="utf-8", buffering=1
            )
        except (OSError, ValueError) as e:
            logger.warning("Cannot open MCP call log %s: %s", self.log_path, e)

    def log_call(self, record: dict[str, Any]) -> None:
        """Write one record to the server-level MCP call log."""
        if self._log_file is None:
            return
        try:
            if "timestamp" not in record:
                record["timestamp"] = datetime.now(timezone.utc).isoformat()
            self._log_file.write(json.dumps(record, default=str) + "\n")
        except (OSError, TypeError) as e:
            logger.warning("Failed to write MCP call log: %s", e)

    def append_session_call(
        self, session_work_dir: Path, session_id: str, record: dict[str, Any]
    ) -> None:
        """Append a copy of the call record to a session directory."""
        try:
            session_dir = resolve_session(session_work_dir, session_id)
            session_log = session_dir / "mcp-calls.jsonl"
            with open(session_log, "a", encoding="utf-8", buffering=1) as f:
                if "timestamp" not in record:
                    record["timestamp"] = datetime.now(timezone.utc).isoformat()
                f.write(json.dumps(record, default=str) + "\n")
        except (OSError, ValueError, FileNotFoundError) as e:
            logger.debug(
                "Could not write session call log for %s: %s", session_id, e
            )

    def close(self) -> None:
        """Close the underlying log file handle."""
        if self._log_file is not None:
            with contextlib.suppress(OSError):
                self._log_file.close()
            self._log_file = None


class SubprocessArtifactRunner:
    """
    Run a subprocess in the background and persist replayable artifacts.

    Artifacts written to ``session_dir``:
      - ``cmd.json``: the command, working directory, and timeout
      - ``stdout.txt``: captured stdout
      - ``stderr.txt``: captured stderr
      - ``result.json``: exit_code, success, output, error, duration
    """

    @staticmethod
    def run(
        session_dir: Path,
        cmd: list[str | Path],
        work_dir: Path | None = None,
        timeout: int = 300,
    ) -> None:
        """Run ``cmd`` and capture stdout/stderr to ``session_dir``."""
        try:
            (session_dir / "cmd.json").write_text(
                json.dumps(
                    {
                        "cmd": [str(c) for c in cmd],
                        "cwd": str(work_dir) if work_dir else None,
                        "timeout": timeout,
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except (OSError, ValueError) as e:
            logger.warning("Could not write cmd.json for %s: %s", session_dir, e)

        start = time.time()
        try:
            result = subprocess.run(  # nosec B603
                [str(c) for c in cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(work_dir) if work_dir else None,
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
            run_error = None
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            stderr = e.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            stderr += f"\n\nTimed out after {timeout} seconds"
            exit_code = -1
            run_error = f"Timeout after {timeout} seconds"
        except (OSError, ValueError) as e:
            stdout = ""
            stderr = f"Failed to run dispatch: {e}"
            exit_code = -1
            run_error = str(e)

        try:
            (session_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
            (session_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
            result_data: dict[str, Any] = {
                "exit_code": exit_code,
                "success": exit_code == 0,
                "output": stdout,
                "error": run_error or (stderr if stderr else None),
                "duration_seconds": round(time.time() - start, 3),
            }
            (session_dir / "result.json").write_text(
                json.dumps(result_data, indent=2, default=str), encoding="utf-8"
            )
        except (OSError, ValueError) as e:
            logger.warning("Could not write result artifacts for %s: %s", session_dir, e)

        # Best-effort update of session.json status
        try:
            session_file = session_dir / "session.json"
            data: dict[str, Any] = {}
            if session_file.exists():
                data = json.loads(session_file.read_text(encoding="utf-8"))
            data["status"] = "completed" if exit_code == 0 else "failed"
            data["duration_seconds"] = round(time.time() - start, 3)
            data["exit_code"] = exit_code
            session_file.write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )
        except (OSError, ValueError, json.JSONDecodeError) as e:
            logger.warning(
                "Could not update session.json for %s: %s", session_dir, e
            )

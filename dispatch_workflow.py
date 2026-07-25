#!/usr/bin/env python3
"""
Background dispatcher for devin-orchestrator workflows/skills.

This script is spawned by mcp_server.py for long-running operations so the
MCP server process stays responsive to cancellation and status requests.
It reads its arguments from a JSON file written by mcp_server.py and writes
a ready file as soon as the session is established.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any


def _setup_import_path() -> None:
    """Make the adjacent workflow-engine package importable."""
    script_dir = Path(__file__).resolve().parent
    engine_dir = script_dir / "workflow-engine"
    if engine_dir.exists() and str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))


_setup_import_path()

from stateless_orchestrator import StatelessOrchestrator  # noqa: E402

logger = logging.getLogger("dispatch_workflow")


def _write_ready(ready_file: Path, session_id: str, workspace: Path) -> None:
    """Write the ready file so the caller can return immediately."""
    try:
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "workspace": str(workspace),
                    "ready": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"Failed to write ready file {ready_file}: {e}")


def _write_pid_file(session_dir: Path) -> Path:
    """Write this dispatcher's PID so cancel_workflow can kill the whole tree."""
    pid_file = session_dir / "workflow-pid.txt"
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(
            json.dumps({"pid": os.getpid(), "create_time": time.time()}),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"Failed to write workflow pid file {pid_file}: {e}")
    return pid_file


def _cleanup_pid_file(pid_file: Path) -> None:
    """Best-effort removal of the workflow PID file."""
    try:
        if pid_file.exists():
            pid_file.unlink()
    except OSError as e:
        logger.warning(f"Failed to remove workflow pid file {pid_file}: {e}")


def _make_ready_callback(ready_file: Path) -> Any:
    """Return a callback that writes the ready file and PID file once the session is known."""
    pid_file: Path | None = None

    def callback(session_id: str, session_dir: Path) -> None:
        nonlocal pid_file
        _write_ready(ready_file, session_id, session_dir)
        pid_file = _write_pid_file(session_dir)

    return callback


def main() -> int:
    parser = argparse.ArgumentParser(description="Background workflow/skill dispatcher")
    parser.add_argument("--args-file", required=True, help="JSON file containing dispatch arguments")
    parser.add_argument("--ready-file", required=True, help="File to write once the session is ready")
    parsed = parser.parse_args()

    args_file = Path(parsed.args_file)
    try:
        args = json.loads(args_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to read args file {args_file}: {e}")
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    ready_file = Path(parsed.ready_file)
    orchestrator = StatelessOrchestrator(
        workspace=args.get("workspace"),
        demo_mode=args.get("demo_mode", False),
        timeout=args.get("timeout"),
        gate_mode=args.get("gate_mode", "auto"),
    )

    focused_context = args.get("focused_context")
    if not isinstance(focused_context, list):
        focused_context = None

    ready_callback = _make_ready_callback(ready_file)
    session_id: str | None = args.get("session_id")
    result: dict[str, Any] = {}

    try:
        action = args.get("action")
        if action == "execute":
            result = orchestrator.execute(
                request=args.get("request", ""),
                intent=args.get("intent", "auto"),
                focused_context=focused_context,
                output_file=args.get("output_file"),
                ready_callback=ready_callback,
            )
        elif action == "run_workflow":
            result = orchestrator.run_workflow(
                workflow_name=args["workflow"],
                request=args.get("request", ""),
                focused_context=focused_context,
                output_file=args.get("output_file"),
                ready_callback=ready_callback,
            )
        elif action == "run_skill":
            result = orchestrator.run_skill(
                skill_name=args["skill"],
                request=args.get("request", ""),
                focused_context=focused_context,
                output_file=args.get("output_file"),
                ready_callback=ready_callback,
            )
        elif action == "plan":
            result = orchestrator.plan(
                request=args.get("request", ""),
                focused_context=focused_context,
                output_file=args.get("output_file"),
                ready_callback=ready_callback,
            )
        elif action == "continue_workflow":
            result = orchestrator.continue_workflow(
                session_id=args["session_id"],
                gate_verdict=args.get("gate_verdict"),
                gate_notes=args.get("gate_notes"),
                gate_id=args.get("gate_id"),
                correction_artifact=args.get("correction_artifact"),
                feedback=args.get("feedback"),
                focused_context=focused_context,
                output_file=args.get("output_file"),
                ready_callback=ready_callback,
            )
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}

        # Ensure session.json reflects the final result for get_session_status.
        sid = result.get("session_id") or session_id
        workspace = result.get("workspace")
        if sid and workspace:
            session_dir = Path(workspace)
            try:
                session_file = session_dir / "session.json"
                if session_file.exists():
                    session_data = json.loads(session_file.read_text(encoding="utf-8"))
                else:
                    session_data = {}
                # Preserve an explicit cancellation status set by cancel_workflow.
                already_cancelled = (
                    session_data.get("status") == "cancelled"
                    or session_data.get("final_status") == "cancelled"
                    or (session_dir / ".cancel").exists()
                )
                final_status = (
                    "cancelled"
                    if already_cancelled
                    else (
                        "completed"
                        if result.get("success")
                        else (result.get("final_status") or session_data.get("final_status") or "failed")
                    )
                )
                session_data.update(
                    {
                        "session_id": sid,
                        "workspace": str(workspace),
                        "success": result.get("success", False),
                        "final_status": final_status,
                        "status": final_status,
                        "output": result.get("output") or result.get("error"),
                        "error": result.get("error"),
                        "artifact_paths": result.get("artifact_paths", []),
                        "done": result.get("done", result.get("success", False)),
                        "next_step": result.get("next_step"),
                        "resume": result.get("resume"),
                    }
                )
                session_file.write_text(json.dumps(session_data, indent=2, default=str), encoding="utf-8")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to update session.json for {sid}: {e}")

    except Exception as e:
        logger.error(f"Background dispatch failed: {e}\n{traceback.format_exc()}")
        sid = result.get("session_id") or session_id
        if sid:
            session_dir = orchestrator.config.session_work_dir / sid
            try:
                session_dir.mkdir(parents=True, exist_ok=True)
                session_file = session_dir / "session.json"
                session_data = {}
                if session_file.exists():
                    session_data = json.loads(session_file.read_text(encoding="utf-8"))
                # Preserve an explicit cancellation status if the user cancelled.
                if session_data.get("status") != "cancelled" and session_data.get("final_status") != "cancelled":
                    session_data["final_status"] = "failed"
                session_data["error"] = str(e)
                session_data["done"] = True
                session_file.write_text(json.dumps(session_data, indent=2, default=str), encoding="utf-8")
            except (OSError, json.JSONDecodeError):
                pass
        return 1
    finally:
        # Best-effort cleanup of workflow-pid file.
        sid = result.get("session_id") or session_id
        if sid:
            _cleanup_pid_file(orchestrator.config.session_work_dir / sid / "workflow-pid.txt")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""CLI entry point for JSON health reporting."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from devin_orchestrator.health_check import health


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print devin-orchestrator health status as JSON."
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional workflow engine work directory to check sessions",
    )
    args = parser.parse_args()

    report = health(work_dir=args.work_dir)
    print(json.dumps(report, indent=2, default=str))

    if report["overall_status"] == "error":
        return 1
    if report["overall_status"] == "warning":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

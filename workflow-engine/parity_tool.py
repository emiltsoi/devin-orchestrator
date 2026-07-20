"""
Parity Tool - Verifies consistency between audits, run transcripts, and runbooks
"""

import json
import re
from pathlib import Path
from typing import Any

import yaml


def check_audit_run_jsonl_parity(session_dir: Path) -> dict[str, Any]:
    """
    Verify that session-audit.md and run.jsonl contain matching stage records.

    Returns a report with matched, mismatched, and missing entries.
    """
    audit_path = session_dir / "session-audit.md"
    run_jsonl_path = session_dir / "run.jsonl"

    report = {
        "valid": True,
        "errors": [],
        "audit_stages": set(),
        "run_stages": set(),
        "matched": [],
    }

    audit_stages = set()
    if audit_path.exists():
        content = audit_path.read_text(encoding="utf-8")
        for line in content.split("\n"):
            match = re.search(r"## Stage:\s*(\S+)", line)
            if match:
                audit_stages.add(match.group(1))

    run_stages = set()
    if run_jsonl_path.exists():
        for line in run_jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                stage = entry.get("stage")
                if stage:
                    run_stages.add(stage)
            except json.JSONDecodeError as e:
                report["errors"].append(f"Invalid JSON in run.jsonl: {e}")

    report["audit_stages"] = audit_stages
    report["run_stages"] = run_stages

    missing_in_run = audit_stages - run_stages
    missing_in_audit = run_stages - audit_stages

    if missing_in_run:
        report["valid"] = False
        report["errors"].append(
            f"Stages in audit but not run.jsonl: {sorted(missing_in_run)}"
        )

    if missing_in_audit:
        report["valid"] = False
        report["errors"].append(
            f"Stages in run.jsonl but not audit: {sorted(missing_in_audit)}"
        )

    report["matched"] = sorted(audit_stages & run_stages)
    return report


def check_manifest_runbook_parity(workflows_dir: Path) -> dict[str, Any]:
    """
    Verify that each workflow manifest has a corresponding runbook with matching
    stage sequence.
    """
    report = {"valid": True, "errors": [], "checked": [], "missing_runbooks": []}

    if not workflows_dir.exists():
        report["valid"] = False
        report["errors"].append(f"Workflows directory not found: {workflows_dir}")
        return report

    manifests = list(workflows_dir.glob("*.manifest.yaml"))
    if not manifests:
        report["errors"].append("No manifest files found to check")
        return report

    for manifest_path in manifests:
        runbook_path = manifest_path.with_suffix("").with_suffix(".runbook.md")
        if not runbook_path.exists():
            expected_name = runbook_path.name
            report["missing_runbooks"].append(expected_name)
            report["valid"] = False
            report["errors"].append(
                f"Missing runbook for {manifest_path.name}: expected {expected_name}"
            )
            continue

        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        runbook = runbook_path.read_text(encoding="utf-8")

        def _normalize(name: str) -> str:
            """Normalize a stage name for comparison"""
            name = name.lower()
            name = re.sub(r"\s*\([^)]*\)", "", name)  # remove parenthetical text
            name = name.replace("_", "-")  # normalize underscores to hyphens
            name = re.sub(r"[^a-z0-9\-]+", "-", name)  # replace spaces/punctuation with hyphens
            return name.strip("-")

        manifest_stages = [s["name"] for s in manifest.get("stages", [])]
        # Match runbook stage markers and capture the heading text after the marker.
        # Supports forms like "### Stage 0: Brainstorming (Optional)", "Stage: brainstorming"
        runbook_stage_matches = re.findall(
            r"(?:^|\n)\s*(?:###?\s+Stage\s+\d*[:\-]?\s+|\*\*Stage\s*[:\-]?\s*|Stage\s*[:\-]\s*)(.+?)(?:\n|\(|$)",
            runbook,
            re.MULTILINE | re.IGNORECASE,
        )

        runbook_stage_set = {_normalize(s) for s in runbook_stage_matches}
        manifest_stage_set = {_normalize(s) for s in manifest_stages}

        missing_in_runbook = manifest_stage_set - runbook_stage_set
        if missing_in_runbook:
            report["valid"] = False
            report["errors"].append(
                f"{manifest_path.name}: stages missing in runbook {runbook_path.name}: {sorted(missing_in_runbook)}"
            )

        report["checked"].append(
            {
                "manifest": manifest_path.name,
                "runbook": runbook_path.name,
                "manifest_stages": manifest_stages,
                "runbook_stages": runbook_stage_matches,
            }
        )

    return report


def main() -> int:
    """CLI entry point for parity checks"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: parity_tool.py <session_dir|workflows_dir>")
        return 1

    target = Path(sys.argv[1])

    if (target / "session-audit.md").exists() or (target / "run.jsonl").exists():
        report = check_audit_run_jsonl_parity(target)
    else:
        report = check_manifest_runbook_parity(target)

    print(json.dumps(report, indent=2, default=str))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

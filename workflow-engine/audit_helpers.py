# -*- coding: utf-8 -*-
"""
Audit Helpers - Deterministic helper modules for audit ledger, gate recording, and run.jsonl
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import threading

# Thread-safe locks for file operations
_audit_lock = threading.Lock()
_gate_lock = threading.Lock()
_run_jsonl_lock = threading.Lock()


def append_audit(
    session_dir: Path,
    stage: str,
    skill: str,
    injected_context: List[str],
    structural_result: str,
    reviewer_verdict: str,
    confidence: str,
    rationale: str,
    triage_decision: str,
    retry_count: int,
    gate_verdict: str
) -> None:
    """
    Appends structured entry to session-audit.md

    Args:
        session_dir: Path to session directory
        stage: Current stage (e.g., "step_1")
        skill: Skill name (e.g., "brainstorming")
        injected_context: List of artifact names injected into worker dispatch
        structural_result: "PASS" or "FAIL"
        reviewer_verdict: "PASS", "FAIL", or detailed verdict
        confidence: "HIGH", "MEDIUM", or "LOW"
        rationale: Cascade reasoning for the decision
        triage_decision: "proceed", "correct", or "escalate"
        retry_count: Number of retry attempts for this stage
        gate_verdict: "approved", "rejected", or "none"
    """
    audit_path = session_dir / 'session-audit.md'
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build human-readable markdown entry
    entry = f"""
## Stage: {stage}
- Timestamp: {timestamp}
- Skill: {skill}
- Injected Context: {', '.join(injected_context) if injected_context else 'none'}
- Structural Result: {structural_result}
- Reviewer Verdict: {reviewer_verdict}
- Confidence: {confidence}
- Rationale: {rationale}
- Triage Decision: {triage_decision}
- Retry Count: {retry_count}
- Gate Verdict: {gate_verdict}
"""

    # Thread-safe append operation
    with _audit_lock:
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(entry)


def record_gate(session_dir: Path, gate_id: str, verdict: str) -> None:
    """
    Records gate verdict to session-audit.md

    Args:
        session_dir: Path to session directory
        gate_id: Gate identifier (e.g., "g1_requirement_approval")
        verdict: "approved" or "rejected"
    """
    audit_path = session_dir / 'session-audit.md'
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build gate record entry
    entry = f"""
## Gate Decision: {gate_id}
- Timestamp: {timestamp}
- Gate ID: {gate_id}
- Verdict: {verdict}
"""

    # Thread-safe append operation
    with _gate_lock:
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(entry)


def write_run_jsonl(session_dir: Path, entry: Dict[str, Any]) -> None:
    """
    Appends machine-readable entry to run.jsonl

    Args:
        session_dir: Path to session directory
        entry: Dictionary with keys:
            - timestamp: ISO8601 timestamp
            - session_id: Session identifier
            - stage: Current stage (e.g., "step_1")
            - skill: Skill name
            - injected_context: List of artifact names
            - structural_result: "PASS" or "FAIL"
            - reviewer_verdict: "PASS", "FAIL", or details
            - confidence: "HIGH", "MEDIUM", or "LOW"
            - rationale: Cascade reasoning
            - triage_decision: "proceed", "correct", or "escalate"
            - retry_count: Number of retry attempts
            - gate_verdict: "approved", "rejected", or "none"
    """
    run_jsonl_path = session_dir / 'run.jsonl'

    # Validate entry has required fields
    required_fields = [
        'timestamp', 'session_id', 'stage', 'skill', 'injected_context',
        'structural_result', 'reviewer_verdict', 'confidence', 'rationale',
        'triage_decision', 'retry_count', 'gate_verdict'
    ]

    for field in required_fields:
        if field not in entry:
            raise ValueError(f"Missing required field: {field}")

    # Thread-safe append operation
    with _run_jsonl_lock:
        with open(run_jsonl_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

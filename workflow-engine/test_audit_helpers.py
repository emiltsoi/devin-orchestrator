#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for audit_helpers.py
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone
from workflow_engine.audit_helpers import (
    append_audit,
    record_gate,
    write_run_jsonl
)


class TestAppendAudit:
    """Tests for append_audit function"""
    
    def test_append_audit_creates_file(self):
        """Test that append_audit creates the audit file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            append_audit(
                session_dir=session_dir,
                stage="step_1",
                skill="brainstorming",
                injected_context=["design.md"],
                structural_result="PASS",
                reviewer_verdict="PASS",
                confidence="HIGH",
                rationale="Good design",
                triage_decision="proceed",
                retry_count=0,
                gate_verdict="none"
            )
            
            audit_path = session_dir / 'session-audit.md'
            assert audit_path.exists()
    
    def test_append_audit_content(self):
        """Test that append_audit writes correct content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            append_audit(
                session_dir=session_dir,
                stage="step_1",
                skill="brainstorming",
                injected_context=["design.md"],
                structural_result="PASS",
                reviewer_verdict="PASS",
                confidence="HIGH",
                rationale="Good design",
                triage_decision="proceed",
                retry_count=0,
                gate_verdict="none"
            )
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            assert "## Stage: step_1" in content
            assert "Skill: brainstorming" in content
            assert "Injected Context: design.md" in content
            assert "Structural Result: PASS" in content
            assert "Confidence: HIGH" in content
            assert "Triage Decision: proceed" in content
    
    def test_append_audit_multiple_entries(self):
        """Test that multiple audit entries are appended"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            append_audit(
                session_dir=session_dir,
                stage="step_1",
                skill="brainstorming",
                injected_context=[],
                structural_result="PASS",
                reviewer_verdict="PASS",
                confidence="HIGH",
                rationale="Good",
                triage_decision="proceed",
                retry_count=0,
                gate_verdict="none"
            )
            
            append_audit(
                session_dir=session_dir,
                stage="step_2",
                skill="writing-plans",
                injected_context=["design.md"],
                structural_result="PASS",
                reviewer_verdict="PASS",
                confidence="HIGH",
                rationale="Good",
                triage_decision="proceed",
                retry_count=0,
                gate_verdict="none"
            )
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            assert content.count("## Stage:") == 2
            assert "step_1" in content
            assert "step_2" in content
    
    def test_append_audit_empty_context(self):
        """Test that empty injected context is handled correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            append_audit(
                session_dir=session_dir,
                stage="step_1",
                skill="brainstorming",
                injected_context=[],
                structural_result="PASS",
                reviewer_verdict="PASS",
                confidence="HIGH",
                rationale="Good",
                triage_decision="proceed",
                retry_count=0,
                gate_verdict="none"
            )
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            assert "Injected Context: none" in content


class TestRecordGate:
    """Tests for record_gate function"""
    
    def test_record_gate_creates_file(self):
        """Test that record_gate creates the audit file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            record_gate(
                session_dir=session_dir,
                gate_id="g1_design_approval",
                verdict="approved"
            )
            
            audit_path = session_dir / 'session-audit.md'
            assert audit_path.exists()
    
    def test_record_gate_content(self):
        """Test that record_gate writes correct content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            record_gate(
                session_dir=session_dir,
                gate_id="g1_design_approval",
                verdict="approved"
            )
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            assert "## Gate Decision: g1_design_approval" in content
            assert "Gate ID: g1_design_approval" in content
            assert "Verdict: approved" in content
    
    def test_record_gate_rejected(self):
        """Test that rejected verdict is recorded correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            record_gate(
                session_dir=session_dir,
                gate_id="g1_design_approval",
                verdict="rejected"
            )
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            assert "Verdict: rejected" in content
    
    def test_record_gate_multiple_entries(self):
        """Test that multiple gate records are appended"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            record_gate(
                session_dir=session_dir,
                gate_id="g1_design_approval",
                verdict="approved"
            )
            
            record_gate(
                session_dir=session_dir,
                gate_id="g2_plan_approval",
                verdict="approved"
            )
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            assert content.count("## Gate Decision:") == 2
            assert "g1_design_approval" in content
            assert "g2_plan_approval" in content


class TestWriteRunJsonl:
    """Tests for write_run_jsonl function"""
    
    def test_write_run_jsonl_creates_file(self):
        """Test that write_run_jsonl creates the run.jsonl file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': 'TEST-001',
                'stage': 'step_1',
                'skill': 'brainstorming',
                'injected_context': ['design.md'],
                'structural_result': 'PASS',
                'reviewer_verdict': 'PASS',
                'confidence': 'HIGH',
                'rationale': 'Good design',
                'triage_decision': 'proceed',
                'retry_count': 0,
                'gate_verdict': 'none'
            }
            
            write_run_jsonl(session_dir, entry)
            
            run_jsonl_path = session_dir / 'run.jsonl'
            assert run_jsonl_path.exists()
    
    def test_write_run_jsonl_content(self):
        """Test that write_run_jsonl writes valid JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': 'TEST-001',
                'stage': 'step_1',
                'skill': 'brainstorming',
                'injected_context': ['design.md'],
                'structural_result': 'PASS',
                'reviewer_verdict': 'PASS',
                'confidence': 'HIGH',
                'rationale': 'Good design',
                'triage_decision': 'proceed',
                'retry_count': 0,
                'gate_verdict': 'none'
            }
            
            write_run_jsonl(session_dir, entry)
            
            run_jsonl_path = session_dir / 'run.jsonl'
            content = run_jsonl_path.read_text()
            
            # Parse the JSON line
            parsed = json.loads(content.strip())
            
            assert parsed['session_id'] == 'TEST-001'
            assert parsed['stage'] == 'step_1'
            assert parsed['skill'] == 'brainstorming'
    
    def test_write_run_jsonl_multiple_entries(self):
        """Test that multiple entries are written as separate lines"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            entry1 = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': 'TEST-001',
                'stage': 'step_1',
                'skill': 'brainstorming',
                'injected_context': [],
                'structural_result': 'PASS',
                'reviewer_verdict': 'PASS',
                'confidence': 'HIGH',
                'rationale': 'Good',
                'triage_decision': 'proceed',
                'retry_count': 0,
                'gate_verdict': 'none'
            }
            
            entry2 = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': 'TEST-001',
                'stage': 'step_2',
                'skill': 'writing-plans',
                'injected_context': ['design.md'],
                'structural_result': 'PASS',
                'reviewer_verdict': 'PASS',
                'confidence': 'HIGH',
                'rationale': 'Good',
                'triage_decision': 'proceed',
                'retry_count': 0,
                'gate_verdict': 'none'
            }
            
            write_run_jsonl(session_dir, entry1)
            write_run_jsonl(session_dir, entry2)
            
            run_jsonl_path = session_dir / 'run.jsonl'
            content = run_jsonl_path.read_text()
            
            lines = content.strip().split('\n')
            assert len(lines) == 2
            
            # Parse both lines
            parsed1 = json.loads(lines[0])
            parsed2 = json.loads(lines[1])
            
            assert parsed1['stage'] == 'step_1'
            assert parsed2['stage'] == 'step_2'
    
    def test_write_run_jsonl_missing_field(self):
        """Test that missing required field raises error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': 'TEST-001',
                # Missing required fields
            }
            
            with pytest.raises(ValueError, match="Missing required field"):
                write_run_jsonl(session_dir, entry)
    
    def test_write_run_jsonl_empty_context(self):
        """Test that empty injected context is handled correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': 'TEST-001',
                'stage': 'step_1',
                'skill': 'brainstorming',
                'injected_context': [],
                'structural_result': 'PASS',
                'reviewer_verdict': 'PASS',
                'confidence': 'HIGH',
                'rationale': 'Good',
                'triage_decision': 'proceed',
                'retry_count': 0,
                'gate_verdict': 'none'
            }
            
            write_run_jsonl(session_dir, entry)
            
            run_jsonl_path = session_dir / 'run.jsonl'
            content = run_jsonl_path.read_text()
            
            parsed = json.loads(content.strip())
            assert parsed['injected_context'] == []


class TestConcurrentWrites:
    """Tests for concurrent write operations"""
    
    def test_concurrent_audit_writes(self):
        """Test that concurrent audit writes don't corrupt data"""
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            def write_audit(i):
                append_audit(
                    session_dir=session_dir,
                    stage=f"step_{i}",
                    skill="test",
                    injected_context=[],
                    structural_result="PASS",
                    reviewer_verdict="PASS",
                    confidence="HIGH",
                    rationale="Test",
                    triage_decision="proceed",
                    retry_count=0,
                    gate_verdict="none"
                )
            
            threads = [threading.Thread(target=write_audit, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            audit_path = session_dir / 'session-audit.md'
            content = audit_path.read_text()
            
            # Should have 10 entries
            assert content.count("## Stage:") == 10
    
    def test_concurrent_jsonl_writes(self):
        """Test that concurrent JSONL writes don't corrupt data"""
        import threading
        
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir)
            
            def write_jsonl(i):
                entry = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'session_id': 'TEST-001',
                    'stage': f'step_{i}',
                    'skill': 'test',
                    'injected_context': [],
                    'structural_result': 'PASS',
                    'reviewer_verdict': 'PASS',
                    'confidence': 'HIGH',
                    'rationale': 'Test',
                    'triage_decision': 'proceed',
                    'retry_count': 0,
                    'gate_verdict': 'none'
                }
                write_run_jsonl(session_dir, entry)
            
            threads = [threading.Thread(target=write_jsonl, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            run_jsonl_path = session_dir / 'run.jsonl'
            content = run_jsonl_path.read_text()
            
            lines = content.strip().split('\n')
            assert len(lines) == 10
            
            # All lines should be valid JSON
            for line in lines:
                json.loads(line)

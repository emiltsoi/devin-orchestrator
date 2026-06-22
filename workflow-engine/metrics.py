#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Metrics Tracking Module

Tracks performance metrics for orchestration system including:
- Stage execution time
- Skill invocation duration
- Retry counts
- Gate decision time
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class StageMetrics:
    """Metrics for a single stage execution"""
    stage_name: str
    skill_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = False
    retry_count: int = 0
    error: Optional[str] = None
    triage_decision: Optional[str] = None


@dataclass
class SkillInvocationMetrics:
    """Metrics for a single skill invocation"""
    skill_name: str
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = False
    error: Optional[str] = None
    is_reviewer: bool = False


@dataclass
class GateMetrics:
    """Metrics for gate decision"""
    gate_id: str
    stage_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    verdict: Optional[str] = None
    blocked: bool = False


@dataclass
class WorkflowMetrics:
    """Metrics for a complete workflow execution"""
    session_id: str
    manifest_name: str
    start_time: float
    end_time: Optional[float] = None
    total_duration: Optional[float] = None
    final_status: Optional[str] = None
    stage_metrics: List[StageMetrics] = field(default_factory=list)
    skill_metrics: List[SkillInvocationMetrics] = field(default_factory=list)
    gate_metrics: List[GateMetrics] = field(default_factory=list)


class MetricsCollector:
    """
    Collects and manages performance metrics for orchestration system
    
    Thread-safe metrics collection with export capabilities
    """
    
    def __init__(self):
        """Initialize metrics collector"""
        self._workflows: Dict[str, WorkflowMetrics] = {}
        self._lock = Lock()
        self._current_workflow: Optional[WorkflowMetrics] = None
        self._current_stage: Optional[StageMetrics] = None
        self._current_skill: Optional[SkillInvocationMetrics] = None
        self._current_gate: Optional[GateMetrics] = None
    
    def start_workflow(self, session_id: str, manifest_name: str) -> WorkflowMetrics:
        """
        Start tracking a new workflow
        
        Args:
            session_id: Unique session identifier
            manifest_name: Name of the workflow manifest
            
        Returns:
            WorkflowMetrics object for this workflow
        """
        with self._lock:
            workflow = WorkflowMetrics(
                session_id=session_id,
                manifest_name=manifest_name,
                start_time=time.time()
            )
            self._workflows[session_id] = workflow
            self._current_workflow = workflow
            logger.info(f"Started tracking workflow: {session_id} ({manifest_name})")
            return workflow
    
    def end_workflow(self, session_id: str, final_status: str) -> Optional[WorkflowMetrics]:
        """
        End tracking for a workflow
        
        Args:
            session_id: Session identifier
            final_status: Final status of the workflow
            
        Returns:
            WorkflowMetrics object if found, None otherwise
        """
        with self._lock:
            workflow = self._workflows.get(session_id)
            if workflow:
                workflow.end_time = time.time()
                workflow.total_duration = workflow.end_time - workflow.start_time
                workflow.final_status = final_status
                logger.info(f"Ended tracking workflow: {session_id} (status: {final_status}, duration: {workflow.total_duration:.2f}s)")
                if self._current_workflow == workflow:
                    self._current_workflow = None
                return workflow
            return None
    
    @contextmanager
    def track_stage(self, stage_name: str, skill_name: str):
        """
        Context manager to track stage execution
        
        Args:
            stage_name: Name of the stage
            skill_name: Name of the skill being invoked
            
        Yields:
            StageMetrics object for this stage
        """
        stage = StageMetrics(
            stage_name=stage_name,
            skill_name=skill_name,
            start_time=time.time()
        )
        
        with self._lock:
            if self._current_workflow:
                self._current_workflow.stage_metrics.append(stage)
            self._current_stage = stage
        
        logger.info(f"Started tracking stage: {stage_name} (skill: {skill_name})")
        
        try:
            yield stage
        finally:
            stage.end_time = time.time()
            stage.duration = stage.end_time - stage.start_time
            logger.info(f"Ended tracking stage: {stage_name} (duration: {stage.duration:.2f}s)")
            
            with self._lock:
                if self._current_stage == stage:
                    self._current_stage = None
    
    @contextmanager
    def track_skill_invocation(self, skill_name: str, session_id: str, is_reviewer: bool = False):
        """
        Context manager to track skill invocation
        
        Args:
            skill_name: Name of the skill
            session_id: Session identifier
            is_reviewer: Whether this is a reviewer dispatch
            
        Yields:
            SkillInvocationMetrics object for this invocation
        """
        skill = SkillInvocationMetrics(
            skill_name=skill_name,
            session_id=session_id,
            start_time=time.time(),
            is_reviewer=is_reviewer
        )
        
        with self._lock:
            if self._current_workflow:
                self._current_workflow.skill_metrics.append(skill)
            self._current_skill = skill
        
        logger.info(f"Started tracking skill invocation: {skill_name} (session: {session_id})")
        
        try:
            yield skill
        finally:
            skill.end_time = time.time()
            skill.duration = skill.end_time - skill.start_time
            logger.info(f"Ended tracking skill invocation: {skill_name} (duration: {skill.duration:.2f}s)")
            
            with self._lock:
                if self._current_skill == skill:
                    self._current_skill = None
    
    @contextmanager
    def track_gate_decision(self, gate_id: str, stage_name: str):
        """
        Context manager to track gate decision time
        
        Args:
            gate_id: Gate identifier
            stage_name: Name of the stage
            
        Yields:
            GateMetrics object for this gate
        """
        gate = GateMetrics(
            gate_id=gate_id,
            stage_name=stage_name,
            start_time=time.time()
        )
        
        with self._lock:
            if self._current_workflow:
                self._current_workflow.gate_metrics.append(gate)
            self._current_gate = gate
        
        logger.info(f"Started tracking gate decision: {gate_id} (stage: {stage_name})")
        
        try:
            yield gate
        finally:
            gate.end_time = time.time()
            gate.duration = gate.end_time - gate.start_time
            logger.info(f"Ended tracking gate decision: {gate_id} (duration: {gate.duration:.2f}s)")
            
            with self._lock:
                if self._current_gate == gate:
                    self._current_gate = None
    
    def record_retry(self, stage_name: str, retry_count: int):
        """
        Record a retry for a stage
        
        Args:
            stage_name: Name of the stage being retried
            retry_count: Current retry count
        """
        with self._lock:
            if self._current_stage and self._current_stage.stage_name == stage_name:
                self._current_stage.retry_count = retry_count
                logger.info(f"Recorded retry for stage {stage_name}: attempt {retry_count}")
    
    def record_stage_result(self, stage_name: str, success: bool, error: Optional[str] = None, triage_decision: Optional[str] = None):
        """
        Record the result of a stage execution
        
        Args:
            stage_name: Name of the stage
            success: Whether the stage succeeded
            error: Error message if failed
            triage_decision: Triage decision made
        """
        with self._lock:
            if self._current_stage and self._current_stage.stage_name == stage_name:
                self._current_stage.success = success
                self._current_stage.error = error
                self._current_stage.triage_decision = triage_decision
                logger.info(f"Recorded result for stage {stage_name}: success={success}, decision={triage_decision}")
    
    def record_skill_result(self, skill_name: str, success: bool, error: Optional[str] = None):
        """
        Record the result of a skill invocation
        
        Args:
            skill_name: Name of the skill
            success: Whether the skill succeeded
            error: Error message if failed
        """
        with self._lock:
            if self._current_skill and self._current_skill.skill_name == skill_name:
                self._current_skill.success = success
                self._current_skill.error = error
                logger.info(f"Recorded result for skill {skill_name}: success={success}")
    
    def record_gate_verdict(self, gate_id: str, verdict: str, blocked: bool):
        """
        Record the verdict of a gate decision
        
        Args:
            gate_id: Gate identifier
            verdict: Verdict (approve, request_changes, block)
            blocked: Whether the gate blocked the workflow
        """
        with self._lock:
            if self._current_gate and self._current_gate.gate_id == gate_id:
                self._current_gate.verdict = verdict
                self._current_gate.blocked = blocked
                logger.info(f"Recorded verdict for gate {gate_id}: {verdict}, blocked={blocked}")
    
    def get_workflow_metrics(self, session_id: str) -> Optional[WorkflowMetrics]:
        """
        Get metrics for a specific workflow
        
        Args:
            session_id: Session identifier
            
        Returns:
            WorkflowMetrics object if found, None otherwise
        """
        with self._lock:
            return self._workflows.get(session_id)
    
    def get_all_metrics(self) -> Dict[str, WorkflowMetrics]:
        """
        Get all collected workflow metrics
        
        Returns:
            Dictionary mapping session_id to WorkflowMetrics
        """
        with self._lock:
            return self._workflows.copy()
    
    def export_to_file(self, output_path: Path, session_id: Optional[str] = None) -> bool:
        """
        Export metrics to a JSON file
        
        Args:
            output_path: Path to output file
            session_id: Optional session ID to export specific workflow, or None for all
            
        Returns:
            True if export succeeded, False otherwise
        """
        try:
            with self._lock:
                if session_id:
                    workflows_to_export = {session_id: self._workflows.get(session_id)}
                else:
                    workflows_to_export = self._workflows.copy()
                
                # Convert to serializable format
                export_data = {}
                for sid, workflow in workflows_to_export.items():
                    if workflow:
                        export_data[sid] = {
                            'session_id': workflow.session_id,
                            'manifest_name': workflow.manifest_name,
                            'start_time': workflow.start_time,
                            'end_time': workflow.end_time,
                            'total_duration': workflow.total_duration,
                            'final_status': workflow.final_status,
                            'stage_metrics': [
                                {
                                    'stage_name': sm.stage_name,
                                    'skill_name': sm.skill_name,
                                    'start_time': sm.start_time,
                                    'end_time': sm.end_time,
                                    'duration': sm.duration,
                                    'success': sm.success,
                                    'retry_count': sm.retry_count,
                                    'error': sm.error,
                                    'triage_decision': sm.triage_decision
                                }
                                for sm in workflow.stage_metrics
                            ],
                            'skill_metrics': [
                                {
                                    'skill_name': sim.skill_name,
                                    'session_id': sim.session_id,
                                    'start_time': sim.start_time,
                                    'end_time': sim.end_time,
                                    'duration': sim.duration,
                                    'success': sim.success,
                                    'error': sim.error,
                                    'is_reviewer': sim.is_reviewer
                                }
                                for sim in workflow.skill_metrics
                            ],
                            'gate_metrics': [
                                {
                                    'gate_id': gm.gate_id,
                                    'stage_name': gm.stage_name,
                                    'start_time': gm.start_time,
                                    'end_time': gm.end_time,
                                    'duration': gm.duration,
                                    'verdict': gm.verdict,
                                    'blocked': gm.blocked
                                }
                                for gm in workflow.gate_metrics
                            ]
                        }
                
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
                
                logger.info(f"Exported metrics to {output_path}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to export metrics to {output_path}: {e}")
            return False
    
    def export_to_console(self, session_id: Optional[str] = None) -> str:
        """
        Export metrics to console-friendly string format
        
        Args:
            session_id: Optional session ID to export specific workflow, or None for all
            
        Returns:
            Formatted string with metrics
        """
        with self._lock:
            if session_id:
                workflows_to_export = {session_id: self._workflows.get(session_id)}
            else:
                workflows_to_export = self._workflows.copy()
            
            output_lines = []
            output_lines.append("=" * 80)
            output_lines.append("PERFORMANCE METRICS REPORT")
            output_lines.append("=" * 80)
            output_lines.append(f"Generated: {datetime.now().isoformat()}")
            output_lines.append("")
            
            for sid, workflow in workflows_to_export.items():
                if not workflow:
                    continue
                
                output_lines.append(f"Workflow: {sid}")
                output_lines.append(f"Manifest: {workflow.manifest_name}")
                output_lines.append(f"Status: {workflow.final_status}")
                if workflow.total_duration:
                    output_lines.append(f"Total Duration: {workflow.total_duration:.2f}s")
                output_lines.append("")
                
                # Stage metrics
                if workflow.stage_metrics:
                    output_lines.append("  Stage Metrics:")
                    output_lines.append("  " + "-" * 76)
                    for sm in workflow.stage_metrics:
                        output_lines.append(f"    Stage: {sm.stage_name}")
                        output_lines.append(f"      Skill: {sm.skill_name}")
                        if sm.duration:
                            output_lines.append(f"      Duration: {sm.duration:.2f}s")
                        output_lines.append(f"      Success: {sm.success}")
                        output_lines.append(f"      Retries: {sm.retry_count}")
                        if sm.triage_decision:
                            output_lines.append(f"      Triage Decision: {sm.triage_decision}")
                        if sm.error:
                            output_lines.append(f"      Error: {sm.error}")
                        output_lines.append("")
                
                # Skill metrics
                if workflow.skill_metrics:
                    output_lines.append("  Skill Invocation Metrics:")
                    output_lines.append("  " + "-" * 76)
                    for sim in workflow.skill_metrics:
                        output_lines.append(f"    Skill: {sim.skill_name}")
                        output_lines.append(f"      Session: {sim.session_id}")
                        if sim.duration:
                            output_lines.append(f"      Duration: {sim.duration:.2f}s")
                        output_lines.append(f"      Success: {sim.success}")
                        output_lines.append(f"      Reviewer: {sim.is_reviewer}")
                        if sim.error:
                            output_lines.append(f"      Error: {sim.error}")
                        output_lines.append("")
                
                # Gate metrics
                if workflow.gate_metrics:
                    output_lines.append("  Gate Decision Metrics:")
                    output_lines.append("  " + "-" * 76)
                    for gm in workflow.gate_metrics:
                        output_lines.append(f"    Gate: {gm.gate_id}")
                        output_lines.append(f"      Stage: {gm.stage_name}")
                        if gm.duration:
                            output_lines.append(f"      Duration: {gm.duration:.2f}s")
                        output_lines.append(f"      Verdict: {gm.verdict}")
                        output_lines.append(f"      Blocked: {gm.blocked}")
                        output_lines.append("")
                
                output_lines.append("=" * 80)
                output_lines.append("")
            
            return "\n".join(output_lines)
    
    def clear_metrics(self, session_id: Optional[str] = None):
        """
        Clear collected metrics
        
        Args:
            session_id: Optional session ID to clear specific workflow, or None for all
        """
        with self._lock:
            if session_id:
                if session_id in self._workflows:
                    del self._workflows[session_id]
                    logger.info(f"Cleared metrics for session: {session_id}")
            else:
                self._workflows.clear()
                logger.info("Cleared all metrics")


# Global metrics collector instance
_global_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """
    Get the global metrics collector instance
    
    Returns:
        Global MetricsCollector instance
    """
    return _global_metrics_collector

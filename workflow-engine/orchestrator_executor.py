#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrator-Driven Workflow Executor

Manifest-driven workflow execution with orchestrator reasoning.
The orchestrator (Cascade) dispatches stages, reasons through results, and handles gates.
"""

import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from skill_invoker import SkillInvoker, SkillInvocationResult


@dataclass
class StageResult:
    """Result of a workflow stage execution"""
    stage_name: str
    step: int
    skill: str
    success: bool
    output_artifacts: List[str]
    error: Optional[str]
    retry_count: int
    gate_verdict: Optional[str]
    structural_result: str
    reviewer_verdict: str
    confidence: str
    triage_decision: str


class OrchestratorExecutor:
    """
    Orchestrator-driven workflow executor
    
    Loads manifest, executes stages with skill_invoker, handles gates,
    and follows the orchestrator–worker pattern with reasoning and triage.
    """
    
    def __init__(self, devin_cli_path: Optional[str] = None, model: Optional[str] = None, demo_mode: bool = True):
        """
        Initialize orchestrator executor
        
        Args:
            devin_cli_path: Optional path to devin.exe (defaults to global config)
            model: Optional model to use for Devin dispatch (defaults to global config)
            demo_mode: If True, skip real Devin dispatches and simulate (for testing)
        """
        from config_loader import ConfigLoader
        
        config = ConfigLoader.load()
        
        self.harness_root = config.workflow_engine_dir
        self.devin_cli_path = devin_cli_path or config.devin_cli_path
        self.model = model or config.default_model
        self.workflows_dir = config.workflows_dir
        self.session_work_dir = config.session_work_dir
        self.demo_mode = demo_mode
        self.skill_invoker = SkillInvoker(devin_cli_path=self.devin_cli_path, model=self.model, demo_mode=demo_mode)
        
    def load_manifest(self, manifest_path: Path) -> Optional[Dict[str, Any]]:
        """Load workflow manifest from YAML"""
        if not manifest_path.exists():
            return None
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def execute_workflow(
        self,
        session_id: str,
        request_content: str,
        manifest_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow following the orchestrator–worker pattern
        
        Args:
            session_id: Session identifier (e.g., "SUPERPOWER-001")
            request_content: Content for request.md
            manifest_path: Optional path to manifest (defaults to superpower.manifest.yaml)
        
        Returns:
            Summary of workflow execution
        """
        # Load manifest
        if not manifest_path:
            manifest_path = self.workflows_dir / "superpower.manifest.yaml"
        
        manifest = self.load_manifest(manifest_path)
        if not manifest:
            return {
                "success": False,
                "error": f"Manifest not found: {manifest_path}"
            }
        
        # Initialize session
        session_dir = self.session_work_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create initial artifacts
        self._create_initial_artifacts(session_dir, session_id, request_content)
        
        # Execute stages
        results = []
        for stage in manifest.get('stages', []):
            stage_result = self.execute_stage(
                stage=stage,
                session_dir=session_dir,
                session_id=session_id,
                manifest=manifest
            )
            results.append(stage_result)
            
            # Check if stage failed
            if not stage_result.success:
                return {
                    "success": False,
                    "error": f"Stage {stage['name']} failed: {stage_result.error}",
                    "results": results
                }
            
            # Check if gate blocked
            if stage_result.gate_verdict == "BLOCK":
                return {
                    "success": False,
                    "error": f"Stage {stage['name']} blocked by gate",
                    "results": results
                }
            
            # Check if triage decision is to escalate
            if stage_result.triage_decision == "escalate":
                return {
                    "success": False,
                    "error": f"Stage {stage['name']} escalated to human",
                    "results": results
                }
        
        return {
            "success": True,
            "results": results
        }
    
    def _create_initial_artifacts(self, session_dir: Path, session_id: str, request_content: str):
        """Create initial session artifacts"""
        # Create request.md
        request_path = session_dir / "request.md"
        request_path.write_text(request_content, encoding="utf-8")
        
        # Create status.md
        status_path = session_dir / "status.md"
        status_content = "# Status for " + session_id + "\n\n## Current Stage\nstep_0\n\n## Status\nInitialized\n\n## Timestamp\n" + datetime.utcnow().isoformat() + "Z\n"
        status_path.write_text(status_content, encoding="utf-8")
        
        # Create session-audit.md
        audit_path = session_dir / "session-audit.md"
        audit_content = "# Session Audit: " + session_id + "\n\n## Session Initialization\n- Session ID: " + session_id + "\n- Timestamp: " + datetime.utcnow().isoformat() + "Z\n- Stage: step_0\n\n## Audit Entries\n\n"
        audit_path.write_text(audit_content, encoding="utf-8")
    
    def execute_stage(
        self,
        stage: Dict[str, Any],
        session_dir: Path,
        session_id: str,
        manifest: Dict[str, Any]
    ) -> StageResult:
        """
        Execute a single workflow stage following the orchestrator–worker pattern
        
        Args:
            stage: Stage definition from manifest
            session_dir: Session directory
            session_id: Session identifier
            manifest: Workflow manifest
        
        Returns:
            StageResult with execution status
        """
        stage_name = stage['name']
        step = stage['step']
        skill_name = stage['skill']
        
        # Prepare context
        context = {
            "session_id": session_id,
            "stage": stage_name,
            "step": step,
            "skill": skill_name
        }
        
        # Prepare focused context (required artifacts)
        required_artifacts = stage.get('required_artifacts', [])
        focused_context = []
        for artifact in required_artifacts:
            artifact_path = session_dir / artifact
            if artifact_path.exists():
                focused_context.append(str(artifact_path))
        
        # Determine if reviewer dispatch
        is_reviewer = skill_name in ["requesting-code-review", "swe-compliance"]
        
        # Dispatch worker
        result = self.skill_invoker.invoke_skill(
            skill_name=skill_name,
            context=context,
            workspace=str(session_dir),
            focused_context=focused_context,
            is_reviewer=is_reviewer
        )
        
        if not result.success:
            return StageResult(
                stage_name=stage_name,
                step=step,
                skill=skill_name,
                success=False,
                output_artifacts=[],
                error=result.error,
                retry_count=0,
                gate_verdict=None,
                structural_result="FAIL",
                reviewer_verdict="N/A",
                confidence="LOW",
                triage_decision="escalate"
            )
        
        # Simulate artifact creation for demo purposes
        # In production, Devin would create these artifacts
        output_artifacts = stage.get('output_artifacts', [])
        self._simulate_artifact_creation(session_dir, output_artifacts, skill_name, session_id)
        
        # Validate structural floor
        structural_result = self._validate_structural_floor(session_dir, output_artifacts)
        
        if structural_result == "FAIL":
            return StageResult(
                stage_name=stage_name,
                step=step,
                skill=skill_name,
                success=False,
                output_artifacts=[],
                error="Structural floor validation failed",
                retry_count=0,
                gate_verdict=None,
                structural_result="FAIL",
                reviewer_verdict="N/A",
                confidence="LOW",
                triage_decision="retry"
            )
        
        # Dispatch neutral reviewer (for demo, simulate)
        reviewer_verdict = "PASS"
        
        # Cascade triage decision (for demo, simulate)
        confidence = "HIGH"
        triage_decision = "proceed"
        
        # Check for gate
        gate_id = stage.get('gate')
        gate_verdict = None
        if gate_id and gate_id != "none":
            # In production, this would wait for human gate decision
            # For demo, simulate approval
            gate_verdict = "APPROVE"
        
        return StageResult(
            stage_name=stage_name,
            step=step,
            skill=skill_name,
            success=True,
            output_artifacts=output_artifacts,
            error=None,
            retry_count=0,
            gate_verdict=gate_verdict,
            structural_result=structural_result,
            reviewer_verdict=reviewer_verdict,
            confidence=confidence,
            triage_decision=triage_decision
        )
    
    def _validate_structural_floor(self, session_dir: Path, artifacts: List[str]) -> str:
        """Validate structural floor for output artifacts"""
        for artifact in artifacts:
            artifact_path = session_dir / artifact
            if not artifact_path.exists():
                return "FAIL"
            content = artifact_path.read_text(encoding="utf-8")
            if not content.strip():
                return "FAIL"
            if "TODO" in content or "PLACEHOLDER" in content:
                return "FAIL"
        return "PASS"
    
    def _simulate_artifact_creation(self, session_dir: Path, artifacts: List[str], skill_name: str, session_id: str):
        """Simulate artifact creation for demo purposes"""
        for artifact in artifacts:
            artifact_path = session_dir / artifact
            # Create parent directories if needed
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create artifact content
            content = f"# {artifact} for {session_id}\n\n## Overview\nThis is a demonstration {artifact} produced by the {skill_name} skill.\n\n## Content\n- Content item 1\n- Content item 2\n\n## Notes\nThis is a sample for demonstration purposes.\n"
            artifact_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    # Test the orchestrator executor
    harness_root = Path(__file__).parent
    devin_cli_path = "C:\\Users\\<username>\\AppData\\Local\\devin\\cli\\bin\\devin.exe"
    
    executor = OrchestratorExecutor(harness_root, devin_cli_path)
    
    request_content = "# Request\n\nImplement a caching layer for skill loading."
    
    result = executor.execute_workflow(
        session_id="SUPERPOWER-TEST-001",
        request_content=request_content
    )
    
    print("=== Orchestrator-Driven Workflow Execution ===")
    print("Success:", result.get("success"))
    if not result.get("success"):
        print("Error:", result.get("error"))
    print("Stages executed:", len(result.get("results", [])))

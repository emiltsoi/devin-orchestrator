#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestration Engine - Actual orchestration logic for workflow execution

This engine provides real automation vs manual protocol following.
It reads manifests, executes stages with retry logic, calls deterministic tools,
and manages state transitions.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from deterministic_tools import (
    session_init,
    validate_structural,
    record_gate,
    update_status,
    create_placeholder_artifact,
    load_manifest,
    load_skill
)
from skill_invoker import SkillInvoker
from config_loader import ConfigLoader


class TriageDecision(Enum):
    """Triage decision for stage execution"""
    PROCEED = "proceed"
    RETRY = "retry"
    ESCALATE = "escalate"


class OrchestrationEngine:
    """Actual orchestration engine for workflow execution"""
    
    def __init__(self, work_dir: Path, config: Optional[Dict[str, Any]] = None):
        """
        Initialize orchestration engine
        
        Args:
            work_dir: Base work directory for sessions
            config: Optional configuration dictionary
        """
        self.work_dir = work_dir
        self.config = config or {}
        self.skill_invoker = SkillInvoker(demo_mode=config.get('demo_mode', False))
    
    def execute_workflow(
        self,
        manifest_path: Path,
        session_id: str,
        request_content: str,
        skip_brainstorming: Optional[bool] = None,
        config_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete workflow from manifest
        
        Args:
            manifest_path: Path to workflow manifest
            session_id: Unique session identifier
            request_content: Initial request content
            skip_brainstorming: Override manifest skip_brainstorming setting
            config_overrides: Optional configuration overrides for skills
            
        Returns:
            Dictionary with execution results
        """
        # Load manifest
        manifest = load_manifest(manifest_path)
        
        # Initialize session
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        # Override skip_brainstorming if provided
        if skip_brainstorming is not None:
            manifest['skip_brainstorming'] = skip_brainstorming
        
        # Execute stages
        results = {
            'session_id': session_id,
            'manifest': manifest['name'],
            'stages': [],
            'final_status': 'unknown'
        }
        
        for stage in manifest['stages']:
            stage_result = self._execute_stage(
                stage=stage,
                manifest=manifest,
                session_dir=session_dir,
                session_id=session_id,
                config_overrides=config_overrides
            )
            results['stages'].append(stage_result)
            
            # Check triage decision
            if stage_result['triage_decision'] == TriageDecision.ESCALATE:
                results['final_status'] = 'escalated'
                update_status(session_dir, stage['name'], 'escalated', 'Workflow escalated to human')
                break
            elif stage_result['triage_decision'] == TriageDecision.RETRY:
                # Implement retry logic with max retries and backoff
                max_retries = 3
                retry_count = 0
                last_error = stage_result['error']
                
                while retry_count < max_retries:
                    retry_count += 1
                    update_status(session_dir, stage['name'], 'retrying', f"Retry {retry_count}/{max_retries}: {last_error}")
                    
                    # Exponential backoff: 2^retry_count seconds
                    import time
                    backoff_seconds = 2 ** retry_count
                    time.sleep(backoff_seconds)
                    
                    # Re-dispatch with correction artifact
                    correction_artifact = session_dir / f"correction-{stage['name']}-attempt{retry_count}.md"
                    correction_artifact.write_text(f"# Correction for {stage['name']}\n\nError: {last_error}\n\nPlease fix the issue and re-run the stage.")
                    
                    stage_result = self._execute_stage(
                        stage=stage,
                        manifest=manifest,
                        session_dir=session_dir,
                        session_id=session_id,
                        config_overrides=config_overrides,
                        correction_artifact=str(correction_artifact)
                    )
                    
                    if stage_result['triage_decision'] == TriageDecision.PROCEED:
                        break
                    last_error = stage_result['error']
                
                if retry_count >= max_retries and stage_result['triage_decision'] != TriageDecision.PROCEED:
                    results['final_status'] = 'escalated'
                    update_status(session_dir, stage['name'], 'escalated', f"Max retries ({max_retries}) exceeded: {last_error}")
                    break
            
            # Handle gate if present
            if 'gate' in stage and stage['gate'] != 'none':
                gate_result = self._handle_gate(
                    gate_id=stage['gate'],
                    stage_name=stage['name'],
                    session_dir=session_dir
                )
                if gate_result['blocked']:
                    results['final_status'] = 'blocked'
                    break
        
        if results['final_status'] == 'unknown':
            results['final_status'] = 'completed'
        
        return results
    
    def _execute_stage(
        self,
        stage: Dict[str, Any],
        manifest: Dict[str, Any],
        session_dir: Path,
        session_id: str,
        config_overrides: Optional[Dict[str, Any]] = None,
        correction_artifact: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a single stage
        
        Args:
            stage: Stage configuration from manifest
            manifest: Full manifest configuration
            session_dir: Session directory
            session_id: Session identifier
            config_overrides: Optional configuration overrides for skills
            
        Returns:
            Dictionary with stage execution results
        """
        stage_name = stage['name']
        skill_name = stage['skill']
        
        update_status(session_dir, stage_name, 'in_progress', f"Starting stage: {stage_name}")
        
        # Check if stage should be skipped
        if manifest.get('skip_brainstorming', False) and stage_name == 'brainstorming':
            return self._skip_stage(stage, session_dir, session_id)
        
        # Check if interactive mode is enabled for this stage
        if config_overrides and config_overrides.get('interactive_mode', False):
            # Create pause file for user input
            pause_file = session_dir / f"pause-{stage_name}.md"
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
            
            # Wait for pause file to be modified
            import time
            max_wait_seconds = 3600  # 1 hour timeout
            check_interval = 5
            waited_seconds = 0
            initial_content = pause_file.read_text()
            
            while waited_seconds < max_wait_seconds:
                time.sleep(check_interval)
                waited_seconds += check_interval
                
                current_content = pause_file.read_text()
                if current_content != initial_content and 'input:' in current_content:
                    # Parse user input
                    user_input = ""
                    for line in current_content.split('\n'):
                        if line.startswith('input:'):
                            user_input = line.split(':', 1)[1].strip()
                            break
                    
                    update_status(session_dir, stage_name, 'paused', f"User input received: {user_input[:50]}...")
                    break
            
            if waited_seconds >= max_wait_seconds:
                update_status(session_dir, stage_name, 'timeout', f"Interactive pause timeout after {max_wait_seconds} seconds")
        
        # Load skill
        from config_loader import ConfigLoader
        config = ConfigLoader.load()
        skills_dir = config.skills_dir
        skill_data = load_skill(skills_dir, skill_name)
        
        # Dispatch skill
        result = self.skill_invoker.invoke_skill(
            skill_name=skill_name,
            context={
                'session_id': session_id,
                'stage': stage_name,
                'skill': skill_name
            },
            workspace=str(session_dir),
            is_reviewer=stage.get('skill') == 'requesting-code-review',
            config_overrides=config_overrides,
            correction_artifact=correction_artifact
        )
        
        # Validate output artifacts
        output_artifacts = stage.get('output_artifacts', [])
        artifact_paths = [session_dir / artifact for artifact in output_artifacts]
        
        validation_result = validate_structural(artifact_paths)
        
        # Make triage decision
        if not result.success:
            triage_decision = TriageDecision.ESCALATE
            error = result.error
        elif not validation_result['valid']:
            triage_decision = TriageDecision.RETRY
            error = '; '.join(validation_result['errors'])
        else:
            triage_decision = TriageDecision.PROCEED
            error = None
        
        update_status(
            session_dir,
            stage_name,
            'completed' if triage_decision == TriageDecision.PROCEED else 'failed',
            f"Triage decision: {triage_decision.value}"
        )
        
        return {
            'stage': stage_name,
            'skill': skill_name,
            'success': result.success,
            'output': result.output,
            'error': error,
            'validation': validation_result,
            'triage_decision': triage_decision
        }
    
    def _skip_stage(
        self,
        stage: Dict[str, Any],
        session_dir: Path,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Skip a stage (e.g., brainstorming when spec is clear)
        
        Args:
            stage: Stage configuration from manifest
            session_dir: Session directory
            session_id: Session identifier
            
        Returns:
            Dictionary with stage skip results
        """
        stage_name = stage['name']
        
        update_status(session_dir, stage_name, 'skipped', 'Skipping stage - spec is clear')
        
        # Create placeholder artifacts
        output_artifacts = stage.get('output_artifacts', [])
        for artifact in output_artifacts:
            artifact_path = session_dir / artifact
            if artifact_path.name == 'design.md':
                placeholder = f"# Design\n\nSkipping brainstorming - spec is clear.\n\nSession ID: {session_id}\n"
                create_placeholder_artifact(artifact_path, placeholder)
        
        return {
            'stage': stage_name,
            'skill': stage['skill'],
            'success': True,
            'output': 'Stage skipped - spec is clear',
            'error': None,
            'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
            'triage_decision': TriageDecision.PROCEED
        }
    
    def _handle_gate(
        self,
        gate_id: str,
        stage_name: str,
        session_dir: Path
    ) -> Dict[str, Any]:
        """
        Handle a gate (human approval or auto-gate)
        
        Args:
            gate_id: Gate identifier
            stage_name: Stage name for context
            session_dir: Session directory
            
        Returns:
            Dictionary with gate handling results
        """
        update_status(session_dir, f"gate_{gate_id}", 'waiting', f"Waiting for gate decision: {gate_id}")
        
        # Create gate decision file for human input
        gate_decision_file = session_dir / f"gate-{gate_id}-decision.md"
        gate_decision_file.write_text(f"""# Gate Decision: {gate_id}

Stage: {stage_name}

Please review the stage output and provide your decision.

## Options:
- approve: Proceed to next stage
- request_changes: Request changes and retry
- block: Block workflow and escalate to human

## Decision Format:
```
verdict: approve|request_changes|block
notes: [optional notes]
```

Please edit this file with your decision.
""")
        
        # Wait for gate decision file to be modified
        import time
        max_wait_seconds = 3600  # 1 hour timeout
        check_interval = 5  # Check every 5 seconds
        waited_seconds = 0
        
        while waited_seconds < max_wait_seconds:
            time.sleep(check_interval)
            waited_seconds += check_interval
            
            # Check if file has been modified (contains decision)
            content = gate_decision_file.read_text()
            if 'verdict:' in content:
                # Parse decision
                verdict = None
                notes = ""
                for line in content.split('\n'):
                    if line.startswith('verdict:'):
                        verdict = line.split(':', 1)[1].strip()
                    elif line.startswith('notes:'):
                        notes = line.split(':', 1)[1].strip()
                
                if verdict in ['approve', 'request_changes', 'block']:
                    record_gate(gate_id, verdict, session_dir, notes)
                    update_status(session_dir, f"gate_{gate_id}", verdict, f"Gate {verdict}: {gate_id}")
                    
                    return {
                        'gate_id': gate_id,
                        'verdict': verdict,
                        'blocked': verdict == 'block'
                    }
        
        # Timeout reached - escalate
        verdict = 'block'
        notes = f"Gate decision timeout after {max_wait_seconds} seconds"
        record_gate(gate_id, verdict, session_dir, notes)
        update_status(session_dir, f"gate_{gate_id}", 'timeout', f"Gate timeout: {gate_id}")
        
        return {
            'gate_id': gate_id,
            'verdict': verdict,
            'blocked': True
        }


def main():
    """CLI entry point for orchestration engine"""
    if len(sys.argv) < 4:
        print("Usage: orchestration_engine.py <manifest_path> <session_id> <request_content> [skip_brainstorming]")
        sys.exit(1)
    
    manifest_path = Path(sys.argv[1])
    session_id = sys.argv[2]
    request_content = sys.argv[3]
    skip_brainstorming = len(sys.argv) > 4 and sys.argv[4].lower() == 'true'
    
    config = ConfigLoader.load()
    work_dir = Path(config.session_work_dir)
    
    engine = OrchestrationEngine(work_dir, config.__dict__)
    results = engine.execute_workflow(manifest_path, session_id, request_content, skip_brainstorming)
    
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()

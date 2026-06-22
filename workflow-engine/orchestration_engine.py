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
import logging
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
from metrics import get_metrics_collector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        try:
            self.work_dir = work_dir
            self.config = config or {}
            self.skill_invoker = SkillInvoker(demo_mode=config.get('demo_mode', False))
            self.metrics = get_metrics_collector()
            logger.info(f"OrchestrationEngine initialized with work_dir: {work_dir}")
        except Exception as e:
            logger.error(f"Error initializing OrchestrationEngine: {e}")
            raise
    
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
        try:
            # Load manifest
            manifest = load_manifest(manifest_path)
            logger.info(f"Loaded manifest from {manifest_path}: {manifest.get('name', 'unknown')}")
        except FileNotFoundError as e:
            logger.error(f"Manifest file not found: {manifest_path} - {e}")
            return {
                'session_id': session_id,
                'manifest': 'unknown',
                'stages': [],
                'final_status': 'failed',
                'error': f"Manifest file not found: {manifest_path}",
                'error_type': 'FileNotFoundError'
            }
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in manifest file {manifest_path}: {e}")
            return {
                'session_id': session_id,
                'manifest': 'unknown',
                'stages': [],
                'final_status': 'failed',
                'error': f"Invalid JSON in manifest file: {e}",
                'error_type': 'JSONDecodeError'
            }
        except Exception as e:
            logger.error(f"Unexpected error loading manifest {manifest_path}: {e}")
            return {
                'session_id': session_id,
                'manifest': 'unknown',
                'stages': [],
                'final_status': 'failed',
                'error': f"Unexpected error loading manifest: {str(e)}",
                'error_type': type(e).__name__
            }
        
        try:
            # Initialize session
            session_dir = session_init(session_id, self.work_dir, request_content)
            logger.info(f"Initialized session {session_id} at {session_dir}")
        except PermissionError as e:
            logger.error(f"Permission error initializing session directory: {e}")
            return {
                'session_id': session_id,
                'manifest': manifest.get('name', 'unknown'),
                'stages': [],
                'final_status': 'failed',
                'error': f"Permission error initializing session: {str(e)}",
                'error_type': 'PermissionError'
            }
        except OSError as e:
            logger.error(f"OS error initializing session directory: {e}")
            return {
                'session_id': session_id,
                'manifest': manifest.get('name', 'unknown'),
                'stages': [],
                'final_status': 'failed',
                'error': f"OS error initializing session: {str(e)}",
                'error_type': 'OSError'
            }
        except Exception as e:
            logger.error(f"Unexpected error initializing session: {e}")
            return {
                'session_id': session_id,
                'manifest': manifest.get('name', 'unknown'),
                'stages': [],
                'final_status': 'failed',
                'error': f"Unexpected error initializing session: {str(e)}",
                'error_type': type(e).__name__
            }
        
        # Override skip_brainstorming if provided
        if skip_brainstorming is not None:
            manifest['skip_brainstorming'] = skip_brainstorming
        
        # Start metrics tracking for this workflow
        self.metrics.start_workflow(session_id, manifest['name'])
        
        # Execute stages
        results = {
            'session_id': session_id,
            'manifest': manifest['name'],
            'stages': [],
            'final_status': 'unknown'
        }
        
        for stage in manifest['stages']:
            try:
                stage_result = self._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id,
                    config_overrides=config_overrides
                )
                results['stages'].append(stage_result)
            except Exception as e:
                logger.error(f"Unexpected error executing stage {stage.get('name', 'unknown')}: {e}")
                results['stages'].append({
                    'stage': stage.get('name', 'unknown'),
                    'skill': stage.get('skill', 'unknown'),
                    'success': False,
                    'output': None,
                    'error': f"Unexpected error during stage execution: {str(e)}",
                    'validation': {'valid': False, 'errors': [f"Unexpected error: {str(e)}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.ESCALATE
                })
                results['final_status'] = 'escalated'
                update_status(session_dir, stage.get('name', 'unknown'), 'error', f"Unexpected error: {str(e)}")
                break
            
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
                    try:
                        correction_artifact = session_dir / f"correction-{stage['name']}-attempt{retry_count}.md"
                        correction_artifact.write_text(f"# Correction for {stage['name']}\n\nError: {last_error}\n\nPlease fix the issue and re-run the stage.")
                        logger.info(f"Created correction artifact: {correction_artifact}")
                    except (PermissionError, IOError) as e:
                        logger.error(f"Error creating correction artifact: {e}")
                        update_status(session_dir, stage['name'], 'error', f"Failed to create correction artifact: {str(e)}")
                        break
                    
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
                    
                    # Log retry exhaustion
                    self.logger.log_retry_exhausted(
                        session_id=session_id,
                        stage_name=stage['name'],
                        max_retries=max_retries,
                        final_error=last_error
                    )
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
        
        # End metrics tracking for this workflow
        self.metrics.end_workflow(session_id, results['final_status'])
        
        # Export metrics to file
        metrics_file = session_dir / "metrics.json"
        self.metrics.export_to_file(metrics_file, session_id)
        
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
        
        # Track stage execution with metrics
        with self.metrics.track_stage(stage_name, skill_name) as stage_metrics:
            # Check if interactive mode is enabled for this stage
            if config_overrides and config_overrides.get('interactive_mode', False):
                # Create pause file for user input
                try:
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
                    logger.info(f"Created pause file for interactive mode: {pause_file}")
                except PermissionError as e:
                    logger.error(f"Permission error creating pause file: {e}")
                    return {
                        'stage': stage_name,
                        'skill': skill_name,
                        'success': False,
                        'output': None,
                        'error': f"Permission error creating pause file: {str(e)}",
                        'validation': {'valid': False, 'errors': [f"Permission error: {str(e)}"], 'artifact_results': {}},
                        'triage_decision': TriageDecision.ESCALATE
                    }
                except IOError as e:
                    logger.error(f"IO error creating pause file: {e}")
                    return {
                        'stage': stage_name,
                        'skill': skill_name,
                        'success': False,
                        'output': None,
                        'error': f"IO error creating pause file: {str(e)}",
                        'validation': {'valid': False, 'errors': [f"IO error: {str(e)}"], 'artifact_results': {}},
                        'triage_decision': TriageDecision.ESCALATE
                    }
                
                # Wait for pause file to be modified
                try:
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
                except PermissionError as e:
                    logger.error(f"Permission error reading pause file: {e}")
                    update_status(session_dir, stage_name, 'error', f"Permission error reading pause file: {str(e)}")
                except IOError as e:
                    logger.error(f"IO error reading pause file: {e}")
                    update_status(session_dir, stage_name, 'error', f"IO error reading pause file: {str(e)}")
            
            # Load skill
            try:
                from config_loader import ConfigLoader
                config = ConfigLoader.load()
                skills_dir = config.skills_dir
                skill_data = load_skill(skills_dir, skill_name)
                logger.info(f"Loaded skill {skill_name} from {skills_dir}")
            except FileNotFoundError as e:
                logger.error(f"Skill directory or file not found for {skill_name}: {e}")
                return {
                    'stage': stage_name,
                    'skill': skill_name,
                    'success': False,
                    'output': None,
                    'error': f"Skill not found: {skill_name}",
                    'validation': {'valid': False, 'errors': [f"Skill not found: {skill_name}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.ESCALATE
                }
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in skill file for {skill_name}: {e}")
                return {
                    'stage': stage_name,
                    'skill': skill_name,
                    'success': False,
                    'output': None,
                    'error': f"Invalid JSON in skill file: {e}",
                    'validation': {'valid': False, 'errors': [f"Invalid JSON in skill file: {e}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.ESCALATE
                }
            except Exception as e:
                logger.error(f"Unexpected error loading skill {skill_name}: {e}")
                return {
                    'stage': stage_name,
                    'skill': skill_name,
                    'success': False,
                    'output': None,
                    'error': f"Unexpected error loading skill: {str(e)}",
                    'validation': {'valid': False, 'errors': [f"Unexpected error loading skill: {str(e)}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.ESCALATE
                }
        
        # Dispatch skill with metrics tracking
        with self.metrics.track_skill_invocation(skill_name, session_id, stage.get('skill') == 'requesting-code-review') as skill_metrics:
            try:
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
                logger.info(f"Skill {skill_name} invocation completed with success={result.success}")
                
                # Record skill result in metrics
                self.metrics.record_skill_result(skill_name, result.success, result.error)
                
            except RuntimeError as e:
                logger.error(f"Runtime error during skill invocation for {skill_name}: {e}")
                self.metrics.record_skill_result(skill_name, False, f"Runtime error: {str(e)}")
                return {
                    'stage': stage_name,
                    'skill': skill_name,
                    'success': False,
                    'output': None,
                    'error': f"Runtime error during skill invocation: {str(e)}",
                    'validation': {'valid': False, 'errors': [f"Runtime error: {str(e)}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.ESCALATE
                }
            except TimeoutError as e:
                logger.error(f"Timeout during skill invocation for {skill_name}: {e}")
                self.metrics.record_skill_result(skill_name, False, f"Timeout: {str(e)}")
                return {
                    'stage': stage_name,
                    'skill': skill_name,
                    'success': False,
                    'output': None,
                    'error': f"Timeout during skill invocation: {str(e)}",
                    'validation': {'valid': False, 'errors': [f"Timeout: {str(e)}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.RETRY
                }
            except Exception as e:
                logger.error(f"Unexpected error during skill invocation for {skill_name}: {e}")
                self.metrics.record_skill_result(skill_name, False, f"Unexpected error: {str(e)}")
                return {
                    'stage': stage_name,
                    'skill': skill_name,
                    'success': False,
                    'output': None,
                    'error': f"Unexpected error during skill invocation: {str(e)}",
                    'validation': {'valid': False, 'errors': [f"Unexpected error: {str(e)}"], 'artifact_results': {}},
                    'triage_decision': TriageDecision.ESCALATE
                }
        
        # Validate output artifacts
        try:
            output_artifacts = stage.get('output_artifacts', [])
            artifact_paths = [session_dir / artifact for artifact in output_artifacts]
            validation_result = validate_structural(artifact_paths)
            logger.info(f"Validation completed for stage {stage_name}: valid={validation_result['valid']}")
        except FileNotFoundError as e:
            logger.error(f"Artifact not found during validation for stage {stage_name}: {e}")
            validation_result = {
                'valid': False,
                'errors': [f"Artifact not found: {str(e)}"],
                'artifact_results': {}
            }
        except PermissionError as e:
            logger.error(f"Permission error during validation for stage {stage_name}: {e}")
            validation_result = {
                'valid': False,
                'errors': [f"Permission error during validation: {str(e)}"],
                'artifact_results': {}
            }
        except Exception as e:
            logger.error(f"Unexpected error during validation for stage {stage_name}: {e}")
            validation_result = {
                'valid': False,
                'errors': [f"Unexpected validation error: {str(e)}"],
                'artifact_results': {}
            }
        
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
        
        # Record stage result in metrics
        self.metrics.record_stage_result(stage_name, result.success, error, triage_decision.value)
        
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
        try:
            output_artifacts = stage.get('output_artifacts', [])
            for artifact in output_artifacts:
                artifact_path = session_dir / artifact
                if artifact_path.name == 'design.md':
                    placeholder = f"# Design\n\nSkipping brainstorming - spec is clear.\n\nSession ID: {session_id}\n"
                    create_placeholder_artifact(artifact_path, placeholder)
                    logger.info(f"Created placeholder artifact: {artifact_path}")
        except (PermissionError, IOError) as e:
            logger.error(f"Error creating placeholder artifacts: {e}")
            return {
                'stage': stage_name,
                'skill': stage['skill'],
                'success': False,
                'output': 'Stage skip failed - artifact creation error',
                'error': f"Error creating placeholder artifacts: {str(e)}",
                'validation': {'valid': False, 'errors': [f"Artifact creation error: {str(e)}"], 'artifact_results': {}},
                'triage_decision': TriageDecision.ESCALATE
            }
        
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
        try:
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
            logger.info(f"Created gate decision file: {gate_decision_file}")
        except (PermissionError, IOError) as e:
            logger.error(f"Error creating gate decision file: {e}")
            update_status(session_dir, f"gate_{gate_id}", 'error', f"Failed to create gate decision file: {str(e)}")
            return {
                'gate_id': gate_id,
                'verdict': 'block',
                'blocked': True,
                'error': f"Failed to create gate decision file: {str(e)}"
            }
        
        # Wait for gate decision file to be modified
        try:
            import time
            max_wait_seconds = 3600  # 1 hour timeout
            check_interval = 5  # Check every 5 seconds
            waited_seconds = 0
            
            while waited_seconds < max_wait_seconds:
                time.sleep(check_interval)
                waited_seconds += check_interval
                
                # Check if file has been modified (contains decision)
                try:
                    content = gate_decision_file.read_text()
                except (PermissionError, IOError) as e:
                    logger.error(f"Error reading gate decision file: {e}")
                    update_status(session_dir, f"gate_{gate_id}", 'error', f"Failed to read gate decision file: {str(e)}")
                    return {
                        'gate_id': gate_id,
                        'verdict': 'block',
                        'blocked': True,
                        'error': f"Failed to read gate decision file: {str(e)}"
                    }
                
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
                        try:
                            record_gate(gate_id, verdict, session_dir, notes)
                            update_status(session_dir, f"gate_{gate_id}", verdict, f"Gate {verdict}: {gate_id}")
                            logger.info(f"Gate {gate_id} decision recorded: {verdict}")
                        except Exception as e:
                            logger.error(f"Error recording gate decision: {e}")
                            update_status(session_dir, f"gate_{gate_id}", 'error', f"Failed to record gate decision: {str(e)}")
                        
                        return {
                            'gate_id': gate_id,
                            'verdict': verdict,
                            'blocked': verdict == 'block'
                        }
            
            # Timeout reached - escalate
            verdict = 'block'
            notes = f"Gate decision timeout after {max_wait_seconds} seconds"
            try:
                record_gate(gate_id, verdict, session_dir, notes)
                update_status(session_dir, f"gate_{gate_id}", 'timeout', f"Gate timeout: {gate_id}")
                logger.warning(f"Gate {gate_id} timeout after {max_wait_seconds} seconds")
            except Exception as e:
                logger.error(f"Error recording gate timeout: {e}")
                update_status(session_dir, f"gate_{gate_id}", 'error', f"Failed to record gate timeout: {str(e)}")
            
            return {
                'gate_id': gate_id,
                'verdict': verdict,
                'blocked': True
            }
        except Exception as e:
            logger.error(f"Unexpected error during gate handling: {e}")
            update_status(session_dir, f"gate_{gate_id}", 'error', f"Unexpected gate handling error: {str(e)}")
            return {
                'gate_id': gate_id,
                'verdict': 'block',
                'blocked': True,
                'error': f"Unexpected gate handling error: {str(e)}"
            }


def main():
    """CLI entry point for orchestration engine"""
    try:
        if len(sys.argv) < 4:
            print("Usage: orchestration_engine.py <manifest_path> <session_id> <request_content> [skip_brainstorming]")
            sys.exit(1)
        
        manifest_path = Path(sys.argv[1])
        session_id = sys.argv[2]
        request_content = sys.argv[3]
        skip_brainstorming = len(sys.argv) > 4 and sys.argv[4].lower() == 'true'
        
        try:
            config = ConfigLoader.load()
            work_dir = Path(config.session_work_dir)
            logger.info(f"Loaded config, work_dir: {work_dir}")
        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {e}")
            print(json.dumps({
                'error': 'Configuration file not found',
                'error_type': 'FileNotFoundError',
                'details': str(e)
            }, indent=2))
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            print(json.dumps({
                'error': 'Invalid JSON in configuration file',
                'error_type': 'JSONDecodeError',
                'details': str(e)
            }, indent=2))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error loading configuration: {e}")
            print(json.dumps({
                'error': 'Unexpected error loading configuration',
                'error_type': type(e).__name__,
                'details': str(e)
            }, indent=2))
            sys.exit(1)
        
        try:
            engine = OrchestrationEngine(work_dir, config.__dict__)
        except Exception as e:
            logger.error(f"Error initializing orchestration engine: {e}")
            print(json.dumps({
                'error': 'Error initializing orchestration engine',
                'error_type': type(e).__name__,
                'details': str(e)
            }, indent=2))
            sys.exit(1)
        
        try:
            results = engine.execute_workflow(manifest_path, session_id, request_content, skip_brainstorming)
            print(json.dumps(results, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            print(json.dumps({
                'error': 'Error executing workflow',
                'error_type': type(e).__name__,
                'details': str(e)
            }, indent=2))
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Workflow execution interrupted by user")
        print(json.dumps({
            'error': 'Workflow execution interrupted',
            'error_type': 'KeyboardInterrupt'
        }, indent=2))
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        print(json.dumps({
            'error': 'Unexpected error',
            'error_type': type(e).__name__,
            'details': str(e)
        }, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Integration Tests for Complete Workflow Execution
Tests end-to-end workflow execution from manifest to completion
Following TDD principles - comprehensive coverage of critical functionality
"""

import unittest
import tempfile
import shutil
import json
import time
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))

from orchestration_engine import OrchestrationEngine, TriageDecision
from deterministic_tools import session_init, validate_structural, record_gate, update_status, load_manifest, load_skill
from skill_invoker import SkillInvoker, SkillInvocationResult
from config_loader import ConfigLoader


class TestWorkflowExecutionIntegration(unittest.TestCase):
    """Integration tests for complete workflow execution"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.work_dir = self.temp_path / 'work'
        self.work_dir.mkdir()
        self.skills_dir = self.temp_path / 'skills'
        self.skills_dir.mkdir()
        self.workflows_dir = self.temp_path / 'workflows'
        self.workflows_dir.mkdir()
        
        # Create comprehensive skill files
        self._create_skill_files()
        
        # Create a realistic workflow manifest
        self.workflow_manifest = {
            'name': 'feature-development',
            'description': 'Complete feature development workflow',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': False,
            'stages': [
                {
                    'name': 'brainstorming',
                    'skill': 'brainstorming',
                    'description': 'Refine requirements and design',
                    'output_artifacts': ['design.md'],
                    'gate': 'none'
                },
                {
                    'name': 'implementation',
                    'skill': 'test-driven-development',
                    'description': 'Implement with TDD approach',
                    'output_artifacts': ['implementation.md', 'test-results.md'],
                    'gate': 'g1_approval'
                },
                {
                    'name': 'review',
                    'skill': 'requesting-code-review',
                    'description': 'Review implementation',
                    'output_artifacts': ['review-findings.md'],
                    'gate': 'none'
                }
            ]
        }
        
        self.manifest_path = self.workflows_dir / 'feature-development.yaml'
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.workflow_manifest, f)
        
        # Mock config
        self.config = {
            'demo_mode': True,
            'skills_dir': self.skills_dir,
            'session_work_dir': str(self.work_dir)
        }
        
        self.engine = OrchestrationEngine(self.work_dir, self.config)

    def _mock_load_skill(self, skills_dir, skill_name):
        """Helper to create mock skill data"""
        return {
            'definition': {
                'schema_version': 1,
                'name': skill_name,
                'description': 'Test skill',
                'iron_law': 'TEST IRON LAW',
                'triggers': ['test'],
                'checklist': [],
                'terminal_state': 'completed',
                'announcement': 'Using test skill',
                'red_flags': []
            },
            'narrative': '# Test Skill\n\nTest skill description.',
            'format': 'separate'
        }

    def _create_skill_files(self):
        """Create skill definition and narrative files"""
        skills = [
            {
                'name': 'brainstorming',
                'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                'description': 'Brainstorming skill for design refinement'
            },
            {
                'name': 'test-driven-development',
                'iron_law': 'WRITE FAILING TEST FIRST, THEN IMPLEMENT TO MAKE IT PASS',
                'description': 'TDD skill for implementation'
            },
            {
                'name': 'requesting-code-review',
                'iron_law': 'REVIEW MUST BE COMPLETED BEFORE MERGE',
                'description': 'Code review skill'
            }
        ]
        
        for skill in skills:
            skill_name = skill['name']
            yaml_content = 'schema_version: 1\nname: {}\ndescription: {}\niron_law: "{}"\ntriggers: [implementation]\nchecklist: []\nterminal_state: completed\nannouncement: "Using the {} skill"\nred_flags: []\n'.format(
                skill_name, skill['description'], skill['iron_law'], skill_name
            )
            md_content = '# {} Skill\n\n## Overview\n{}\n\n## The Iron Law\n{}\n'.format(
                skill_name.title(), skill['description'], skill['iron_law']
            )
            (self.skills_dir / (skill_name + '.yaml')).write_text(yaml_content)
            (self.skills_dir / (skill_name + '.md')).write_text(md_content)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_complete_workflow_execution_success(self):
        """Test complete workflow execution from manifest to completion"""
        session_id = 'INT-001'
        request_content = 'Implement user authentication feature'
        
        # Mock skill invoker to return success
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Skill executed successfully',
                    error=None
                )
                
                # Execute workflow
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content
                )
            
            # Verify workflow completed successfully
            self.assertEqual(results['session_id'], session_id)
            self.assertEqual(results['manifest'], 'feature-development')
            self.assertEqual(results['final_status'], 'completed')
            self.assertEqual(len(results['stages']), 3)
            
            # Verify each stage was executed
            stage_names = [stage['stage'] for stage in results['stages']]
            self.assertEqual(stage_names, ['brainstorming', 'implementation', 'review'])
            
            # Verify session directory was created
            session_dir = self.work_dir / session_id
            self.assertTrue(session_dir.exists())
            
            # Verify session.json was created
            session_file = session_dir / 'session.json'
            self.assertTrue(session_file.exists())
            
            # Verify session metadata
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            self.assertEqual(session_data['session_id'], session_id)
            self.assertEqual(session_data['request'], request_content)
            self.assertEqual(session_data['status'], 'completed')

    def test_skill_invocation_through_orchestration(self):
        """Test skill invocation through orchestration engine"""
        session_id = 'INT-002'
        request_content = 'Test skill invocation'
        
        # Track skill invocations
        invoked_skills = []
        
        def mock_invoke_skill(skill_name, context, workspace, **kwargs):
            invoked_skills.append(skill_name)
            return SkillInvocationResult(
                success=True,
                session_id='skill-{}'.format(session_id),
                output='{} executed successfully'.format(skill_name),
                error=None
            )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content
                )
            
            # Verify all skills were invoked in order
            self.assertEqual(invoked_skills, ['brainstorming', 'test-driven-development', 'requesting-code-review'])
            
            # Verify context was passed correctly
            self.assertEqual(results['final_status'], 'completed')

    def test_gate_decision_flow_approve(self):
        """Test gate decision flow with approve decision"""
        session_id = 'INT-003'
        request_content = 'Test gate approval'
        
        # Create manifest with gate
        gate_manifest = {
            'name': 'gate-test',
            'description': 'Test gate flow',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'stage1',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md'],
                    'gate': 'g1_approval'
                }
            ]
        }
        
        gate_manifest_path = self.workflows_dir / 'gate-test.yaml'
        with open(gate_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(gate_manifest, f)
        
        # Mock skill invoker
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Success',
                    error=None
                )
                
                # Mock gate handler to return approve
                with patch.object(self.engine, '_handle_gate') as mock_gate:
                    mock_gate.return_value = {
                        'gate_id': 'g1_approval',
                        'verdict': 'approve',
                        'blocked': False
                    }
                    
                    results = self.engine.execute_workflow(
                        gate_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Verify gate was called and workflow completed
                    mock_gate.assert_called_once()
                    self.assertEqual(results['final_status'], 'completed')

    def test_gate_decision_flow_block(self):
        """Test gate decision flow with block decision"""
        session_id = 'INT-004'
        request_content = 'Test gate block'
        
        gate_manifest = {
            'name': 'gate-block-test',
            'description': 'Test gate block',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'stage1',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md'],
                    'gate': 'g1_approval'
                }
            ]
        }
        
        gate_manifest_path = self.workflows_dir / 'gate-block-test.yaml'
        with open(gate_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(gate_manifest, f)
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Success',
                    error=None
                )
                
                # Mock gate handler to return block
                with patch.object(self.engine, '_handle_gate') as mock_gate:
                    mock_gate.return_value = {
                        'gate_id': 'g1_approval',
                        'verdict': 'block',
                        'blocked': True
                    }
                    
                    results = self.engine.execute_workflow(
                        gate_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Verify workflow was blocked
                    self.assertEqual(results['final_status'], 'blocked')

    def test_retry_loop_with_actual_corrections(self):
        """Test retry loop with actual correction artifacts"""
        session_id = 'INT-005'
        request_content = 'Test retry with corrections'
        
        retry_manifest = {
            'name': 'retry-test',
            'description': 'Test retry loop',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        retry_manifest_path = self.workflows_dir / 'retry-test.yaml'
        with open(retry_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(retry_manifest, f)
        
        call_count = [0]
        correction_artifacts = []
        
        def mock_invoke_skill(skill_name, context, workspace, correction_artifact=None, **kwargs):
            call_count[0] += 1
            correction_artifacts.append(correction_artifact)
            
            # First call fails validation, second succeeds
            if call_count[0] == 1:
                # Create invalid artifact
                artifact_path = Path(workspace) / 'design.md'
                artifact_path.write_text('TODO: implement design')
                
                return SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Initial attempt',
                    error=None
                )
            else:
                # Create valid artifact
                artifact_path = Path(workspace) / 'design.md'
                artifact_path.write_text('# Design\n\nComplete design specification.')
                
                return SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Corrected attempt',
                    error=None
                )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                with patch('time.sleep'):  # Mock sleep to speed up test
                    results = self.engine.execute_workflow(
                        retry_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Verify retry occurred
                    self.assertEqual(call_count[0], 2)
                    
                    # Verify correction artifact was created and passed
                    self.assertIsNone(correction_artifacts[0])
                    self.assertIsNotNone(correction_artifacts[1])
                    self.assertIn('correction-', correction_artifacts[1])
                    
                    # Verify workflow completed after retry
                    self.assertEqual(results['final_status'], 'completed')

    def test_retry_loop_max_retries_exceeded(self):
        """Test retry loop when max retries exceeded"""
        session_id = 'INT-006'
        request_content = 'Test max retries'
        
        retry_manifest = {
            'name': 'max-retry-test',
            'description': 'Test max retries exceeded',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        retry_manifest_path = self.workflows_dir / 'max-retry-test.yaml'
        with open(retry_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(retry_manifest, f)
        
        def mock_invoke_skill(skill_name, context, workspace, **kwargs):
            # Always create invalid artifact
            artifact_path = Path(workspace) / 'design.md'
            artifact_path.write_text('TODO: implement design')
            
            return SkillInvocationResult(
                success=True,
                session_id='skill-{}'.format(session_id),
                output='Failed attempt',
                error=None
            )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                with patch('time.sleep'):  # Mock sleep to speed up test
                    results = self.engine.execute_workflow(
                        retry_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Verify workflow escalated after max retries
                    self.assertEqual(results['final_status'], 'escalated')

    def test_session_management_across_stages(self):
        """Test session management across multiple stages"""
        session_id = 'INT-007'
        request_content = 'Test session management'
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Stage completed',
                    error=None
                )
                
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content
                )
            
            # Verify session directory structure
            session_dir = self.work_dir / session_id
            self.assertTrue(session_dir.exists())
            
            # Verify session.json contains all stage updates
            session_file = session_dir / 'session.json'
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Verify all stages were recorded
            self.assertEqual(len(session_data['stages']), 3)
            
            # Verify status progression
            stage_statuses = [stage['status'] for stage in session_data['stages']]
            self.assertEqual(stage_statuses, ['completed', 'completed', 'completed'])
            
            # Verify audit log was populated
            self.assertGreater(len(session_data['audit_log']), 0)
            
            # Verify final status
            self.assertEqual(session_data['status'], 'completed')

    def test_session_management_with_failures(self):
        """Test session management when stages fail"""
        session_id = 'INT-008'
        request_content = 'Test session management with failures'
        
        failure_manifest = {
            'name': 'failure-test',
            'description': 'Test failure handling',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        failure_manifest_path = self.workflows_dir / 'failure-test.yaml'
        with open(failure_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(failure_manifest, f)
        
        def mock_invoke_skill(skill_name, context, workspace, **kwargs):
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error='Skill execution failed'
            )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                results = self.engine.execute_workflow(
                    failure_manifest_path,
                    session_id,
                    request_content
                )
            
            # Verify session recorded failure
            session_dir = self.work_dir / session_id
            session_file = session_dir / 'session.json'
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Verify failure status
            self.assertEqual(session_data['status'], 'escalated')
            
            # Verify failure was recorded in stages
            self.assertEqual(len(session_data['stages']), 1)
            self.assertEqual(session_data['stages'][0]['status'], 'failed')

    def test_config_overrides_in_workflow(self):
        """Test config overrides applied during workflow execution"""
        session_id = 'INT-009'
        request_content = 'Test config overrides'
        config_overrides = {'interactive_mode': True, 'custom_param': 'value'}
        
        override_calls = []
        
        def mock_invoke_skill(skill_name, context, workspace, config_overrides=None, **kwargs):
            override_calls.append(config_overrides)
            return SkillInvocationResult(
                success=True,
                session_id='skill-{}'.format(session_id),
                output='Stage completed',
                error=None
            )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content,
                    config_overrides=config_overrides
                )
            
            # Verify config overrides were passed to all skill invocations
            self.assertEqual(len(override_calls), 3)
            for override in override_calls:
                self.assertEqual(override, config_overrides)
            
            self.assertEqual(results['final_status'], 'completed')

    def test_skip_brainstorming_override(self):
        """Test skip_brainstorming override in workflow"""
        session_id = 'INT-010'
        request_content = 'Test skip brainstorming'
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = SkillInvocationResult(
                    success=True,
                    session_id='skill-{}'.format(session_id),
                    output='Stage completed',
                    error=None
                )
                
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content,
                    skip_brainstorming=True
                )
            
            # Verify brainstorming was skipped
            self.assertEqual(results['stages'][0]['stage'], 'brainstorming')
            self.assertEqual(results['stages'][0]['output'], 'Stage skipped - spec is clear')
            
            # Verify other stages still executed
            self.assertEqual(len(results['stages']), 3)

    def test_artifact_validation_in_workflow(self):
        """Test artifact validation during workflow execution"""
        session_id = 'INT-011'
        request_content = 'Test artifact validation'
        
        def mock_invoke_skill(skill_name, context, workspace, **kwargs):
            # Create artifacts
            if skill_name == 'brainstorming':
                artifact_path = Path(workspace) / 'design.md'
                artifact_path.write_text('# Design\n\nValid design document.')
            elif skill_name == 'test-driven-development':
                (Path(workspace) / 'implementation.md').write_text('# Implementation')
                (Path(workspace) / 'test-results.md').write_text('# Test Results\nAll tests passed.')
            elif skill_name == 'requesting-code-review':
                (Path(workspace) / 'review-findings.md').write_text('# Review\nNo issues found.')
            
            return SkillInvocationResult(
                success=True,
                session_id='skill-{}'.format(session_id),
                output='Stage completed',
                error=None
            )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content
                )
            
            # Verify all stages passed validation
            for stage in results['stages']:
                self.assertTrue(stage['validation']['valid'])
                self.assertEqual(len(stage['validation']['errors']), 0)

    def test_artifact_validation_failure_triggers_retry(self):
        """Test artifact validation failure triggers retry"""
        session_id = 'INT-012'
        request_content = 'Test validation failure'
        
        validation_manifest = {
            'name': 'validation-test',
            'description': 'Test validation failure',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'validation_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        validation_manifest_path = self.workflows_dir / 'validation-test.yaml'
        with open(validation_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(validation_manifest, f)
        
        call_count = [0]
        
        def mock_invoke_skill(skill_name, context, workspace, **kwargs):
            call_count[0] += 1
            artifact_path = Path(workspace) / 'design.md'
            
            if call_count[0] == 1:
                # First call creates invalid artifact
                artifact_path.write_text('TODO: implement')
            else:
                # Second call creates valid artifact
                artifact_path.write_text('# Design\n\nValid design.')
            
            return SkillInvocationResult(
                success=True,
                session_id='skill-{}'.format(session_id),
                output='Stage completed',
                error=None
            )
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                with patch('time.sleep'):
                    results = self.engine.execute_workflow(
                        validation_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Verify retry was triggered
                    self.assertEqual(call_count[0], 2)
                    self.assertEqual(results['final_status'], 'completed')

    def test_exponential_backoff_in_retry(self):
        """Test exponential backoff in retry loop"""
        session_id = 'INT-013'
        request_content = 'Test exponential backoff'
        
        retry_manifest = {
            'name': 'backoff-test',
            'description': 'Test exponential backoff',
            'version': '1.0.0',
            'schema_version': 1,
            'session_shape': 'feature',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'retry_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        retry_manifest_path = self.workflows_dir / 'backoff-test.yaml'
        with open(retry_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(retry_manifest, f)
        
        call_count = [0]
        sleep_times = []
        
        def mock_invoke_skill(skill_name, context, workspace, **kwargs):
            call_count[0] += 1
            artifact_path = Path(workspace) / 'design.md'
            
            if call_count[0] < 3:
                # First two calls fail
                artifact_path.write_text('TODO: implement')
            else:
                # Third call succeeds
                artifact_path.write_text('# Design\n\nValid design.')
            
            return SkillInvocationResult(
                success=True,
                session_id='skill-{}'.format(session_id),
                output='Stage completed',
                error=None
            )
        
        def mock_sleep(seconds):
            sleep_times.append(seconds)
        
        with patch('orchestration_engine.load_skill', side_effect=self._mock_load_skill):
            with patch.object(self.engine.skill_invoker, 'invoke_skill', side_effect=mock_invoke_skill):
                with patch('time.sleep', side_effect=mock_sleep):
                    results = self.engine.execute_workflow(
                        retry_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Verify exponential backoff: 2^1, 2^2
                    self.assertEqual(sleep_times, [2, 4])
                    self.assertEqual(results['final_status'], 'completed')


class TestSkillLoadingIntegration(unittest.TestCase):
    """Integration tests for skill loading in workflow context"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.skills_dir = self.temp_path / 'skills'
        self.skills_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_load_skill_separate_format(self):
        """Test loading skill in separate format (YAML + MD)"""
        skill_name = 'test-skill'
        
        # Create separate format skill files
        yaml_content = 'schema_version: 1\nname: test-skill\ndescription: Test skill\niron_law: "TEST IRON LAW"\ntriggers: [test]\nchecklist: []\nterminal_state: completed\nannouncement: "Using test skill"\nred_flags: []\n'
        md_content = '# Test Skill\n\n## Overview\nTest skill description.\n\n## The Iron Law\nTEST IRON LAW\n'
        
        (self.skills_dir / (skill_name + '.yaml')).write_text(yaml_content)
        (self.skills_dir / (skill_name + '.md')).write_text(md_content)
        
        # Load skill
        skill_data = load_skill(self.skills_dir, skill_name)
        
        # Verify skill data
        self.assertEqual(skill_data['definition']['name'], skill_name)
        self.assertEqual(skill_data['definition']['iron_law'], 'TEST IRON LAW')
        self.assertIn('Test skill description', skill_data['narrative'])
        self.assertEqual(skill_data['format'], 'separate')

    def test_load_skill_single_format(self):
        """Test loading skill in single format (MD with frontmatter)"""
        skill_name = 'single-skill'
        
        # Create single format skill file
        content = '''---
schema_version: 1
name: single-skill
description: Single format skill
iron_law: "SINGLE FORMAT IRON LAW"
triggers: [test]
checklist: []
terminal_state: completed
announcement: "Using single format skill"
red_flags: []
---
# Single Format Skill

## Overview
Single format skill description.

## The Iron Law
SINGLE FORMAT IRON LAW
'''
        
        (self.skills_dir / (skill_name + '.md')).write_text(content)
        
        # Load skill
        skill_data = load_skill(self.skills_dir, skill_name)
        
        # Verify skill data
        self.assertEqual(skill_data['definition']['name'], skill_name)
        self.assertEqual(skill_data['definition']['iron_law'], 'SINGLE FORMAT IRON LAW')
        self.assertIn('Single format skill description', skill_data['narrative'])
        self.assertEqual(skill_data['format'], 'single')

    def test_load_skill_subdirectory_format(self):
        """Test loading skill from subdirectory"""
        skill_name = 'subdir-skill'
        skill_subdir = self.skills_dir / skill_name
        skill_subdir.mkdir()
        
        # Create skill files in subdirectory
        yaml_content = 'schema_version: 1\nname: subdir-skill\ndescription: Subdirectory skill\niron_law: "SUBDIR IRON LAW"\ntriggers: [test]\nchecklist: []\nterminal_state: completed\nannouncement: "Using subdir skill"\nred_flags: []\n'
        md_content = '# Subdir Skill\n\n## Overview\nSubdirectory skill description.\n'
        
        (skill_subdir / (skill_name + '.yaml')).write_text(yaml_content)
        (skill_subdir / (skill_name + '.md')).write_text(md_content)
        
        # Load skill
        skill_data = load_skill(self.skills_dir, skill_name)
        
        # Verify skill data
        self.assertEqual(skill_data['definition']['name'], skill_name)
        self.assertEqual(skill_data['definition']['iron_law'], 'SUBDIR IRON LAW')
        self.assertIn('Subdirectory skill description', skill_data['narrative'])


class TestManifestLoadingIntegration(unittest.TestCase):
    """Integration tests for manifest loading in workflow context"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.workflows_dir = self.temp_path / 'workflows'
        self.workflows_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_load_valid_manifest(self):
        """Test loading a valid manifest"""
        manifest_content = 'name: test-workflow\ndescription: Test workflow\nversion: 1.0.0\nschema_version: 1\nsession_shape: feature\nskip_brainstorming: false\nstages:\n  - name: brainstorming\n    skill: brainstorming\n    output_artifacts: [design.md]\n    gate: none\n'
        manifest_path = self.workflows_dir / 'test.yaml'
        manifest_path.write_text(manifest_content)
        
        # Load manifest
        manifest = load_manifest(manifest_path)
        
        # Verify manifest data
        self.assertEqual(manifest['name'], 'test-workflow')
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual(len(manifest['stages']), 1)
        self.assertEqual(manifest['stages'][0]['name'], 'brainstorming')

    def test_load_manifest_with_gates(self):
        """Test loading manifest with gates"""
        manifest_content = 'name: gated-workflow\ndescription: Workflow with gates\nversion: 1.0.0\nschema_version: 1\nsession_shape: feature\nskip_brainstorming: false\nstages:\n  - name: stage1\n    skill: brainstorming\n    output_artifacts: [design.md]\n    gate: g1_approval\ngates:\n  - id: g1_approval\n    name: Design Approval\n    description: Approve design\n    type: human\n'
        manifest_path = self.workflows_dir / 'gated.yaml'
        manifest_path.write_text(manifest_content)
        
        # Load manifest
        manifest = load_manifest(manifest_path)
        
        # Verify manifest includes gates
        self.assertEqual(manifest['name'], 'gated-workflow')
        self.assertEqual(len(manifest['gates']), 1)
        self.assertEqual(manifest['gates'][0]['id'], 'g1_approval')


if __name__ == '__main__':
    unittest.main()

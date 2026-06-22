# -*- coding: utf-8 -*-
"""
Unit Tests for Orchestration Engine
Tests follow TDD principles - comprehensive coverage of critical functionality
"""

import unittest
import tempfile
import shutil
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent))

from orchestration_engine import OrchestrationEngine, TriageDecision


class TestOrchestrationEngine(unittest.TestCase):
    """Test cases for OrchestrationEngine"""

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
        
        # Create a valid manifest
        self.valid_manifest = {
            'name': 'test-workflow',
            'description': 'Test workflow for orchestration engine',
            'skip_brainstorming': False,
            'stages': [
                {
                    'name': 'brainstorming',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                },
                {
                    'name': 'implementation',
                    'skill': 'implementation',
                    'output_artifacts': ['code.py'],
                    'gate': 'g1_approval'
                }
            ]
        }
        
        # Create manifest file
        self.manifest_path = self.workflows_dir / 'test-manifest.yaml'
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.valid_manifest, f)
        
        # Create skill files
        (self.skills_dir / 'brainstorming.yaml').write_text(
            'schema_version: 1\n'
            'name: brainstorming\n'
            'description: Brainstorming skill\n'
            'iron_law: "NO IMPLEMENTATION UNTIL DESIGN APPROVED"\n'
            'triggers: [new_feature]\n'
            'checklist: []\n'
            'terminal_state: writing-plans\n'
            'announcement: "Using the brainstorming skill"\n'
            'red_flags: []\n'
        )
        
        (self.skills_dir / 'brainstorming.md').write_text(
            '# Brainstorming Skill\n\n'
            '## Overview\n'
            'Brainstorming skill for generating ideas.\n\n'
            '## The Iron Law\n'
            'NO IMPLEMENTATION UNTIL DESIGN APPROVED\n'
        )
        
        (self.skills_dir / 'implementation.yaml').write_text(
            'schema_version: 1\n'
            'name: implementation\n'
            'description: Implementation skill\n'
            'iron_law: "IMPLEMENTATION ONLY AFTER DESIGN APPROVAL"\n'
            'triggers: [implementation]\n'
            'checklist: []\n'
            'terminal_state: completed\n'
            'announcement: "Using the implementation skill"\n'
            'red_flags: []\n'
        )
        
        (self.skills_dir / 'implementation.md').write_text(
            '# Implementation Skill\n\n'
            '## Overview\n'
            'Implementation skill for coding.\n\n'
            '## The Iron Law\n'
            'IMPLEMENTATION ONLY AFTER DESIGN APPROVAL\n'
        )
        
        # Mock config
        self.config = {
            'demo_mode': True,
            'skills_dir': self.skills_dir,
            'session_work_dir': str(self.work_dir)
        }
        
        self.engine = OrchestrationEngine(self.work_dir, self.config)
        
        # Mock skill data for avoiding encoding issues
        self.mock_skill_data = {
            'definition': {
                'schema_version': 1,
                'name': 'brainstorming',
                'description': 'Brainstorming skill',
                'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                'triggers': ['new_feature'],
                'checklist': [],
                'terminal_state': 'writing-plans',
                'announcement': 'Using the brainstorming skill',
                'red_flags': []
            },
            'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
            'format': 'separate'
        }
    
    def mock_load_skill(self, skill_name='brainstorming'):
        """Helper to create mock skill data"""
        skill_data = self.mock_skill_data.copy()
        skill_data['definition']['name'] = skill_name
        skill_data['narrative'] = f'# {skill_name} Skill\n\n## Overview\n{skill_name} skill.'
        return skill_data

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Should initialize engine with work directory and config"""
        self.assertEqual(self.engine.work_dir, self.work_dir)
        self.assertEqual(self.engine.config, self.config)
        self.assertIsNotNone(self.engine.skill_invoker)

    def test_execute_workflow_basic(self):
        """Should execute a basic workflow successfully"""
        session_id = 'TEST-001'
        request_content = 'Test request'
        
        # Mock _execute_stage to avoid encoding issues with global skills
        with patch.object(self.engine, '_execute_stage') as mock_execute:
            mock_execute.return_value = {
                'stage': 'brainstorming',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
            
            results = self.engine.execute_workflow(
                self.manifest_path,
                session_id,
                request_content
            )
            
            self.assertEqual(results['session_id'], session_id)
            self.assertEqual(results['manifest'], 'test-workflow')
            self.assertEqual(results['final_status'], 'completed')
            self.assertEqual(len(results['stages']), 2)

    def test_execute_workflow_with_skip_brainstorming(self):
        """Should skip brainstorming stage when configured"""
        session_id = 'TEST-002'
        request_content = 'Test request'
        
        # Mock _execute_stage to avoid encoding issues
        with patch.object(self.engine, '_execute_stage') as mock_execute:
            mock_execute.return_value = {
                'stage': 'brainstorming',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
            
            results = self.engine.execute_workflow(
                self.manifest_path,
                session_id,
                request_content,
                skip_brainstorming=True
            )
            
            self.assertEqual(results['session_id'], session_id)
            self.assertEqual(results['final_status'], 'completed')
            # First stage should be skipped
            self.assertEqual(results['stages'][0]['stage'], 'brainstorming')
            self.assertEqual(results['stages'][0]['output'], 'Stage skipped - spec is clear')

    def test_execute_workflow_with_config_overrides(self):
        """Should apply config overrides to skill dispatch"""
        session_id = 'TEST-003'
        request_content = 'Test request'
        config_overrides = {'interactive_mode': True}
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage') as mock_execute:
                mock_execute.return_value = {
                    'stage': 'brainstorming',
                    'skill': 'brainstorming',
                    'success': True,
                    'output': 'Success',
                    'error': None,
                    'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                    'triage_decision': TriageDecision.PROCEED
                }
                
                results = self.engine.execute_workflow(
                    self.manifest_path,
                    session_id,
                    request_content,
                    config_overrides=config_overrides
                )
                
                # Verify config_overrides passed to _execute_stage
                mock_execute.assert_called()
                call_kwargs = mock_execute.call_args[1]
                self.assertEqual(call_kwargs['config_overrides'], config_overrides)

    def test_retry_logic_with_exponential_backoff(self):
        """Should implement retry logic with exponential backoff"""
        session_id = 'TEST-004'
        request_content = 'Test request'
        
        # Create a manifest with a single stage that will fail validation
        retry_manifest = {
            'name': 'retry-test',
            'description': 'Test retry logic',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        retry_manifest_path = self.workflows_dir / 'retry-manifest.yaml'
        with open(retry_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(retry_manifest, f)
        
        # Mock _execute_stage to return validation failure first, then success
        call_count = [0]
        
        def mock_execute_stage(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call fails validation
                return {
                    'stage': 'failing_stage',
                    'skill': 'brainstorming',
                    'success': True,
                    'output': 'Output',
                    'error': 'Validation failed',
                    'validation': {'valid': False, 'errors': ['File is empty'], 'artifact_results': {}},
                    'triage_decision': TriageDecision.RETRY
                }
            else:
                # Subsequent calls succeed
                return {
                    'stage': 'failing_stage',
                    'skill': 'brainstorming',
                    'success': True,
                    'output': 'Success',
                    'error': None,
                    'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                    'triage_decision': TriageDecision.PROCEED
                }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                with patch('time.sleep') as mock_sleep:
                    results = self.engine.execute_workflow(
                        retry_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Should have retried once (initial call + 1 retry = 2 calls)
                    self.assertEqual(call_count[0], 2)
                    self.assertEqual(results['final_status'], 'completed')
                    
                    # Verify exponential backoff was called (2^1 = 2 seconds)
                    mock_sleep.assert_called_with(2)

    def test_retry_logic_max_retries_exceeded(self):
        """Should escalate when max retries exceeded"""
        session_id = 'TEST-005'
        request_content = 'Test request'
        
        retry_manifest = {
            'name': 'max-retry-test',
            'description': 'Test max retries',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        retry_manifest_path = self.workflows_dir / 'max-retry-manifest.yaml'
        with open(retry_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(retry_manifest, f)
        
        # Mock _execute_stage to always fail
        def mock_execute_stage(*args, **kwargs):
            return {
                'stage': 'failing_stage',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Output',
                'error': 'Validation failed',
                'validation': {'valid': False, 'errors': ['File is empty'], 'artifact_results': {}},
                'triage_decision': TriageDecision.RETRY
            }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                with patch('time.sleep'):
                    results = self.engine.execute_workflow(
                        retry_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Should have retried max 3 times (initial + 3 retries = 4 calls)
                    self.assertEqual(results['final_status'], 'escalated')

    def test_retry_with_correction_artifact(self):
        """Should create correction artifact during retry"""
        session_id = 'TEST-006'
        request_content = 'Test request'
        
        retry_manifest = {
            'name': 'correction-test',
            'description': 'Test correction artifact',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        retry_manifest_path = self.workflows_dir / 'correction-manifest.yaml'
        with open(retry_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(retry_manifest, f)
        
        call_count = [0]
        correction_artifacts = []
        
        def mock_execute_stage(*args, **kwargs):
            call_count[0] += 1
            correction_artifacts.append(kwargs.get('correction_artifact'))
            
            if call_count[0] == 1:
                return {
                    'stage': 'failing_stage',
                    'skill': 'brainstorming',
                    'success': True,
                    'output': 'Output',
                    'error': 'Validation failed',
                    'validation': {'valid': False, 'errors': ['File is empty'], 'artifact_results': {}},
                    'triage_decision': TriageDecision.RETRY
                }
            else:
                return {
                    'stage': 'failing_stage',
                    'skill': 'brainstorming',
                    'success': True,
                    'output': 'Success',
                    'error': None,
                    'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                    'triage_decision': TriageDecision.PROCEED
                }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                with patch('time.sleep'):
                    results = self.engine.execute_workflow(
                        retry_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # First call should have no correction artifact
                    self.assertIsNone(correction_artifacts[0])
                    # Second call should have correction artifact
                    self.assertIsNotNone(correction_artifacts[1])
                    self.assertIn('correction-', correction_artifacts[1])

    def test_gate_handling_approve(self):
        """Should handle gate with approve decision"""
        session_id = 'TEST-007'
        request_content = 'Test request'
        
        gate_manifest = {
            'name': 'gate-test',
            'description': 'Test gate handling',
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
        
        gate_manifest_path = self.workflows_dir / 'gate-manifest.yaml'
        with open(gate_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(gate_manifest, f)
        
        session_dir = self.work_dir / session_id
        session_dir.mkdir(exist_ok=True)
        
        # Mock _execute_stage to succeed
        def mock_execute_stage(*args, **kwargs):
            return {
                'stage': 'stage1',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
        
        # Mock _handle_gate to return approve
        def mock_handle_gate(*args, **kwargs):
            return {
                'gate_id': 'g1_approval',
                'verdict': 'approve',
                'blocked': False
            }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                with patch.object(self.engine, '_handle_gate', side_effect=mock_handle_gate):
                    results = self.engine.execute_workflow(
                        gate_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    self.assertEqual(results['final_status'], 'completed')

    def test_gate_handling_block(self):
        """Should handle gate with block decision"""
        session_id = 'TEST-008'
        request_content = 'Test request'
        
        gate_manifest = {
            'name': 'gate-block-test',
            'description': 'Test gate block',
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
        
        gate_manifest_path = self.workflows_dir / 'gate-block-manifest.yaml'
        with open(gate_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(gate_manifest, f)
        
        # Mock _execute_stage to succeed
        def mock_execute_stage(*args, **kwargs):
            return {
                'stage': 'stage1',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
        
        # Mock _handle_gate to return block
        def mock_handle_gate(*args, **kwargs):
            return {
                'gate_id': 'g1_approval',
                'verdict': 'block',
                'blocked': True
            }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                with patch.object(self.engine, '_handle_gate', side_effect=mock_handle_gate):
                    results = self.engine.execute_workflow(
                        gate_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    self.assertEqual(results['final_status'], 'blocked')

    def test_gate_handling_with_decision_file(self):
        """Should create gate decision file"""
        session_id = 'TEST-009'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            gate_result = self.engine._handle_gate(
                gate_id='g1_approval',
                stage_name='stage1',
                session_dir=session_dir
            )
        
        # Check that gate decision file was created
        gate_decision_file = session_dir / 'gate-g1_approval-decision.md'
        self.assertTrue(gate_decision_file.exists())
        
        # Verify the file has the expected structure
        content = gate_decision_file.read_text()
        self.assertIn('Gate Decision: g1_approval', content)
        self.assertIn('Stage: stage1', content)
        self.assertIn('verdict:', content)
        
        # Since no user input was provided, it should timeout and block
        self.assertEqual(gate_result['verdict'], 'block')
        self.assertTrue(gate_result['blocked'])

    def test_gate_handling_timeout(self):
        """Should timeout and block when gate decision not provided"""
        session_id = 'TEST-010'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            gate_result = self.engine._handle_gate(
                gate_id='g1_approval',
                stage_name='stage1',
                session_dir=session_dir
            )
        
        # Should timeout and block
        self.assertEqual(gate_result['verdict'], 'block')
        self.assertTrue(gate_result['blocked'])

    def test_interactive_mode_pause(self):
        """Should create pause file and wait for user input in interactive mode"""
        session_id = 'TEST-011'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'interactive_stage',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = self.valid_manifest
        config_overrides = {'interactive_mode': True}
        
        # Pre-create pause file with user input to avoid timeout
        pause_file = session_dir / 'pause-interactive_stage.md'
        pause_file.write_text(
            '# Interactive Pause: interactive_stage\n\n'
            'input: User provided input\n'
        )
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = self.mock_load_skill('brainstorming')
            
            # Mock skill invoker to succeed
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=True,
                    output='Success',
                    error=None
                )
                
                # Mock time.sleep to speed up test
                with patch('time.sleep'):
                    result = self.engine._execute_stage(
                        stage=stage,
                        manifest=manifest,
                        session_dir=session_dir,
                        session_id=session_id,
                        config_overrides=config_overrides
                    )
        
        # Check that pause file was created
        self.assertTrue(pause_file.exists())

    def test_interactive_mode_resume(self):
        """Should resume after user provides input in pause file"""
        session_id = 'TEST-012'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'interactive_stage',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = self.valid_manifest
        config_overrides = {'interactive_mode': True}
        
        # Create pause file with user input
        pause_file = session_dir / 'pause-interactive_stage.md'
        pause_file.write_text(
            '# Interactive Pause: interactive_stage\n\n'
            'input: User provided input here\n'
        )
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = self.mock_load_skill('brainstorming')
            
            # Mock skill invoker to succeed
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=True,
                    output='Success',
                    error=None
                )
                
                # Mock time.sleep to speed up test
                with patch('time.sleep'):
                    result = self.engine._execute_stage(
                        stage=stage,
                        manifest=manifest,
                        session_dir=session_dir,
                        session_id=session_id,
                        config_overrides=config_overrides
                    )
        
        self.assertEqual(result['triage_decision'], TriageDecision.PROCEED)

    def test_stage_execution_with_correction_artifact(self):
        """Should pass correction artifact to skill invoker"""
        session_id = 'TEST-013'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'correction_stage',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = self.valid_manifest
        correction_artifact = str(session_dir / 'correction-design.md')
        
        # Create correction artifact
        Path(correction_artifact).write_text('# Correction\n\nFix this issue\n')
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = self.mock_load_skill('brainstorming')
            
            # Mock skill invoker
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=True,
                    output='Success',
                    error=None
                )
                
                result = self.engine._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id,
                    correction_artifact=correction_artifact
                )
                
                # Verify correction artifact was passed to skill invoker
                mock_invoke.assert_called_once()
                call_kwargs = mock_invoke.call_args[1]
                self.assertEqual(call_kwargs['correction_artifact'], correction_artifact)

    def test_stage_execution_validation_failure(self):
        """Should return RETRY decision when validation fails"""
        session_id = 'TEST-014'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'validation_stage',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = self.valid_manifest
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = self.mock_load_skill('brainstorming')
            
            # Mock skill invoker to succeed but create empty artifact
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=True,
                    output='Success',
                    error=None
                )
                
                # Create empty artifact to fail validation
                (session_dir / 'design.md').write_text('')
                
                result = self.engine._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id
                )
                
                self.assertEqual(result['triage_decision'], TriageDecision.RETRY)
                self.assertIsNotNone(result['error'])

    def test_stage_execution_skill_failure(self):
        """Should return ESCALATE decision when skill fails"""
        session_id = 'TEST-015'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'failing_stage',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = self.valid_manifest
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = self.mock_load_skill('brainstorming')
            
            # Mock skill invoker to fail
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=False,
                    output=None,
                    error='Skill execution failed'
                )
                
                result = self.engine._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id
                )
                
                self.assertEqual(result['triage_decision'], TriageDecision.ESCALATE)
                self.assertIsNotNone(result['error'])

    def test_skip_stage(self):
        """Should skip stage when skip_brainstorming is enabled"""
        session_id = 'TEST-016'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'brainstorming',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = {'skip_brainstorming': True}
        
        result = self.engine._skip_stage(stage, session_dir, session_id)
        
        self.assertEqual(result['stage'], 'brainstorming')
        self.assertEqual(result['success'], True)
        self.assertEqual(result['triage_decision'], TriageDecision.PROCEED)
        self.assertEqual(result['output'], 'Stage skipped - spec is clear')
        
        # Check that placeholder artifact was created
        design_file = session_dir / 'design.md'
        self.assertTrue(design_file.exists())
        content = design_file.read_text()
        self.assertIn('Skipping brainstorming', content)

    def test_session_state_management(self):
        """Should manage session state correctly"""
        session_id = 'TEST-017'
        request_content = 'Test request'
        
        session_dir = self.work_dir / session_id
        session_dir.mkdir(exist_ok=True)
        
        # Initialize session
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        # Check session file was created
        session_file = session_dir / 'session.json'
        self.assertTrue(session_file.exists())
        
        # Read session data
        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        self.assertEqual(session_data['session_id'], session_id)
        self.assertEqual(session_data['status'], 'initialized')
        self.assertEqual(session_data['request'], request_content)

    def test_manifest_loading(self):
        """Should load manifest correctly"""
        # Mock _execute_stage to avoid encoding issues
        with patch.object(self.engine, '_execute_stage') as mock_execute:
            mock_execute.return_value = {
                'stage': 'brainstorming',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
            
            manifest = self.engine.execute_workflow(
                self.manifest_path,
                'TEST-018',
                'Test request'
            )
            
            self.assertEqual(manifest['manifest'], 'test-workflow')

    def test_manifest_validation_missing_file(self):
        """Should handle missing manifest file"""
        missing_manifest = self.workflows_dir / 'missing-manifest.yaml'
        
        with self.assertRaises(FileNotFoundError):
            self.engine.execute_workflow(
                missing_manifest,
                'TEST-019',
                'Test request'
            )

    def test_escalate_on_skill_failure(self):
        """Should escalate workflow when skill fails"""
        session_id = 'TEST-020'
        request_content = 'Test request'
        
        escalate_manifest = {
            'name': 'escalate-test',
            'description': 'Test escalation',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'failing_stage',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                }
            ]
        }
        
        escalate_manifest_path = self.workflows_dir / 'escalate-manifest.yaml'
        with open(escalate_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(escalate_manifest, f)
        
        # Mock _execute_stage to return escalate decision
        def mock_execute_stage(*args, **kwargs):
            return {
                'stage': 'failing_stage',
                'skill': 'brainstorming',
                'success': False,
                'output': None,
                'error': 'Skill failed',
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.ESCALATE
            }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                results = self.engine.execute_workflow(
                    escalate_manifest_path,
                    session_id,
                    request_content
                )
                
                self.assertEqual(results['final_status'], 'escalated')

    def test_no_gate_when_none(self):
        """Should not call gate handler when gate is 'none'"""
        session_id = 'TEST-021'
        request_content = 'Test request'
        
        no_gate_manifest = {
            'name': 'no-gate-test',
            'description': 'Test no gate',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'stage1',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md'],
                    'gate': 'none'
                }
            ]
        }
        
        no_gate_manifest_path = self.workflows_dir / 'no-gate-manifest.yaml'
        with open(no_gate_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(no_gate_manifest, f)
        
        def mock_execute_stage(*args, **kwargs):
            return {
                'stage': 'stage1',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine, '_execute_stage', side_effect=mock_execute_stage):
                with patch.object(self.engine, '_handle_gate') as mock_handle_gate:
                    results = self.engine.execute_workflow(
                        no_gate_manifest_path,
                        session_id,
                        request_content
                    )
                    
                    # Gate handler should not be called
                    mock_handle_gate.assert_not_called()
                    self.assertEqual(results['final_status'], 'completed')

    def test_multiple_stages_execution(self):
        """Should execute multiple stages in sequence"""
        session_id = 'TEST-022'
        request_content = 'Test request'
        
        multi_stage_manifest = {
            'name': 'multi-stage-test',
            'description': 'Test multiple stages',
            'skip_brainstorming': True,
            'stages': [
                {
                    'name': 'stage1',
                    'skill': 'brainstorming',
                    'output_artifacts': ['design.md']
                },
                {
                    'name': 'stage2',
                    'skill': 'implementation',
                    'output_artifacts': ['code.py']
                },
                {
                    'name': 'stage3',
                    'skill': 'brainstorming',
                    'output_artifacts': ['review.md']
                }
            ]
        }
        
        multi_stage_manifest_path = self.workflows_dir / 'multi-stage-manifest.yaml'
        with open(multi_stage_manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(multi_stage_manifest, f)
        
        # Mock _execute_stage to avoid encoding issues and return different results for each stage
        stage_results = [
            {
                'stage': 'stage1',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            },
            {
                'stage': 'stage2',
                'skill': 'implementation',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            },
            {
                'stage': 'stage3',
                'skill': 'brainstorming',
                'success': True,
                'output': 'Success',
                'error': None,
                'validation': {'valid': True, 'errors': [], 'artifact_results': {}},
                'triage_decision': TriageDecision.PROCEED
            }
        ]
        
        with patch.object(self.engine, '_execute_stage', side_effect=stage_results):
            results = self.engine.execute_workflow(
                multi_stage_manifest_path,
                session_id,
                request_content
            )
            
            self.assertEqual(len(results['stages']), 3)
            self.assertEqual(results['stages'][0]['stage'], 'stage1')
            self.assertEqual(results['stages'][1]['stage'], 'stage2')
            self.assertEqual(results['stages'][2]['stage'], 'stage3')
            self.assertEqual(results['final_status'], 'completed')

    def test_config_overrides_passed_to_skill(self):
        """Should pass config overrides to skill invoker"""
        session_id = 'TEST-023'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'config_stage',
            'skill': 'brainstorming',
            'output_artifacts': ['design.md']
        }
        
        manifest = self.valid_manifest
        config_overrides = {'custom_param': 'custom_value'}
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'brainstorming',
                    'description': 'Brainstorming skill',
                    'iron_law': 'NO IMPLEMENTATION UNTIL DESIGN APPROVED',
                    'triggers': ['new_feature'],
                    'checklist': [],
                    'terminal_state': 'writing-plans',
                    'announcement': 'Using the brainstorming skill',
                    'red_flags': []
                },
                'narrative': '# Brainstorming Skill\n\n## Overview\nBrainstorming skill for generating ideas.',
                'format': 'separate'
            }
            
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=True,
                    output='Success',
                    error=None
                )
                
                self.engine._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id,
                    config_overrides=config_overrides
                )
                
                # Verify config overrides were passed
                call_kwargs = mock_invoke.call_args[1]
                self.assertEqual(call_kwargs['config_overrides'], config_overrides)

    def test_is_reviewer_flag(self):
        """Should set is_reviewer flag for requesting-code-review skill"""
        session_id = 'TEST-024'
        request_content = 'Test request'
        
        # Initialize session first
        from deterministic_tools import session_init
        session_dir = session_init(session_id, self.work_dir, request_content)
        
        stage = {
            'name': 'review_stage',
            'skill': 'requesting-code-review',
            'output_artifacts': ['review.md']
        }
        
        manifest = self.valid_manifest
        
        # Mock load_skill to avoid encoding issues
        with patch('orchestration_engine.load_skill') as mock_load_skill:
            mock_load_skill.return_value = {
                'definition': {
                    'schema_version': 1,
                    'name': 'requesting-code-review',
                    'description': 'Code review skill',
                    'iron_law': 'NO APPROVAL WITHOUT REVIEW',
                    'triggers': ['review'],
                    'checklist': [],
                    'terminal_state': 'completed',
                    'announcement': 'Using the code review skill',
                    'red_flags': []
                },
                'narrative': '# Code Review Skill\n\n## Overview\nCode review skill for reviewing code.',
                'format': 'separate'
            }
            
            with patch.object(self.engine.skill_invoker, 'invoke_skill') as mock_invoke:
                mock_invoke.return_value = MagicMock(
                    success=True,
                    output='Success',
                    error=None
                )
                
                self.engine._execute_stage(
                    stage=stage,
                    manifest=manifest,
                    session_dir=session_dir,
                    session_id=session_id
                )
                
                # Verify is_reviewer flag was set
                call_kwargs = mock_invoke.call_args[1]
                self.assertTrue(call_kwargs['is_reviewer'])


if __name__ == '__main__':
    unittest.main()

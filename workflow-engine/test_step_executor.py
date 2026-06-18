# -*- coding: utf-8 -*-
"""
Unit Tests for Step Executor
Tests follow TDD principles - written to validate existing implementation
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import yaml
from unittest.mock import Mock, patch
from io import StringIO

import sys
sys.path.insert(0, str(Path(__file__).parent))

from step_executor import StepExecutor, StepResult
from manifest_loader import Manifest, ManifestLoader
from session_manager import SessionManager


class TestStepExecutor(unittest.TestCase):
    """Test cases for StepExecutor"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.harness_root = self.temp_path
        self.work_dir = self.temp_path / 'work'
        self.workflows_dir = self.temp_path / 'workflows'
        self.skills_dir = self.temp_path / 'skills'
        
        self.work_dir.mkdir()
        self.workflows_dir.mkdir()
        self.skills_dir.mkdir()
        
        # Create skill files
        (self.skills_dir / 'brainstorming.yaml').write_text('schema_version: 1\nname: brainstorming\n')
        (self.skills_dir / 'brainstorming.md').write_text('# Brainstorming Skill\n')
        (self.skills_dir / 'test-driven-development.yaml').write_text('schema_version: 1\nname: test-driven-development\n')
        (self.skills_dir / 'test-driven-development.md').write_text('# TDD Skill\n')
        
        # Create a valid manifest
        self.valid_manifest = {
            'schema_version': 1,
            'session_shape': 'feature',
            'description': 'Test workflow',
            'slash_command': '/test',
            'canonical_workflow': 'workflows/test.md',
            'session_id_format': 'TEST-NNN',
            'session_init': {
                'command': 'session-init',
                'creates_workdir': 'work/<session_id>/',
                'initial_artefacts': ['request.md', 'status.md']
            },
            'auto_load': [],
            'required_artefacts': {
                'step_0': ['request.md', 'status.md'],
                'step_1': ['requirement.md'],
                'step_2': ['baseline.md']
            },
            'gates': [
                {
                    'id': 'g1_approval',
                    'after_step': 'step_1',
                    'type': 'user_gate',
                    'description': 'User approval required'
                }
            ],
            'skills': [
                {
                    'name': 'brainstorming',
                    'phases': ['step_1'],
                    'announcement': 'Using brainstorming skill'
                },
                {
                    'name': 'test-driven-development',
                    'phases': ['step_2'],
                    'announcement': 'Using TDD skill'
                }
            ],
            'branch': {
                'default': 'feature/<session_id>',
                'policy': 'implementation_branch_committable'
            }
        }
        
        manifest_path = self.workflows_dir / 'test.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.valid_manifest, f)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_execute_workflow_success(self):
        """Should execute complete workflow successfully"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        
        success = executor.execute_workflow('test.manifest.yaml', 'TEST-001')
        
        self.assertTrue(success)
        self.assertIsNotNone(executor.session_manager)
        self.assertEqual(executor.session_manager.state.status, 'completed')

    def test_execute_step_0(self):
        """Should execute session init correctly"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-002', executor.manifest)
        
        result = executor._execute_step_0()
        
        self.assertIsInstance(result, StepResult)
        self.assertTrue(result.success)
        self.assertEqual(result.step, 'step_0')
        self.assertIn('request.md', result.artifacts_created)
        self.assertIn('status.md', result.artifacts_created)

    def test_get_step_order(self):
        """Should return ordered list of steps excluding step_0"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        
        steps = executor._get_step_order()
        
        self.assertIsInstance(steps, list)
        self.assertNotIn('step_0', steps)
        self.assertIn('step_1', steps)
        self.assertIn('step_2', steps)
        # Check ordering
        self.assertEqual(steps.index('step_1'), 0)
        self.assertEqual(steps.index('step_2'), 1)

    def test_execute_step_with_skill(self):
        """Should execute step with skill invocation"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-003', executor.manifest)
        
        # Create required artifact for step_1
        session_dir = executor.session_manager.get_session_dir()
        (session_dir / 'requirement.md').write_text('# Requirement\n')
        
        result = executor._execute_step('step_1')
        
        self.assertTrue(result)

    def test_execute_step_without_skill(self):
        """Should handle steps with no assigned skills"""
        # Create manifest with step that has no skills
        manifest_dict = self.valid_manifest.copy()
        manifest_dict['skills'] = []  # No skills
        manifest_dict['required_artefacts']['step_3'] = ['design.md']
        
        manifest_path = self.workflows_dir / 'no_skills.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_dict, f)
        
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('no_skills.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-004', executor.manifest)
        
        result = executor._execute_step('step_3')
        
        self.assertTrue(result)

    def test_get_skills_for_step(self):
        """Should return correct skills for a step"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        
        skills = executor._get_skills_for_step('step_1')
        
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]['name'], 'brainstorming')
        
        skills = executor._get_skills_for_step('step_2')
        
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]['name'], 'test-driven-development')

    def test_validate_artifacts(self):
        """Should identify missing artifacts correctly"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-005', executor.manifest)
        
        # Check missing artifacts
        missing = executor._validate_artifacts(['requirement.md', 'baseline.md'])
        
        self.assertIn('requirement.md', missing)
        self.assertIn('baseline.md', missing)
        
        # Create one artifact
        session_dir = executor.session_manager.get_session_dir()
        (session_dir / 'requirement.md').write_text('# Requirement\n')
        
        # Check again
        missing = executor._validate_artifacts(['requirement.md', 'baseline.md'])
        
        self.assertNotIn('requirement.md', missing)
        self.assertIn('baseline.md', missing)

    def test_has_gate_after_step(self):
        """Should correctly identify gates after steps"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        
        self.assertTrue(executor._has_gate_after_step('step_1'))
        self.assertFalse(executor._has_gate_after_step('step_2'))

    def test_handle_user_gate_interactive(self):
        """Should handle user gate in interactive mode"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=True)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-006', executor.manifest)
        
        # Mock user input to approve
        with patch('builtins.input', return_value=''):
            result = executor._handle_gate('step_1')
        
        self.assertTrue(result)

    def test_handle_user_gate_interactive_reject(self):
        """Should handle user rejection in interactive mode"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=True)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-007', executor.manifest)
        
        # Mock user input to reject (check for 'no' as rejection signal)
        with patch('builtins.input', return_value='no'):
            result = executor._handle_gate('step_1')
        
        self.assertFalse(result)

    def test_handle_user_gate_non_interactive(self):
        """Should auto-approve user gate in non-interactive mode"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-008', executor.manifest)
        
        result = executor._handle_gate('step_1')
        
        self.assertTrue(result)

    def test_handle_auto_gate(self):
        """Should automatically pass auto gates"""
        # Create manifest with auto gate
        manifest_dict = self.valid_manifest.copy()
        manifest_dict['gates'] = [
            {
                'id': 'g_auto',
                'after_step': 'step_1',
                'type': 'auto_gate',
                'description': 'Auto gate'
            }
        ]
        
        manifest_path = self.workflows_dir / 'auto_gate.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_dict, f)
        
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('auto_gate.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-009', executor.manifest)
        
        result = executor._handle_gate('step_1')
        
        self.assertTrue(result)

    def test_manual_execution_mode(self):
        """Should prompt for manual skill execution in interactive mode"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=True)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-010', executor.manifest)
        
        # Create required artifact
        session_dir = executor.session_manager.get_session_dir()
        (session_dir / 'requirement.md').write_text('# Requirement\n')
        
        # Mock user input to complete
        with patch('builtins.input', return_value=''):
            result = executor._execute_step('step_1')
        
        self.assertTrue(result)

    def test_manual_execution_mode_skip(self):
        """Should handle skip in manual execution mode"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=True)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-011', executor.manifest)
        
        # Mock user input to skip
        with patch('builtins.input', return_value='skip'):
            result = executor._execute_step('step_1')
        
        self.assertTrue(result)

    def test_automated_dispatch_mode(self):
        """Should use skill invoker in automated dispatch mode"""
        # Mock devin-cli path
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-012', executor.manifest)
        
        # Create required artifact
        session_dir = executor.session_manager.get_session_dir()
        (session_dir / 'requirement.md').write_text('# Requirement\n')
        
        # This will fail because devin.exe doesn't exist, but should create placeholder
        result = executor._execute_step('step_1')
        
        # Should still succeed due to fallback
        self.assertTrue(result)

    def test_fallback_to_placeholder(self):
        """Should create placeholder artifacts on dispatch failure"""
        # Mock devin-cli path that doesn't exist
        devin_cli_path = str(self.temp_path / 'nonexistent_devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-013', executor.manifest)
        
        # Execute step that requires skill invocation
        result = executor._execute_step('step_1')
        
        # Should create placeholder artifact
        session_dir = executor.session_manager.get_session_dir()
        placeholder_path = session_dir / 'requirement.md'
        self.assertTrue(placeholder_path.exists())
        content = placeholder_path.read_text(encoding='utf-8')
        self.assertIn('Placeholder', content)

    def test_get_gate_after_step(self):
        """Should get gate configuration after a specific step"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        
        gate = executor._get_gate_after_step('step_1')
        
        self.assertIsNotNone(gate)
        self.assertEqual(gate['id'], 'g1_approval')
        self.assertEqual(gate['after_step'], 'step_1')
        self.assertEqual(gate['type'], 'user_gate')
        
        gate = executor._get_gate_after_step('step_2')
        
        self.assertIsNone(gate)


if __name__ == '__main__':
    unittest.main()

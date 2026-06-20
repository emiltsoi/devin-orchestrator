# -*- coding: utf-8 -*-
"""
Integration Tests for Skill Evaluator with Step Executor
Tests the confidence scoring and decision logic in workflow context
Following TDD principles - these tests should fail initially
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import yaml
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

import sys
sys.path.insert(0, str(Path(__file__).parent))

from step_executor import StepExecutor, StepResult
from skill_evaluator import SkillEvaluator, EvaluationResult
from manifest_loader import Manifest, ManifestLoader
from session_manager import SessionManager


class TestSkillEvaluatorIntegration(unittest.TestCase):
    """Integration tests for skill evaluator with step executor"""

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
        
        # Create skill files with iron laws
        (self.skills_dir / 'brainstorming.yaml').write_text('''schema_version: 1
name: brainstorming
iron_law: Generate creative ideas without placeholders
''')
        (self.skills_dir / 'brainstorming.md').write_text('# Brainstorming Skill\n')
        
        (self.skills_dir / 'test-driven-development.yaml').write_text('''schema_version: 1
name: test-driven-development
iron_law: WRITE FAILING TEST FIRST, THEN IMPLEMENT TO MAKE IT PASS
''')
        (self.skills_dir / 'test-driven-development.md').write_text('# TDD Skill\n')
        
        (self.skills_dir / 'verification-before-completion.yaml').write_text('''schema_version: 1
name: verification-before-completion
iron_law: Verify all tests pass before completion
''')
        (self.skills_dir / 'verification-before-completion.md').write_text('# Verification Skill\n')
        
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
                'step_2': ['baseline.md'],
                'step_3': ['test_results.md']
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
                },
                {
                    'name': 'verification-before-completion',
                    'phases': ['step_3'],
                    'announcement': 'Using verification skill'
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

    def test_skill_evaluator_integration_high_confidence_auto_approve(self):
        """Should auto-approve skill output with high confidence (>= 0.9)"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-001', executor.manifest)
        
        # Create high-quality artifact with passing tests
        session_dir = executor.session_manager.get_session_dir()
        test_results_path = session_dir / 'test_results.md'
        test_results_path.write_text('''# Test Results

All tests passed successfully.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors

Build status: OK
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_results_path,
            context={'session_id': 'TEST-001', 'step': 'step_3'}
        )
        
        # Should have high confidence and be auto-approvable
        self.assertGreaterEqual(evaluation.confidence, 0.9, 
            f"Expected confidence >= 0.9, got {evaluation.confidence}")
        self.assertTrue(evaluation.auto_approvable, 
            "Should be auto-approvable for high confidence")
        self.assertFalse(evaluation.requires_user_input,
            "Should not require user input for high confidence")

    def test_skill_evaluator_integration_medium_confidence_user_gate(self):
        """Should require user gate for medium confidence (0.7-0.9)"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-002', executor.manifest)
        
        # Create artifact with some test failures (medium confidence)
        session_dir = executor.session_manager.get_session_dir()
        test_results_path = session_dir / 'test_results.md'
        test_results_path.write_text('''# Test Results

Some tests failed.

## Summary
- 65/70 tests passed
- 5 failed
- 0 errors

Build status: OK
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_results_path,
            context={'session_id': 'TEST-002', 'step': 'step_3'}
        )
        
        # Should have medium confidence and require user input
        self.assertGreaterEqual(evaluation.confidence, 0.7,
            f"Expected confidence >= 0.7, got {evaluation.confidence}")
        self.assertLess(evaluation.confidence, 0.9,
            f"Expected confidence < 0.9, got {evaluation.confidence}")
        self.assertFalse(evaluation.auto_approvable,
            "Should not be auto-approvable for medium confidence")
        self.assertTrue(evaluation.requires_user_input,
            "Should require user input for medium confidence")

    def test_skill_evaluator_integration_low_confidence_user_gate(self):
        """Should require user gate for low confidence (< 0.7)"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-003', executor.manifest)
        
        # Create artifact with multiple failures and placeholders (low confidence)
        session_dir = executor.session_manager.get_session_dir()
        test_results_path = session_dir / 'test_results.md'
        test_results_path.write_text('''# Test Results

Multiple failures.

## Summary
- 45/70 tests passed
- 25 failed
- 0 errors

Build status: FAILED

TODO: fix the failing tests
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_results_path,
            context={'session_id': 'TEST-003', 'step': 'step_3'}
        )
        
        # Should have low confidence and require user input
        self.assertLess(evaluation.confidence, 0.7,
            f"Expected confidence < 0.7, got {evaluation.confidence}")
        self.assertFalse(evaluation.auto_approvable,
            "Should not be auto-approvable for low confidence")
        self.assertTrue(evaluation.requires_user_input,
            "Should require user input for low confidence")

    def test_automated_dispatch_with_evaluation_success(self):
        """Should complete automated dispatch when evaluation passes"""
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-004', executor.manifest)
        
        # Mock skill invoker to return success
        mock_invocation_result = MagicMock()
        mock_invocation_result.success = True
        mock_invocation_result.session_id = 'skill-session-123'
        mock_invocation_result.output = 'Skill executed successfully'
        
        with patch.object(executor.skill_invoker, 'invoke_skill', return_value=mock_invocation_result):
            # Create high-quality artifact that will pass evaluation
            session_dir = executor.session_manager.get_session_dir()
            baseline_path = session_dir / 'baseline.md'
            baseline_path.write_text('''# Baseline Tests

All tests passed.

## Summary
- 50/50 tests passed
- 0 failed
''')
            
            # Execute step with automated dispatch
            result = executor._execute_step('step_2')
            
            # Should succeed because evaluation passes
            self.assertTrue(result, "Step should succeed with high confidence evaluation")

    def test_automated_dispatch_with_evaluation_failure(self):
        """Should abort automated dispatch when evaluation fails in non-interactive mode"""
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-005', executor.manifest)
        
        # Mock skill invoker to return success
        mock_invocation_result = MagicMock()
        mock_invocation_result.success = True
        mock_invocation_result.session_id = 'skill-session-123'
        mock_invocation_result.output = 'Skill executed successfully'
        
        with patch.object(executor.skill_invoker, 'invoke_skill', return_value=mock_invocation_result):
            # Create low-quality artifact that will fail evaluation
            session_dir = executor.session_manager.get_session_dir()
            baseline_path = session_dir / 'baseline.md'
            baseline_path.write_text('''# Baseline Tests

PLACEHOLDER - TODO implement

## Summary
- 10/50 tests passed
- 40 failed
''')
            
            # Execute step with automated dispatch
            result = executor._execute_step('step_2')
            
            # Should fail because evaluation fails in non-interactive mode
            self.assertFalse(result, "Step should fail with low confidence evaluation in non-interactive mode")

    def test_iron_law_compliance_check(self):
        """Should check Iron Law compliance in evaluation"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-006', executor.manifest)
        
        # Create artifact that violates Iron Law (no tests when required)
        session_dir = executor.session_manager.get_session_dir()
        baseline_path = session_dir / 'baseline.md'
        baseline_path.write_text('''# Implementation Plan

This is the implementation plan without tests.
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='test-driven-development',
            artifact_path=baseline_path,
            context={'session_id': 'TEST-006', 'step': 'step_2'}
        )
        
        # Should fail Iron Law check
        self.assertFalse(evaluation.passed, "Should fail Iron Law compliance check")
        self.assertIn('Iron Law', str(evaluation.issues), 
            "Issues should mention Iron Law violation")

    def test_placeholder_detection_in_evaluation(self):
        """Should detect placeholder patterns in evaluation"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-007', executor.manifest)
        
        # Create artifact with placeholders
        session_dir = executor.session_manager.get_session_dir()
        requirement_path = session_dir / 'requirement.md'
        requirement_path.write_text('''# Requirements

PLACEHOLDER: TODO fill in requirements

TBD: need to specify acceptance criteria
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='brainstorming',
            artifact_path=requirement_path,
            context={'session_id': 'TEST-007', 'step': 'step_1'}
        )
        
        # Should detect placeholders
        self.assertFalse(evaluation.passed, "Should fail due to placeholders")
        self.assertTrue(any('placeholder' in issue.lower() for issue in evaluation.issues),
            "Issues should mention placeholder detection")

    def test_structural_validation_in_evaluation(self):
        """Should validate structural requirements in evaluation"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-008', executor.manifest)
        
        # Create empty artifact
        session_dir = executor.session_manager.get_session_dir()
        baseline_path = session_dir / 'baseline.md'
        baseline_path.write_text('')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='test-driven-development',
            artifact_path=baseline_path,
            context={'session_id': 'TEST-008', 'step': 'step_2'}
        )
        
        # Should fail structural check
        self.assertFalse(evaluation.passed, "Should fail structural validation")
        self.assertTrue(any('empty' in issue.lower() for issue in evaluation.issues),
            "Issues should mention empty artifact")

    def test_format_validation_yaml(self):
        """Should validate YAML format in evaluation"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-009', executor.manifest)
        
        # Create invalid YAML artifact
        session_dir = executor.session_manager.get_session_dir()
        yaml_path = session_dir / 'config.yaml'
        yaml_path.write_text('''
name: test
version: 1.0
steps:
  - step1
  - [unclosed bracket
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='brainstorming',
            artifact_path=yaml_path,
            context={'session_id': 'TEST-009', 'step': 'step_1'}
        )
        
        # Should fail format check
        self.assertFalse(evaluation.passed, "Should fail YAML format validation")
        self.assertTrue(any('yaml' in issue.lower() or 'parsing' in issue.lower() for issue in evaluation.issues),
            "Issues should mention YAML parsing error")

    def test_evaluation_details_completeness(self):
        """Should provide complete evaluation details"""
        executor = StepExecutor(self.harness_root, self.work_dir, interactive=False)
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-010', executor.manifest)
        
        # Create comprehensive artifact
        session_dir = executor.session_manager.get_session_dir()
        test_results_path = session_dir / 'test_results.md'
        test_results_path.write_text('''# Test Results

All tests passed.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors
''')
        
        # Evaluate the artifact
        evaluation = executor.skill_evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_results_path,
            context={'session_id': 'TEST-010', 'step': 'step_3'}
        )
        
        # Should have complete details
        self.assertIn('structural', evaluation.details, "Should include structural check details")
        self.assertIn('iron_law', evaluation.details, "Should include Iron Law check details")
        self.assertIn('format', evaluation.details, "Should include format check details")
        self.assertIn('test_results', evaluation.details, "Should include test results details")


class TestConfidenceThresholdBoundaries(unittest.TestCase):
    """Test confidence threshold boundary conditions"""

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
        (self.skills_dir / 'verification-before-completion.yaml').write_text('''schema_version: 1
name: verification-before-completion
iron_law: Verify all tests pass before completion
''')
        (self.skills_dir / 'verification-before-completion.md').write_text('# Verification Skill\n')
        
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
                'step_1': ['test_results.md']
            },
            'gates': [],
            'skills': [
                {
                    'name': 'verification-before-completion',
                    'phases': ['step_1'],
                    'announcement': 'Using verification skill'
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

    def test_confidence_exactly_0_9_auto_approve(self):
        """Should auto-approve when confidence is exactly 0.9"""
        evaluator = SkillEvaluator(self.harness_root)
        
        # Create artifact that should give exactly 0.9 confidence
        # (perfect structural + iron law + format, but minor test issue)
        test_path = self.temp_path / 'test_results.md'
        test_path.write_text('''# Test Results

Minor issue but mostly complete.

## Summary
- 69/70 tests passed
- 1 failed
- 0 errors
''')
        
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_path,
            context={}
        )
        
        # At 0.9 exactly, should be auto-approvable
        self.assertGreaterEqual(evaluation.confidence, 0.9,
            f"Expected confidence >= 0.9, got {evaluation.confidence}")
        self.assertTrue(evaluation.auto_approvable,
            "Should be auto-approvable at confidence >= 0.9")

    def test_confidence_just_below_0_9_requires_review(self):
        """Should require review when confidence is just below 0.9"""
        evaluator = SkillEvaluator(self.harness_root)
        
        # Create artifact with slightly more issues
        test_path = self.temp_path / 'test_results.md'
        test_path.write_text('''# Test Results

Some issues.

## Summary
- 68/70 tests passed
- 2 failed
- 0 errors
''')
        
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_path,
            context={}
        )
        
        # Below 0.9, should not be auto-approvable
        self.assertLess(evaluation.confidence, 0.9,
            f"Expected confidence < 0.9, got {evaluation.confidence}")
        self.assertFalse(evaluation.auto_approvable,
            "Should not be auto-approvable below 0.9")

    def test_confidence_exactly_0_7_user_gate(self):
        """Should require user input when confidence is exactly 0.7"""
        evaluator = SkillEvaluator(self.harness_root)
        
        # Create artifact that should give exactly 0.7 confidence
        test_path = self.temp_path / 'test_results.md'
        test_path.write_text('''# Test Results

Multiple failures.

## Summary
- 65/70 tests passed
- 5 failed
- 0 errors
''')
        
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_path,
            context={}
        )
        
        # At 0.7, should require user input
        self.assertGreaterEqual(evaluation.confidence, 0.7,
            f"Expected confidence >= 0.7, got {evaluation.confidence}")
        self.assertTrue(evaluation.requires_user_input,
            "Should require user input at confidence <= 0.7")

    def test_confidence_just_below_0_7_user_gate(self):
        """Should require user input when confidence is just below 0.7"""
        evaluator = SkillEvaluator(self.harness_root)
        
        # Create artifact with more significant issues
        test_path = self.temp_path / 'test_results.md'
        test_path.write_text('''# Test Results

Many failures.

## Summary
- 60/70 tests passed
- 10 failed
- 0 errors
''')
        
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_path,
            context={}
        )
        
        # Below 0.7, should require user input
        self.assertLess(evaluation.confidence, 0.7,
            f"Expected confidence < 0.7, got {evaluation.confidence}")
        self.assertTrue(evaluation.requires_user_input,
            "Should require user input below 0.7")

    def test_confidence_clamping_at_zero(self):
        """Should clamp confidence to minimum 0.0"""
        evaluator = SkillEvaluator(self.harness_root)
        
        # Create artifact with multiple severe issues
        test_path = self.temp_path / 'test_results.md'
        test_path.write_text('''PLACEHOLDER TODO

## Summary
- 0/70 tests passed
- 70 failed
- 10 errors
''')
        
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_path,
            context={}
        )
        
        # Should be clamped to 0.0 minimum
        self.assertGreaterEqual(evaluation.confidence, 0.0,
            f"Expected confidence >= 0.0, got {evaluation.confidence}")
        self.assertLessEqual(evaluation.confidence, 1.0,
            f"Expected confidence <= 1.0, got {evaluation.confidence}")

    def test_confidence_clamping_at_one(self):
        """Should clamp confidence to maximum 1.0"""
        evaluator = SkillEvaluator(self.harness_root)
        
        # Create perfect artifact
        test_path = self.temp_path / 'test_results.md'
        test_path.write_text('''# Test Results

Perfect execution.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors
''')
        
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',
            artifact_path=test_path,
            context={}
        )
        
        # Should be clamped to 1.0 maximum
        self.assertLessEqual(evaluation.confidence, 1.0,
            f"Expected confidence <= 1.0, got {evaluation.confidence}")


class TestAutomatedDispatchScenarios(unittest.TestCase):
    """Test automated dispatch evaluation scenarios"""

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
        (self.skills_dir / 'test-driven-development.yaml').write_text('''schema_version: 1
name: test-driven-development
iron_law: WRITE FAILING TEST FIRST, THEN IMPLEMENT TO MAKE IT PASS
''')
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
                'step_1': ['baseline.md']
            },
            'gates': [],
            'skills': [
                {
                    'name': 'test-driven-development',
                    'phases': ['step_1'],
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

    def test_automated_dispatch_creates_artifacts(self):
        """Should create artifacts after successful automated dispatch"""
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-001', executor.manifest)
        
        # Mock skill invoker to return success
        mock_invocation_result = MagicMock()
        mock_invocation_result.success = True
        mock_invocation_result.session_id = 'skill-session-123'
        mock_invocation_result.output = 'Skill executed successfully'
        
        with patch.object(executor.skill_invoker, 'invoke_skill', return_value=mock_invocation_result):
            # Create high-quality artifact
            session_dir = executor.session_manager.get_session_dir()
            baseline_path = session_dir / 'baseline.md'
            baseline_path.write_text('''# Baseline

Test specification.

## Tests
- Test 1
- Test 2
''')
            
            # Execute step
            result = executor._execute_step('step_1')
            
            # Should create artifact
            self.assertTrue(baseline_path.exists(), "Artifact should be created")
            self.assertTrue(result, "Step should succeed")

    def test_automated_dispatch_with_skill_invocation_failure(self):
        """Should handle skill invocation failure gracefully"""
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-002', executor.manifest)
        
        # Mock skill invoker to return failure
        mock_invocation_result = MagicMock()
        mock_invocation_result.success = False
        mock_invocation_result.session_id = None
        mock_invocation_result.output = None
        mock_invocation_result.error = 'Skill invocation failed'
        
        with patch.object(executor.skill_invoker, 'invoke_skill', return_value=mock_invocation_result):
            # Execute step
            result = executor._execute_step('step_1')
            
            # Should create placeholder as fallback
            session_dir = executor.session_manager.get_session_dir()
            baseline_path = session_dir / 'baseline.md'
            self.assertTrue(baseline_path.exists(), "Placeholder artifact should be created")
            
            content = baseline_path.read_text(encoding='utf-8')
            self.assertIn('Placeholder', content, "Should contain placeholder text")
            self.assertIn('dispatch failure', content, "Should mention dispatch failure")

    def test_automated_dispatch_evaluation_influences_workflow(self):
        """Should use evaluation results to influence workflow decisions"""
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('test.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-003', executor.manifest)
        
        # Mock skill invoker to return success
        mock_invocation_result = MagicMock()
        mock_invocation_result.success = True
        mock_invocation_result.session_id = 'skill-session-123'
        mock_invocation_result.output = 'Skill executed successfully'
        
        with patch.object(executor.skill_invoker, 'invoke_skill', return_value=mock_invocation_result):
            # Create low-quality artifact that will fail evaluation
            session_dir = executor.session_manager.get_session_dir()
            baseline_path = session_dir / 'baseline.md'
            baseline_path.write_text('''PLACEHOLDER

TODO implement
''')
            
            # Execute step - should fail due to evaluation
            result = executor._execute_step('step_1')
            
            # Should fail workflow due to low confidence evaluation
            self.assertFalse(result, "Workflow should fail due to evaluation")

    def test_automated_dispatch_with_missing_skill_definition(self):
        """Should handle missing skill definition gracefully"""
        devin_cli_path = str(self.temp_path / 'devin.exe')
        
        # Create manifest with non-existent skill
        manifest_dict = self.valid_manifest.copy()
        manifest_dict['skills'] = [
            {
                'name': 'non-existent-skill',
                'phases': ['step_1'],
                'announcement': 'Using non-existent skill'
            }
        ]
        
        manifest_path = self.workflows_dir / 'no_skill.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(manifest_dict, f)
        
        executor = StepExecutor(
            self.harness_root,
            self.work_dir,
            interactive=False,
            devin_cli_path=devin_cli_path
        )
        executor.manifest = executor.manifest_loader.load('no_skill.manifest.yaml')
        executor.session_manager = SessionManager(self.harness_root, self.work_dir)
        executor.session_manager.initialize_session('TEST-004', executor.manifest)
        
        # Mock skill invoker to return failure due to missing skill
        mock_invocation_result = MagicMock()
        mock_invocation_result.success = False
        mock_invocation_result.session_id = None
        mock_invocation_result.output = None
        mock_invocation_result.error = 'Skill definition not found'
        
        with patch.object(executor.skill_invoker, 'invoke_skill', return_value=mock_invocation_result):
            # Execute step - should create placeholder
            result = executor._execute_step('step_1')
            
            # Should create placeholder as fallback
            session_dir = executor.session_manager.get_session_dir()
            baseline_path = session_dir / 'baseline.md'
            self.assertTrue(baseline_path.exists(), "Placeholder should be created")


if __name__ == '__main__':
    unittest.main()

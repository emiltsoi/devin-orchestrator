# -*- coding: utf-8 -*-
"""
Unit Tests for Skill Invoker
Tests follow TDD principles - written to validate existing implementation
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import yaml
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent))

from skill_invoker import SkillInvoker, SkillInvocationResult
from devin_cli_adapter import DevinCliAdapter, InvocationResult


class TestSkillInvoker(unittest.TestCase):
    """Test cases for SkillInvoker"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.harness_root = self.temp_path / 'harness'
        self.harness_root.mkdir()
        self.skills_dir = self.temp_path / 'skills'
        self.skills_dir.mkdir()
        
        # Create skill files
        (self.skills_dir / 'brainstorming.yaml').write_text(
            'schema_version: 1\n'
            'name: brainstorming\n'
            'description: Brainstorming skill\n'
            'iron_law: "NO IMPLEMENTATION UNTIL DESIGN APPROVED"\n'
            'triggers: [new_feature]\n'
            'checklist: []\n'
            'terminal_state: writing-plans\n'
            'announcement: "Using the brainstorming skill to refine {topic}"\n'
            'red_flags: []\n'
        )
        
        (self.skills_dir / 'brainstorming.md').write_text(
            '# Brainstorming Skill\n\n'
            '## Overview\n'
            'Brainstorming skill for generating ideas.\n\n'
            '## The Iron Law\n'
            'NO IMPLEMENTATION UNTIL DESIGN APPROVED\n'
        )
        
        self.devin_cli_path = str(self.temp_path / 'devin.exe')
        self.skill_invoker = SkillInvoker(self.harness_root, self.devin_cli_path)

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_invoke_skill_success(self):
        """Should successfully invoke skill using devin-cli"""
        context = {
            'session_id': 'TEST-001',
            'step': 'step_1',
            'session_dir': str(self.temp_path / 'work' / 'TEST-001'),
            'required_artifacts': ['requirement.md']
        }
        
        # Mock the adapter to return success
        with patch.object(DevinCliAdapter, 'invoke') as mock_invoke:
            mock_invoke.return_value = InvocationResult(
                success=True,
                output='Skill executed successfully',
                error=None,
                exit_code=0
            )
            
            result = self.skill_invoker.invoke_skill('brainstorming', context)
            
            self.assertTrue(result.success)
            self.assertIsNotNone(result.session_id)
            self.assertEqual(result.output, 'Skill executed successfully')
            self.assertIsNone(result.error)

    def test_invoke_skill_missing_definition(self):
        """Should fail when skill YAML not found"""
        context = {'session_id': 'TEST-002'}
        
        result = self.skill_invoker.invoke_skill('nonexistent_skill', context)
        
        self.assertFalse(result.success)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.output)
        self.assertIn('Skill definition not found', result.error)

    def test_invoke_skill_missing_narrative(self):
        """Should fail when skill markdown not found"""
        # Create YAML but not markdown
        (self.skills_dir / 'partial_skill.yaml').write_text('schema_version: 1\nname: partial_skill\n')
        
        context = {'session_id': 'TEST-003'}
        
        result = self.skill_invoker.invoke_skill('partial_skill', context)
        
        self.assertFalse(result.success)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.output)
        self.assertIn('Skill narrative not found', result.error)

    def test_invoke_skill_no_devin_path(self):
        """Should fail when devin CLI path not configured"""
        skill_invoker_no_path = SkillInvoker(self.harness_root, None)
        context = {'session_id': 'TEST-004'}
        
        result = skill_invoker_no_path.invoke_skill('brainstorming', context)
        
        self.assertFalse(result.success)
        self.assertIsNone(result.session_id)
        self.assertIsNone(result.output)
        self.assertIn('Devin CLI path not configured', result.error)

    def test_load_skill_definition(self):
        """Should load skill YAML correctly"""
        skill_def = self.skill_invoker.load_skill_definition('brainstorming')

        self.assertIsNotNone(skill_def)
        self.assertEqual(skill_def['name'], 'brainstorming')
        self.assertEqual(skill_def['schema_version'], 1)
        self.assertIn('iron_law', skill_def)

    def test_load_skill_definition_not_found(self):
        """Should return None for missing skill YAML"""
        skill_def = self.skill_invoker.load_skill_definition('nonexistent')

        self.assertIsNone(skill_def)

    def test_load_skill_narrative(self):
        """Should load skill markdown correctly"""
        skill_narrative = self.skill_invoker.load_skill_narrative('brainstorming')

        self.assertIsNotNone(skill_narrative)
        self.assertIn('Brainstorming Skill', skill_narrative)
        self.assertIn('Iron Law', skill_narrative)

    def test_load_skill_narrative_not_found(self):
        """Should return None for missing skill markdown"""
        skill_narrative = self.skill_invoker.load_skill_narrative('nonexistent')

        self.assertIsNone(skill_narrative)

    def test_build_skill_prompt(self):
        """Should build correct prompt with context and skill content"""
        skill_def = self.skill_invoker.load_skill_definition('brainstorming')
        skill_narrative = self.skill_invoker.load_skill_narrative('brainstorming')
        
        context = {
            'session_id': 'TEST-005',
            'step': 'step_1',
            'required_artifacts': ['requirement.md']
        }
        
        prompt = self.skill_invoker.build_skill_prompt(
            'brainstorming',
            skill_def,
            skill_narrative,
            context
        )
        
        self.assertIn('Skill Invocation: brainstorming', prompt)
        self.assertIn('session_id: TEST-005', prompt)
        self.assertIn('step: step_1', prompt)
        self.assertIn('Iron Law:', prompt)
        self.assertIn('NO IMPLEMENTATION UNTIL DESIGN APPROVED', prompt)
        self.assertIn('Skill Narrative', prompt)
        self.assertIn('Brainstorming Skill', prompt)
        self.assertIn('Instructions', prompt)

    def test_invoke_skill_with_model(self):
        """Should use specified model when provided"""
        skill_invoker_with_model = SkillInvoker(
            self.harness_root,
            self.devin_cli_path,
            model='claude-opus-4.6'
        )
        
        context = {'session_id': 'TEST-006'}
        
        with patch('skill_invoker.DevinCliAdapter') as mock_adapter_class:
            mock_adapter = Mock()
            mock_adapter_class.return_value = mock_adapter
            mock_adapter.invoke.return_value = InvocationResult(
                success=True,
                output='Success',
                error=None,
                exit_code=0
            )
            
            result = skill_invoker_with_model.invoke_skill('brainstorming', context)
            
            self.assertTrue(result.success)
            # Verify adapter was initialized with model parameter
            mock_adapter_class.assert_called_once()
            call_args = mock_adapter_class.call_args
            # Check positional and keyword arguments
            if call_args[1]:  # kwargs
                self.assertEqual(call_args[1].get('model'), 'claude-opus-4.6')

    def test_invoke_skill_with_permission_mode(self):
        """Should use specified permission mode"""
        skill_invoker_with_mode = SkillInvoker(
            self.harness_root,
            self.devin_cli_path,
            permission_mode='smart'
        )
        
        context = {'session_id': 'TEST-007'}
        
        with patch('skill_invoker.DevinCliAdapter') as mock_adapter_class:
            mock_adapter = Mock()
            mock_adapter_class.return_value = mock_adapter
            mock_adapter.invoke.return_value = InvocationResult(
                success=True,
                output='Success',
                error=None,
                exit_code=0
            )
            
            result = skill_invoker_with_mode.invoke_skill('brainstorming', context)
            
            self.assertTrue(result.success)
            # Verify adapter was initialized with permission mode parameter
            mock_adapter_class.assert_called_once()
            call_args = mock_adapter_class.call_args
            # Check positional and keyword arguments
            if call_args[1]:  # kwargs
                self.assertEqual(call_args[1].get('permission_mode'), 'smart')

    def test_invoke_skill_adapter_exception(self):
        """Should handle adapter exceptions gracefully"""
        context = {'session_id': 'TEST-008'}
        
        with patch.object(DevinCliAdapter, 'invoke') as mock_invoke:
            mock_invoke.side_effect = Exception('Adapter error')
            
            result = self.skill_invoker.invoke_skill('brainstorming', context)
            
            self.assertFalse(result.success)
            self.assertIsNone(result.session_id)
            self.assertIsNone(result.output)
            self.assertIsNotNone(result.error)
            self.assertIn('Adapter error', result.error)

    def test_session_id_generation(self):
        """Should generate session ID for tracking"""
        context = {'session_id': 'TEST-009'}
        
        with patch.object(DevinCliAdapter, 'invoke') as mock_invoke:
            mock_invoke.return_value = InvocationResult(
                success=True,
                output='Success',
                error='',
                exit_code=0
            )
            
            result = self.skill_invoker.invoke_skill('brainstorming', context)
            
            self.assertIsNotNone(result.session_id)
            self.assertIn('brainstorming', result.session_id)
            self.assertIn('TEST-009', result.session_id)

    def test_skill_definition_caching(self):
        """Should cache skill definitions after first load"""
        # First load - cache miss
        skill_def_1 = self.skill_invoker.load_skill_definition('brainstorming')
        self.assertIsNotNone(skill_def_1)
        initial_misses = self.skill_invoker._cache_misses
        initial_hits = self.skill_invoker._cache_hits

        # Second load - cache hit
        skill_def_2 = self.skill_invoker.load_skill_definition('brainstorming')
        self.assertIsNotNone(skill_def_2)
        self.assertEqual(skill_def_1, skill_def_2)

        # Verify cache stats
        self.assertEqual(self.skill_invoker._cache_misses, initial_misses)
        self.assertEqual(self.skill_invoker._cache_hits, initial_hits + 1)

    def test_skill_narrative_caching(self):
        """Should cache skill narratives after first load"""
        # First load - cache miss
        skill_narrative_1 = self.skill_invoker.load_skill_narrative('brainstorming')
        self.assertIsNotNone(skill_narrative_1)
        initial_misses = self.skill_invoker._cache_misses
        initial_hits = self.skill_invoker._cache_hits

        # Second load - cache hit
        skill_narrative_2 = self.skill_invoker.load_skill_narrative('brainstorming')
        self.assertIsNotNone(skill_narrative_2)
        self.assertEqual(skill_narrative_1, skill_narrative_2)

        # Verify cache stats
        self.assertEqual(self.skill_invoker._cache_misses, initial_misses)
        self.assertEqual(self.skill_invoker._cache_hits, initial_hits + 1)

    def test_cache_stats_initialization(self):
        """Should initialize cache stats to zero"""
        self.assertEqual(self.skill_invoker._cache_hits, 0)
        self.assertEqual(self.skill_invoker._cache_misses, 0)

    def test_cache_independent_instances(self):
        """Should have independent caches per SkillInvoker instance"""
        # Create second invoker with same harness
        invoker_2 = SkillInvoker(self.harness_root, self.devin_cli_path)

        # Load skill in first invoker
        self.skill_invoker.load_skill_definition('brainstorming')

        # Second invoker should have empty cache
        self.assertEqual(invoker_2._cache_hits, 0)
        self.assertEqual(invoker_2._cache_misses, 0)
        self.assertEqual(len(invoker_2._skill_definition_cache), 0)

    def test_clear_skill_cache(self):
        """Should clear all cache data and reset stats"""
        # Load some skills to populate cache
        self.skill_invoker.load_skill_definition('brainstorming')
        self.skill_invoker.load_skill_narrative('brainstorming')

        # Verify cache is populated
        self.assertGreater(len(self.skill_invoker._skill_definition_cache), 0)
        self.assertGreater(len(self.skill_invoker._skill_narrative_cache), 0)

        # Clear cache
        self.skill_invoker.clear_skill_cache()

        # Verify cache is cleared
        self.assertEqual(len(self.skill_invoker._skill_definition_cache), 0)
        self.assertEqual(len(self.skill_invoker._skill_narrative_cache), 0)
        self.assertEqual(self.skill_invoker._cache_hits, 0)
        self.assertEqual(self.skill_invoker._cache_misses, 0)


if __name__ == '__main__':
    unittest.main()

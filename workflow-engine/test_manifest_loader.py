# -*- coding: utf-8 -*-
"""
Unit Tests for Manifest Loader
Tests follow TDD principles - written to fail initially
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent))

from manifest_loader import ManifestLoader, Manifest


class TestManifestLoader(unittest.TestCase):
    """Test cases for ManifestLoader"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.harness_root = self.temp_path
        self.workflows_dir = self.temp_path / 'workflows'
        self.skills_dir = self.temp_path / 'skills'
        self.workflows_dir.mkdir()
        self.skills_dir.mkdir()
        
        self.loader = ManifestLoader(self.harness_root)
        
        # Create valid manifest
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
                'initial_artifacts': ['request.md', 'status.md']
            },
            'auto_load': [
                {'path': 'skills/README.md', 'always': True, 'purpose': 'Skill index'}
            ],
            'required_artifacts': {
                'step_0': ['request.md', 'status.md'],
                'step_1': ['requirement.md']
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
                }
            ],
            'branch': {
                'default': 'feature/<session_id>',
                'policy': 'implementation_branch_committable'
            }
        }
        
        # Create skill files referenced in manifest
        (self.skills_dir / 'brainstorming.yaml').write_text('schema_version: 1\nname: brainstorming\n')
        (self.skills_dir / 'brainstorming.md').write_text('# Brainstorming Skill\n')

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_load_valid_manifest(self):
        """Should successfully load a valid manifest.yaml"""
        manifest_path = self.workflows_dir / 'test.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.valid_manifest, f)
        
        manifest = self.loader.load('test.manifest.yaml')
        
        self.assertIsInstance(manifest, Manifest)
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.session_shape, 'feature')
        self.assertEqual(manifest.description, 'Test workflow')
        self.assertEqual(manifest.slash_command, '/test')

    def test_load_missing_manifest(self):
        """Should raise FileNotFoundError for missing manifest"""
        with self.assertRaises(FileNotFoundError) as context:
            self.loader.load('missing.manifest.yaml')
        
        self.assertIn('Manifest not found', str(context.exception))

    def test_validate_required_fields(self):
        """Should raise ValueError for missing required fields"""
        invalid_manifest = {'schema_version': 1}  # Missing most required fields
        manifest_path = self.workflows_dir / 'invalid.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(invalid_manifest, f)
        
        with self.assertRaises(ValueError) as context:
            self.loader.load('invalid.manifest.yaml')
        
        self.assertIn('Missing required fields', str(context.exception))

    def test_validate_schema_version(self):
        """Should raise ValueError for unsupported schema version"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest['schema_version'] = 99  # Unsupported version
        
        manifest_path = self.workflows_dir / 'invalid_version.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(invalid_manifest, f)
        
        with self.assertRaises(ValueError) as context:
            self.loader.load('invalid_version.manifest.yaml')
        
        self.assertIn('Unsupported schema version', str(context.exception))

    def test_validate_skill_references(self):
        """Should raise ValueError for missing skill files"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest['skills'] = [
            {'name': 'nonexistent_skill', 'phases': ['step_1']}
        ]
        
        manifest_path = self.workflows_dir / 'invalid_skill.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(invalid_manifest, f)
        
        with self.assertRaises(ValueError) as context:
            self.loader.load('invalid_skill.manifest.yaml')
        
        self.assertIn('Skill YAML not found', str(context.exception))

    def test_validate_skill_references_missing_markdown(self):
        """Should raise ValueError for missing skill markdown"""
        # Create YAML but not markdown
        (self.skills_dir / 'partial_skill.yaml').write_text('schema_version: 1\nname: partial_skill\n')
        
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest['skills'] = [
            {'name': 'partial_skill', 'phases': ['step_1']}
        ]
        
        manifest_path = self.workflows_dir / 'invalid_skill_md.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(invalid_manifest, f)
        
        with self.assertRaises(ValueError) as context:
            self.loader.load('invalid_skill_md.manifest.yaml')
        
        self.assertIn('Skill markdown not found', str(context.exception))

    def test_validate_gate_references(self):
        """Should raise ValueError for invalid gate configurations"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest['gates'] = [
            {'id': 'invalid_gate'}  # Missing after_step and type
        ]
        
        manifest_path = self.workflows_dir / 'invalid_gate.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(invalid_manifest, f)
        
        with self.assertRaises(ValueError) as context:
            self.loader.load('invalid_gate.manifest.yaml')
        
        self.assertIn('missing', str(context.exception).lower())

    def test_validate_gate_references_invalid_type(self):
        """Should raise ValueError for invalid gate type"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest['gates'] = [
            {
                'id': 'invalid_type_gate',
                'after_step': 'step_1',
                'type': 'invalid_gate_type'  # Invalid type
            }
        ]
        
        manifest_path = self.workflows_dir / 'invalid_gate_type.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(invalid_manifest, f)
        
        with self.assertRaises(ValueError) as context:
            self.loader.load('invalid_gate_type.manifest.yaml')
        
        self.assertIn('invalid type', str(context.exception).lower())

    def test_parse_all_fields(self):
        """Should correctly parse all manifest fields into Manifest dataclass"""
        manifest_path = self.workflows_dir / 'full.manifest.yaml'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.valid_manifest, f)
        
        manifest = self.loader.load('full.manifest.yaml')
        
        # Verify all fields are parsed correctly
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.session_shape, 'feature')
        self.assertEqual(manifest.description, 'Test workflow')
        self.assertEqual(manifest.slash_command, '/test')
        self.assertEqual(manifest.canonical_workflow, 'workflows/test.md')
        self.assertEqual(manifest.session_id_format, 'TEST-NNN')
        self.assertEqual(manifest.session_init['command'], 'session-init')
        self.assertEqual(len(manifest.auto_load), 1)
        self.assertEqual(len(manifest.required_artifacts), 2)
        self.assertEqual(len(manifest.gates), 1)
        self.assertEqual(len(manifest.skills), 1)
        self.assertEqual(manifest.branch['default'], 'feature/<session_id>')


if __name__ == '__main__':
    unittest.main()

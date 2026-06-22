# -*- coding: utf-8 -*-
"""
Unit Tests for Session Manager
Tests follow TDD principles - written to validate existing implementation
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent))

from session_manager import SessionManager, SessionState
from manifest_loader import Manifest, ManifestLoader


class TestSessionManager(unittest.TestCase):
    """Test cases for SessionManager"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.harness_root = self.temp_path
        self.work_dir = self.temp_path / 'work'
        self.work_dir.mkdir()
        
        self.session_manager = SessionManager(self.harness_root, self.work_dir)
        
        # Create a minimal manifest for testing
        self.manifest = Manifest(
            schema_version=1,
            session_shape='feature',
            description='Test workflow',
            slash_command='/test',
            canonical_workflow='workflows/test.md',
            session_id_format='TEST-NNN',
            session_init={
                'command': 'session-init',
                'creates_workdir': 'work/<session_id>/',
                'initial_artifacts': ['request.md', 'status.md']
            },
            auto_load=[],
            required_artifacts={
                'step_0': ['request.md', 'status.md'],
                'step_1': ['requirement.md']
            },
            gates=[],
            skills=[],
            branch={'default': 'feature/<session_id>', 'policy': 'implementation_branch_committable'}
        )

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_initialize_session(self):
        """Should create session directory and initial artifacts"""
        session_id = 'TEST-001'
        state = self.session_manager.initialize_session(session_id, self.manifest)
        
        # Check session directory was created
        session_dir = self.work_dir / session_id
        self.assertTrue(session_dir.exists())
        self.assertTrue(session_dir.is_dir())
        
        # Check state was initialized correctly
        self.assertIsInstance(state, SessionState)
        self.assertEqual(state.session_id, session_id)
        self.assertEqual(state.current_step, 'step_0')
        self.assertEqual(state.current_phase, 'context')
        self.assertEqual(state.status, 'in_progress')
        self.assertEqual(state.retries, 0)
        self.assertIsNotNone(state.start_time)
        self.assertIsNone(state.end_time)

    def test_initialize_artifacts(self):
        """Should create request.md, status.md, session-audit.md with correct content"""
        session_id = 'TEST-002'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        session_dir = self.work_dir / session_id
        
        # Check request.md
        request_path = session_dir / 'request.md'
        self.assertTrue(request_path.exists())
        request_content = request_path.read_text(encoding='utf-8')
        self.assertIn(session_id, request_content)
        self.assertIn('Request', request_content)
        
        # Check status.md
        status_path = session_dir / 'status.md'
        self.assertTrue(status_path.exists())
        status_content = status_path.read_text(encoding='utf-8')
        self.assertIn('step_0', status_content)
        self.assertIn('context', status_content)
        self.assertIn('in_progress', status_content)
        
        # Check session-audit.md
        audit_path = session_dir / 'session-audit.md'
        self.assertTrue(audit_path.exists())
        audit_content = audit_path.read_text(encoding='utf-8')
        self.assertIn(session_id, audit_content)
        self.assertIn('Session Start', audit_content)
        self.assertIn('Phase Transitions', audit_content)

    def test_update_phase(self):
        """Should update session state and status.md correctly"""
        session_id = 'TEST-003'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Update phase
        self.session_manager.update_phase('step_1', 'brainstorming', 'brainstorming')
        
        # Check state was updated
        self.assertEqual(self.session_manager.state.current_step, 'step_1')
        self.assertEqual(self.session_manager.state.current_phase, 'brainstorming')
        self.assertEqual(self.session_manager.state.retries, 0)
        
        # Check status.md was updated
        status_path = self.session_manager.get_session_dir() / 'status.md'
        status_content = status_path.read_text(encoding='utf-8')
        self.assertIn('step_1', status_content)
        self.assertIn('brainstorming', status_content)
        
        # Check audit log was updated
        audit_path = self.session_manager.get_session_dir() / 'session-audit.md'
        audit_content = audit_path.read_text(encoding='utf-8')
        self.assertIn('step_1', audit_content)
        self.assertIn('brainstorming', audit_content)
        self.assertIn('Phase transition', audit_content)

    def test_increment_retry(self):
        """Should increment retry counter and update status.md"""
        session_id = 'TEST-004'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Increment retry
        self.session_manager.increment_retry()
        
        # Check retry counter was incremented
        self.assertEqual(self.session_manager.state.retries, 1)
        
        # Check status.md was updated
        status_path = self.session_manager.get_session_dir() / 'status.md'
        status_content = status_path.read_text(encoding='utf-8')
        self.assertIn('retries=1', status_content)

    def test_complete_session(self):
        """Should mark session as completed with end time"""
        session_id = 'TEST-005'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Complete session
        self.session_manager.complete_session()
        
        # Check state was updated
        self.assertEqual(self.session_manager.state.status, 'completed')
        self.assertIsNotNone(self.session_manager.state.end_time)
        
        # Check status.md was updated
        status_path = self.session_manager.get_session_dir() / 'status.md'
        status_content = status_path.read_text(encoding='utf-8')
        self.assertIn('completed', status_content)
        
        # Check audit log was updated
        audit_path = self.session_manager.get_session_dir() / 'session-audit.md'
        audit_content = audit_path.read_text(encoding='utf-8')
        self.assertIn('Session End', audit_content)
        self.assertIn('completed', audit_content)

    def test_fail_session(self):
        """Should mark session as failed with reason"""
        session_id = 'TEST-006'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Fail session
        reason = 'Test failure reason'
        self.session_manager.fail_session(reason)
        
        # Check state was updated
        self.assertEqual(self.session_manager.state.status, 'failed')
        self.assertIsNotNone(self.session_manager.state.end_time)
        
        # Check status.md was updated
        status_path = self.session_manager.get_session_dir() / 'status.md'
        status_content = status_path.read_text(encoding='utf-8')
        self.assertIn('failed', status_content)
        
        # Check audit log was updated
        audit_path = self.session_manager.get_session_dir() / 'session-audit.md'
        audit_content = audit_path.read_text(encoding='utf-8')
        self.assertIn('Session End', audit_content)
        self.assertIn('failed', audit_content)
        self.assertIn(reason, audit_content)

    def test_artifact_exists(self):
        """Should correctly check artifact existence"""
        session_id = 'TEST-007'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Check existing artifact
        self.assertTrue(self.session_manager.artifact_exists('request.md'))
        self.assertTrue(self.session_manager.artifact_exists('status.md'))
        
        # Check non-existing artifact
        self.assertFalse(self.session_manager.artifact_exists('nonexistent.md'))

    def test_get_session_dir(self):
        """Should return correct session directory path"""
        session_id = 'TEST-008'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        session_dir = self.session_manager.get_session_dir()
        expected_dir = self.work_dir / session_id
        
        self.assertEqual(session_dir, expected_dir)
        self.assertTrue(session_dir.exists())

    def test_log_phase_transition(self):
        """Should log phase transitions in session-audit.md"""
        session_id = 'TEST-009'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Update phase (which logs the transition)
        self.session_manager.update_phase('step_1', 'brainstorming', 'brainstorming')
        
        # Check audit log
        audit_path = self.session_manager.get_session_dir() / 'session-audit.md'
        audit_content = audit_path.read_text(encoding='utf-8')
        
        self.assertIn('Phase transition', audit_content)
        self.assertIn('step_1', audit_content)
        self.assertIn('brainstorming', audit_content)
        # Check for timestamp format (ISO format with T and Z)
        self.assertRegex(audit_content, r'\d{4}-\d{2}-\d{2}T')

    def test_log_session_completion(self):
        """Should log session completion in session-audit.md"""
        session_id = 'TEST-010'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Complete session
        self.session_manager.complete_session()
        
        # Check audit log
        audit_path = self.session_manager.get_session_dir() / 'session-audit.md'
        audit_content = audit_path.read_text(encoding='utf-8')
        
        self.assertIn('Session End', audit_content)
        self.assertIn('completed', audit_content)
        # Check for timestamp format
        self.assertRegex(audit_content, r'\d{4}-\d{2}-\d{2}T')

    def test_log_session_failure(self):
        """Should log session failure in session-audit.md"""
        session_id = 'TEST-011'
        self.session_manager.initialize_session(session_id, self.manifest)
        
        # Fail session
        reason = 'Test failure'
        self.session_manager.fail_session(reason)
        
        # Check audit log
        audit_path = self.session_manager.get_session_dir() / 'session-audit.md'
        audit_content = audit_path.read_text(encoding='utf-8')
        
        self.assertIn('Session End', audit_content)
        self.assertIn('failed', audit_content)
        self.assertIn(reason, audit_content)

    def test_update_phase_without_initialization(self):
        """Should raise RuntimeError when updating phase without initialization"""
        with self.assertRaises(RuntimeError) as context:
            self.session_manager.update_phase('step_1', 'brainstorming', 'brainstorming')
        
        self.assertIn('Session not initialized', str(context.exception))

    def test_increment_retry_without_initialization(self):
        """Should raise RuntimeError when incrementing retry without initialization"""
        with self.assertRaises(RuntimeError) as context:
            self.session_manager.increment_retry()
        
        self.assertIn('Session not initialized', str(context.exception))

    def test_complete_session_without_initialization(self):
        """Should raise RuntimeError when completing session without initialization"""
        with self.assertRaises(RuntimeError) as context:
            self.session_manager.complete_session()
        
        self.assertIn('Session not initialized', str(context.exception))

    def test_fail_session_without_initialization(self):
        """Should raise RuntimeError when failing session without initialization"""
        with self.assertRaises(RuntimeError) as context:
            self.session_manager.fail_session('Test reason')
        
        self.assertIn('Session not initialized', str(context.exception))

    def test_artifact_exists_without_initialization(self):
        """Should return False when checking artifact without initialization"""
        result = self.session_manager.artifact_exists('request.md')
        self.assertFalse(result)

    def test_get_session_dir_without_initialization(self):
        """Should raise RuntimeError when getting session dir without initialization"""
        with self.assertRaises(RuntimeError) as context:
            self.session_manager.get_session_dir()
        
        self.assertIn('Session not initialized', str(context.exception))


if __name__ == '__main__':
    unittest.main()

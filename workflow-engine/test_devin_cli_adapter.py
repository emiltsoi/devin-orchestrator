# -*- coding: utf-8 -*-
"""
Unit Tests for Devin CLI Adapter
Tests follow TDD principles - written to validate existing implementation
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).parent))

from devin_cli_adapter import DevinCliAdapter, InvocationResult


class TestDevinCliAdapter(unittest.TestCase):
    """Test cases for DevinCliAdapter"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.workspace = self.temp_path / 'workspace'
        self.workspace.mkdir()
        
        # Create a mock devin.exe path
        self.devin_cli_path = str(self.temp_path / 'devin.exe')
        
        # Create a simple batch script that acts like devin for testing
        if sys.platform == 'win32':
            batch_script = f"@echo off\necho Mock devin output\nexit /b 0\n"
            (self.temp_path / 'devin.exe').write_text(batch_script)
        else:
            shell_script = f"#!/bin/bash\necho 'Mock devin output'\nexit 0\n"
            (self.temp_path / 'devin').write_text(shell_script)
            (self.temp_path / 'devin').chmod(0o755)
        
        self.adapter = DevinCliAdapter(self.devin_cli_path, str(self.workspace))

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_invoke_success(self):
        """Should successfully invoke devin-cli with prompt"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[self.devin_cli_path],
                returncode=0,
                stdout='Mock devin output',
                stderr=''
            )
            
            result = self.adapter.invoke('test prompt')
            
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            self.assertIn('Mock devin output', result.output)

    def test_invoke_with_model(self):
        """Should include model parameter when specified"""
        adapter_with_model = DevinCliAdapter(
            self.devin_cli_path,
            str(self.workspace),
            model='claude-opus-4.6'
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = adapter_with_model.invoke('test prompt')
            
            # Verify command includes model parameter
            call_args = mock_run.call_args[0][0]
            self.assertIn('--model', call_args)
            self.assertIn('claude-opus-4.6', call_args)

    def test_invoke_with_permission_mode(self):
        """Should include permission mode parameter"""
        adapter_with_mode = DevinCliAdapter(
            self.devin_cli_path,
            str(self.workspace),
            permission_mode='smart'
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = adapter_with_mode.invoke('test prompt')
            
            # Verify command includes permission mode parameter
            call_args = mock_run.call_args[0][0]
            self.assertIn('--permission-mode', call_args)
            self.assertIn('smart', call_args)

    def test_invoke_default_permission_mode(self):
        """Should default to dangerous permission mode"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = self.adapter.invoke('test prompt')
            
            # Verify command includes default permission mode
            call_args = mock_run.call_args[0][0]
            self.assertIn('--permission-mode', call_args)
            self.assertIn('dangerous', call_args)

    def test_invoke_timeout(self):
        """Should handle timeout gracefully"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('devin', 120)
            
            result = self.adapter.invoke('test prompt')
            
            self.assertFalse(result.success)
            self.assertEqual(result.exit_code, -1)
            self.assertIn('timed out', result.error.lower())

    def test_invoke_command_failure(self):
        """Should handle non-zero exit codes"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout=b'',
                stderr=b'Error occurred'
            )
            
            result = self.adapter.invoke('test prompt')
            
            self.assertFalse(result.success)
            self.assertEqual(result.exit_code, 1)
            self.assertIn('Error occurred', result.error)

    def test_invoke_encoding_errors(self):
        """Should handle encoding errors gracefully"""
        with patch('subprocess.run') as mock_run:
            # Simulate encoding error by raising an exception
            mock_run.side_effect = UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid')
            
            result = self.adapter.invoke('test prompt')
            
            # The current implementation doesn't catch UnicodeDecodeError specifically
            # but it should be handled by the general exception handler
            self.assertFalse(result.success)

    def test_context_manager(self):
        """Should support context manager interface"""
        with DevinCliAdapter(self.devin_cli_path, str(self.workspace)) as adapter:
            self.assertIsInstance(adapter, DevinCliAdapter)
            result = adapter.invoke('test prompt')
            self.assertTrue(result.success)

    def test_workspace_parameter(self):
        """Should use workspace directory for execution"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = self.adapter.invoke('test prompt')
            
            # Verify command was executed with workspace parameter
            call_kwargs = mock_run.call_args[1]
            self.assertIn('cwd', call_kwargs)
            self.assertEqual(call_kwargs['cwd'], str(self.workspace))

    def test_invoke_without_model(self):
        """Should work without model parameter"""
        adapter_no_model = DevinCliAdapter(self.devin_cli_path, str(self.workspace))
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = adapter_no_model.invoke('test prompt')
            
            # Verify command does not include model parameter
            call_args = mock_run.call_args[0][0]
            self.assertNotIn('--model', call_args)

    def test_invoke_custom_timeout(self):
        """Should use custom timeout when specified"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = self.adapter.invoke('test prompt', timeout=300)
            
            # Verify custom timeout was used
            call_kwargs = mock_run.call_args[1]
            self.assertEqual(call_kwargs['timeout'], 300)

    def test_invoke_default_timeout(self):
        """Should use default timeout when not specified"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Success',
                stderr=b''
            )
            
            result = self.adapter.invoke('test prompt')
            
            # Verify default timeout was used
            call_kwargs = mock_run.call_args[1]
            self.assertEqual(call_kwargs['timeout'], 120)

    def test_invoke_generic_exception(self):
        """Should handle generic exceptions gracefully"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception('Generic error')
            
            result = self.adapter.invoke('test prompt')
            
            self.assertFalse(result.success)
            self.assertEqual(result.exit_code, -1)
            self.assertIn('Generic error', result.error)

    def test_invoke_capture_output(self):
        """Should capture stdout and stderr"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=b'Stdout content',
                stderr=b'Stderr content'
            )
            
            result = self.adapter.invoke('test prompt')
            
            self.assertEqual(result.output, 'Stdout content')
            self.assertEqual(result.error, 'Stderr content')


if __name__ == '__main__':
    unittest.main()

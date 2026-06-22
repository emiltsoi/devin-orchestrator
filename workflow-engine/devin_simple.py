# -*- coding: utf-8 -*-
"""
Simple Devin CLI wrapper using non-interactive mode
Much simpler and more reliable than ACP for basic usage
"""

import subprocess
import json
import os


def run_devin_non_interactive(prompt, workspace=None, timeout=120):
    """
    Run devin-cli in non-interactive mode
    
    Args:
        prompt: The prompt to send to devin
        workspace: Working directory (defaults to current dir)
        timeout: Timeout in seconds (default: 120)
    
    Returns:
        dict: {
            'success': bool,
            'output': str,
            'error': str,
            'exit_code': int
        }
    """
    # Load devin_cli_path from config instead of hardcoding
    try:
        from config_loader import ConfigLoader
        config = ConfigLoader.load()
        devin_cli_path = config.devin_cli_path
    except Exception as e:
        # Fallback to environment variable if config loading fails
        devin_cli_path = os.getenv("DEVIN_CLI_PATH", "devin.exe")
    
    if workspace is None:
        workspace = os.getcwd()
    
    cmd = [devin_cli_path, '--permission-mode', 'dangerous', '--print', prompt]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace
        )
        
        return {
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr,
            'exit_code': result.returncode
        }
        
    except Exception as e:
        # Handle both timeout and other exceptions
        error_msg = str(e)
        if 'timed out' in error_msg.lower():
            return {
                'success': False,
                'output': '',
                'error': 'Command timed out after {} seconds'.format(timeout),
                'exit_code': -1
            }
        else:
            return {
                'success': False,
                'output': '',
                'error': error_msg,
                'exit_code': -1
            }


def test_simple():
    """Test the simple non-interactive wrapper"""
    print("=" * 60)
    print("Devin CLI Non-Interactive Test")
    print("=" * 60)
    
    # Use current directory instead of hardcoded path
    workspace = os.getcwd()
    prompt = "list the files in the current directory"
    
    print("\nWorkspace: {}".format(workspace))
    print("Prompt: {}".format(prompt))
    
    result = run_devin_non_interactive(prompt, workspace)
    
    print("\nSuccess: {}".format(result['success']))
    print("Exit code: {}".format(result['exit_code']))
    
    if result['output']:
        print("\nOutput:\n{}".format(result['output']))
    
    if result['error']:
        print("\nError:\n{}".format(result['error']))
    
    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)
    
    return result['success']


if __name__ == '__main__':
    test_simple()
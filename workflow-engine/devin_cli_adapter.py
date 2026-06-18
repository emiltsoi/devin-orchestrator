# -*- coding: utf-8 -*-
"""
Devin CLI Simple Adapter
Uses devin-cli's native --print flag for non-interactive execution
Much simpler and more reliable than ACP for basic usage
"""

import subprocess
import os
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class InvocationResult:
    """Result from devin-cli invocation"""
    success: bool
    output: str
    error: str
    exit_code: int


class DevinCliAdapter:
    """
    Devin CLI simple adapter using --print mode

    Uses devin-cli's native non-interactive mode for automated execution.
    Simpler and more reliable than ACP for basic skill invocation.
    """

    def __init__(self, devin_cli_path: str, workspace: Optional[str] = None, model: Optional[str] = None, permission_mode: str = "dangerous"):
        """
        Initialize devin-cli adapter

        Args:
            devin_cli_path: Path to devin.exe binary
            workspace: Optional workspace path (defaults to current directory)
            model: Optional model to use (e.g., "claude-sonnet-4", "claude-opus-4.6")
            permission_mode: Permission mode (auto, smart, dangerous) - defaults to dangerous for automated dispatch
        """
        self.devin_cli_path = devin_cli_path
        self.workspace = workspace or str(Path.cwd())
        self.model = model
        self.permission_mode = permission_mode

    def invoke(self, prompt: str, timeout: int = 120) -> InvocationResult:
        """
        Invoke devin-cli with a prompt in non-interactive mode

        Args:
            prompt: The prompt to send to devin
            timeout: Timeout in seconds (default: 120)

        Returns:
            InvocationResult with success status, output, and error
        """
        cmd = [self.devin_cli_path, '--permission-mode', self.permission_mode, '--print', prompt]

        # Add model if specified
        if self.model:
            cmd = [self.devin_cli_path, '--permission-mode', self.permission_mode, '--model', self.model, '--print', prompt]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',  # Handle encoding errors gracefully
                timeout=timeout,
                cwd=self.workspace
            )

            return InvocationResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode
            )

        except subprocess.TimeoutExpired:
            return InvocationResult(
                success=False,
                output='',
                error=f'Command timed out after {timeout} seconds',
                exit_code=-1
            )
        except Exception as e:
            return InvocationResult(
                success=False,
                output='',
                error=str(e),
                exit_code=-1
            )

    def __enter__(self):
        """Context manager entry (no-op for simple adapter)"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit (no-op for simple adapter)"""
        pass

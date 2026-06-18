# -*- coding: utf-8 -*-
"""
Devin CLI ACP Transport Adapter
Implements the Agent Client Protocol (ACP) for automated session management and prompt dispatch
"""

import subprocess
import json
import uuid
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ACPResponse:
    """ACP JSON-RPC response"""
    jsonrpc: str
    id: str
    result: Optional[Dict[str, Any]]
    error: Optional[Dict[str, Any]]


@dataclass
class SessionInfo:
    """Session information from ACP"""
    session_id: str
    status: str
    workspace: str


class DevinCliAdapter:
    """
    Devin CLI ACP transport adapter
    
    Communicates with devin-cli via ACP (JSON-RPC 2.0 over stdin/stdout)
    for automated session management and prompt dispatch.
    """

    def __init__(self, devin_cli_path: str, workspace: Optional[str] = None):
        """
        Initialize devin-cli adapter

        Args:
            devin_cli_path: Path to devin.exe binary
            workspace: Optional workspace path (defaults to current directory)
        """
        self.devin_cli_path = devin_cli_path
        self.workspace = workspace or str(Path.cwd())
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0

    def start(self) -> None:
        """Start devin-cli in ACP mode"""
        cmd = [self.devin_cli_path, 'acp', '--workspace', self.workspace]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,  # Binary mode for proper framing
            bufsize=0  # Unbuffered
        )

        # Initialize ACP protocol
        self._initialize()

    def stop(self) -> None:
        """Stop devin-cli process"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

    def _initialize(self) -> None:
        """Initialize ACP protocol handshake"""
        init_params = {
            "processId": str(os.getpid()),
            "rootUri": str(Path(self.workspace).as_uri()),
            "capabilities": {}
        }
        self._send_request('initialize', init_params)

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> ACPResponse:
        """
        Send JSON-RPC request to devin-cli

        Args:
            method: ACP method name (e.g., 'session/new')
            params: Method parameters

        Returns:
            ACPResponse with result or error
        """
        if not self.process:
            raise RuntimeError("Devin-cli process not started")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": str(self.request_id)
        }

        # Send request with LSP-style Content-Length framing
        request_json = json.dumps(request)
        content_length = len(request_json.encode('utf-8'))
        framed_request = f"Content-Length: {content_length}\r\n\r\n{request_json}".encode('utf-8')
        self.process.stdin.write(framed_request)
        self.process.stdin.flush()

        # Read response with LSP-style framing
        response = self._read_framed_response()
        if not response:
            raise RuntimeError("No response from devin-cli")

        response_data = json.loads(response.decode('utf-8'))
        return ACPResponse(
            jsonrpc=response_data.get('jsonrpc', '2.0'),
            id=response_data.get('id', ''),
            result=response_data.get('result'),
            error=response_data.get('error')
        )

    def _read_framed_response(self) -> Optional[bytes]:
        """
        Read LSP-style framed response from devin-cli

        Returns:
            JSON response bytes or None
        """
        # Read Content-Length header
        header_line = self.process.stdout.readline()
        if not header_line:
            return None

        header_str = header_line.decode('utf-8').strip()
        if not header_str.startswith('Content-Length:'):
            raise RuntimeError(f"Invalid response header: {header_str}")

        content_length = int(header_str.split(':')[1].strip())

        # Read empty line after header
        empty_line = self.process.stdout.readline()
        if empty_line.decode('utf-8').strip() != '':
            raise RuntimeError("Expected empty line after header")

        # Read JSON body
        body = self.process.stdout.read(content_length)
        return body

    def session_new(self, session_id: str, description: str) -> SessionInfo:
        """
        Create a new session

        Args:
            session_id: Session identifier
            description: Session description

        Returns:
            SessionInfo with session details
        """
        params = {
            "session_id": session_id,
            "description": description
        }

        response = self._send_request('session/new', params)

        if response.error:
            raise RuntimeError(f"session/new failed: {response.error}")

        result = response.result
        return SessionInfo(
            session_id=result['session_id'],
            status=result['status'],
            workspace=result.get('workspace', self.workspace)
        )

    def session_prompt(self, session_id: str, prompt: str) -> Dict[str, Any]:
        """
        Send a prompt to a session

        Args:
            session_id: Session identifier
            prompt: Prompt text

        Returns:
            Response data from the session
        """
        params = {
            "session_id": session_id,
            "prompt": prompt
        }

        response = self._send_request('session/prompt', params)

        if response.error:
            raise RuntimeError(f"session/prompt failed: {response.error}")

        return response.result

    def session_cancel(self, session_id: str) -> bool:
        """
        Cancel a session

        Args:
            session_id: Session identifier

        Returns:
            True if cancelled successfully
        """
        params = {
            "session_id": session_id
        }

        response = self._send_request('session/cancel', params)

        if response.error:
            raise RuntimeError(f"session/cancel failed: {response.error}")

        return response.result.get('cancelled', False)

    def session_list(self) -> List[SessionInfo]:
        """
        List all active sessions

        Returns:
            List of SessionInfo objects
        """
        response = self._send_request('session/list', {})

        if response.error:
            raise RuntimeError(f"session/list failed: {response.error}")

        sessions = []
        for session_data in response.result.get('sessions', []):
            sessions.append(SessionInfo(
                session_id=session_data['session_id'],
                status=session_data['status'],
                workspace=session_data.get('workspace', self.workspace)
            ))

        return sessions

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()

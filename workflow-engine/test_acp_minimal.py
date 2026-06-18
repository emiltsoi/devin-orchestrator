# -*- coding: utf-8 -*-
"""
Minimal ACP Test Script
Tests basic communication with devin-cli ACP mode
"""

import subprocess
import json
import os
from pathlib import Path


def test_acp_minimal():
    """Test minimal ACP communication"""
    print("=" * 60)
    print("Minimal ACP Test")
    print("=" * 60)

    devin_cli_path = r"C:\Users\<username>\AppData\Local\devin\cli\bin\devin.exe"
    workspace = r"C:\Users\<username>\OneDrive\Documents\Work\devin-orchestrator"

    print(f"\nDevin CLI: {devin_cli_path}")
    print(f"Workspace: {workspace}")

    # Start devin-cli in ACP mode
    cmd = [devin_cli_path, 'acp']
    print(f"\nCommand: {' '.join(cmd)}")

    # Change to workspace directory before starting
    original_cwd = os.getcwd()
    os.chdir(workspace)

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,  # Text mode (Windows compatible)
        bufsize=1,
        cwd=workspace  # Set working directory
    )

    os.chdir(original_cwd)

    # Check if process started
    if process.poll() is not None:
        stderr_output = process.stderr.read()
        print(f"\nProcess failed to start: {stderr_output}")
        return False

    print("Process started successfully")

    # Check if process is still alive before writing
    import time
    time.sleep(0.5)
    if process.poll() is not None:
        print("Process terminated unexpectedly")
        # Try to read stderr to see why
        stderr_output = process.stderr.read()
        print(f"Stderr: {stderr_output}")
        return False

    # Try to read any initial output from devin-cli
    print("\nChecking for initial output...")
    import threading
    initial_output = None

    def read_initial():
        nonlocal initial_output
        try:
            initial_output = process.stdout.readline()
        except:
            pass

    thread = threading.Thread(target=read_initial)
    thread.daemon = True
    thread.start()
    thread.join(timeout=1.0)

    if initial_output:
        print(f"Initial output: {initial_output}")
    else:
        print("No initial output from devin-cli")

    # Try sending a simple session/new request (skip initialize)
    print("\nSending session/new request (skip initialize)...")
    request = {
        "jsonrpc": "2.0",
        "method": "session/new",
        "params": {
            "session_id": "test-session-001",
            "description": "Test session"
        },
        "id": "1"
    }

    request_json = json.dumps(request)
    content_length = len(request_json.encode('utf-8'))
    framed_request = f"Content-Length: {content_length}\r\n\r\n{request_json}"

    print(f"Request JSON: {request_json}")
    print(f"Content-Length: {content_length}")
    print(f"Framed request: {repr(framed_request[:100])}...")

    try:
        # Try writing using communicate() instead with longer timeout
        output, error = process.communicate(input=framed_request, timeout=30)
        print(f"Output: {output}")
        print(f"Error: {error}")

        if output:
            response = json.loads(output.strip())
            print(f"Parsed response: {json.dumps(response, indent=2)}")
        else:
            print("No output received")

    except subprocess.TimeoutExpired:
        print("Process timed out even with 30s timeout")
        process.kill()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)


if __name__ == '__main__':
    test_acp_minimal()

# -*- coding: utf-8 -*-
"""
Minimal ACP Test Script
Tests basic communication with devin-cli ACP mode using Python 3 to call batch file
"""

import subprocess
import json
import os


def test_acp_minimal():
    """Test minimal ACP communication by calling the working batch file"""
    print("=" * 60)
    print("Minimal ACP Test (Python 3 + Batch File)")
    print("=" * 60)

    workspace = r"C:\Users\<username>\OneDrive\Documents\Work\devin-orchestrator"
    batch_file = r"C:\Users\<username>\OneDrive\Documents\Work\devin-orchestrator\workflow-engine\test_acp_simple.bat"

    print(f"\nWorkspace: {workspace}")
    print(f"Batch file: {batch_file}")

    try:
        # Run the batch file using subprocess
        result = subprocess.run(
            f'cmd /c "{batch_file}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=workspace
        )
        
        print(f"Process exit code: {result.returncode}")
        
        if result.stderr:
            print(f"Stderr: {result.stderr}")
        
        if result.stdout:
            print(f"Raw output length: {len(result.stdout)}")
            
            # Extract JSON from output (it may be mixed with log lines)
            lines = result.stdout.split('\n')
            json_lines = [line for line in lines if line.strip().startswith('{')]
            
            if json_lines:
                json_response = json_lines[0]
                print(f"JSON response: {json_response}")
                
                try:
                    init_response = json.loads(json_response)
                    print(f"Parsed initialize response: {json.dumps(init_response, indent=2)}")
                    
                    # Check if authentication is required
                    if 'authMethods' in init_response.get('result', {}):
                        auth_methods = init_response['result']['authMethods']
                        print(f"\nAuthentication required. Available methods: {auth_methods}")
                        print("Note: For full functionality, implement authenticate step")
                    
                    print("\n" + "=" * 60)
                    print("Test complete - ACP connection successful!")
                    print("=" * 60)
                    return True
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON: {e}")
            else:
                print("No JSON response found in output")
                print("Full output:")
                print(result.stdout)
        else:
            print("No output received")
        
        return False

    except subprocess.TimeoutExpired:
        print("Process timed out")
        return False
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    test_acp_minimal()

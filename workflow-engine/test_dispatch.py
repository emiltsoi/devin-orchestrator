# -*- coding: utf-8 -*-
"""
Test Automated Dispatch
Tests the skill invoker with devin-cli transport adapter
"""

import sys
import os
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from step_executor import StepExecutor


def test_automated_dispatch():
    """Test automated dispatch with devin-cli"""
    print("=" * 60)
    print("Automated Dispatch Test")
    print("=" * 60)

    # Setup paths
    harness_root = Path(__file__).parent.parent
    work_dir = harness_root / 'work'

    print(f"\nHarness root: {harness_root}")
    print(f"Work directory: {work_dir}")

    # Devin CLI path - from environment variable or default
    devin_cli_path = os.environ.get('DEVIN_CLI_PATH')

    # Default path for Windows (adjust as needed)
    if not devin_cli_path and os.name == 'nt':
        devin_cli_path = r"C:\Users\<username>\AppData\Local\devin\cli\bin\devin.exe"

    if not devin_cli_path:
        print("Skipping automated dispatch test (no DEVIN_CLI_PATH set)")
        print("Set DEVIN_CLI_PATH environment variable to test automated dispatch")
        return 0

    if not os.path.exists(devin_cli_path):
        print(f"Skipping automated dispatch test (devin-cli not found: {devin_cli_path})")
        return 0

    print(f"Using devin-cli: {devin_cli_path}")

    # Model selection (optional)
    model = os.environ.get('DEVIN_MODEL')
    if model:
        print(f"Using model: {model}")

    # Permission mode (defaults to dangerous for automated dispatch)
    permission_mode = os.environ.get('DEVIN_PERMISSION_MODE', 'dangerous')
    print(f"Using permission mode: {permission_mode}")

    # Max retries (default 2)
    max_retries = int(os.environ.get('DEVIN_MAX_RETRIES', '2'))
    print(f"Max retries: {max_retries}")

    # Enable semantic evaluation (default False)
    enable_semantic = os.environ.get('DEVIN_ENABLE_SEMANTIC', 'false').lower() == 'true'
    print(f"Semantic evaluation: {enable_semantic}")

    # Create executor with automated dispatch
    executor = StepExecutor(
        harness_root,
        work_dir,
        interactive=False,  # Use automated dispatch
        devin_cli_path=devin_cli_path,
        model=model,  # Optional model selection
        permission_mode=permission_mode,  # Permission mode for artifact creation
        max_retries=max_retries  # Max retry attempts
    )

    # Enable semantic evaluation if requested
    if enable_semantic:
        executor.skill_evaluator.enable_semantic = True

    # Execute workflow with unique session ID to avoid artifact contamination
    import time
    session_id = f"FEATURE-DISPATCH-{int(time.time())}"
    print("\nStarting workflow execution (automated dispatch mode)...")
    success = executor.execute_workflow('feature.manifest.yaml', session_id)

    if success:
        print("\n" + "=" * 60)
        print("Automated Dispatch Test: PASSED")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("Automated Dispatch Test: FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(test_automated_dispatch())

# -*- coding: utf-8 -*-
"""
Test Automated Dispatch
Tests the skill invoker with devin-cli transport adapter
"""

import sys
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

    # Devin CLI path - adjust as needed
    # Example: C:\Users\etsoi\AppData\Local\Programs\Windsurf\resources\app\extensions\windsurf\devin\bin\devin.exe
    devin_cli_path = input("\nEnter devin.exe path (or press Enter to skip): ").strip()

    if not devin_cli_path:
        print("Skipping automated dispatch test (no devin-cli path provided)")
        return 0

    # Create executor with automated dispatch
    executor = StepExecutor(
        harness_root,
        work_dir,
        interactive=False,  # Use automated dispatch
        devin_cli_path=devin_cli_path
    )

    # Execute workflow
    print("\nStarting workflow execution (automated dispatch mode)...")
    success = executor.execute_workflow('feature.manifest.yaml', 'FEATURE-DISPATCH-001')

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

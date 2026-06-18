"""
Phase 1 End-to-End Test
Tests the basic workflow engine with the feature workflow
"""

import sys
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from step_executor import StepExecutor


def test_phase1():
    """Test Phase 1 workflow engine end-to-end"""
    print("=" * 60)
    print("Phase 1 End-to-End Test")
    print("=" * 60)

    # Setup paths
    harness_root = Path(__file__).parent.parent
    work_dir = harness_root / 'work'

    print("\nHarness root: {}".format(harness_root))
    print("Work directory: {}".format(work_dir))

    # Create executor
    executor = StepExecutor(harness_root, work_dir)

    # Execute workflow
    print("\nStarting workflow execution...")
    success = executor.execute_workflow('feature.manifest.yaml', 'FEATURE-TEST-001')

    if success:
        print("\n" + "=" * 60)
        print("Phase 1 Test: PASSED")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("Phase 1 Test: FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(test_phase1())

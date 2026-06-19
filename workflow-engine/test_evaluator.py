# -*- coding: utf-8 -*-
"""
Test Skill Evaluator - Direct evaluation testing
Tests the confidence scoring and decision logic without full workflow
"""

import sys
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from skill_evaluator import SkillEvaluator, EvaluationResult


def test_evaluator():
    """Test skill evaluator with various artifact scenarios"""
    print("=" * 60)
    print("Skill Evaluator Test")
    print("=" * 60)

    harness_root = Path(__file__).parent.parent
    evaluator = SkillEvaluator(harness_root)

    # Test 1: Empty artifact (should fail)
    print("\n[Test 1] Empty artifact")
    empty_path = Path(__file__).parent / 'test_empty.md'
    empty_path.write_text('', encoding='utf-8')
    result = evaluator.evaluate_skill_output('test-driven-development', empty_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    empty_path.unlink()

    # Test 2: Placeholder artifact (should fail)
    print("\n[Test 2] Placeholder artifact")
    placeholder_path = Path(__file__).parent / 'test_placeholder.md'
    placeholder_path.write_text('# PLACEHOLDER\n\nTODO: implement', encoding='utf-8')
    result = evaluator.evaluate_skill_output('writing-plans', placeholder_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    placeholder_path.unlink()

    # Test 3: Valid artifact with passing tests (should pass)
    print("\n[Test 3] Valid artifact with passing tests")
    valid_path = Path(__file__).parent / 'test_valid.md'
    valid_path.write_text('''# Test Results

All tests passed successfully.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors

Build status: OK
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('verification-before-completion', valid_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    valid_path.unlink()

    # Test 4: Valid artifact with failing tests (should fail)
    print("\n[Test 4] Valid artifact with failing tests")
    failing_path = Path(__file__).parent / 'test_failing.md'
    failing_path.write_text('''# Test Results

Some tests failed.

## Summary
- 65/70 tests passed
- 5 failed
- 0 errors

Build status: OK
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('verification-before-completion', failing_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    failing_path.unlink()

    # Test 5: Valid YAML artifact (should pass)
    print("\n[Test 5] Valid YAML artifact")
    yaml_path = Path(__file__).parent / 'test_valid.yaml'
    yaml_path.write_text('''
name: test
version: 1.0
steps:
  - step1
  - step2
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('writing-plans', yaml_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    yaml_path.unlink()

    # Test 6: Invalid YAML artifact (should fail)
    print("\n[Test 6] Invalid YAML artifact")
    invalid_yaml_path = Path(__file__).parent / 'test_invalid.yaml'
    invalid_yaml_path.write_text('''
name: test
version: 1.0
steps:
  - step1
  - [unclosed bracket
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('writing-plans', invalid_yaml_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    invalid_yaml_path.unlink()

    # Test 7: Confidence threshold boundaries (0.9 auto-approve, 0.7 user review)
    print("\n[Test 7] Confidence threshold boundaries")
    boundary_path = Path(__file__).parent / 'test_boundary.md'
    boundary_path.write_text('''# Test Results

Some minor issues but mostly complete.

## Summary
- 68/70 tests passed
- 2 failed
- 0 errors

Build status: OK
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('verification-before-completion', boundary_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Auto-approvable: {result.auto_approvable}")
    print(f"Requires user input: {result.requires_user_input}")
    # Should have confidence < 0.9 due to test failures, require user input
    assert result.confidence < 0.9, f"Expected confidence < 0.9, got {result.confidence}"
    assert result.requires_user_input, "Should require user input for medium confidence"
    boundary_path.unlink()

    # Test 8: High confidence auto-approval (>= 0.9)
    print("\n[Test 8] High confidence auto-approval")
    high_conf_path = Path(__file__).parent / 'test_high_conf.md'
    high_conf_path.write_text('''# Test Results

All tests passed successfully.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors

Build status: OK
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('verification-before-completion', high_conf_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Auto-approvable: {result.auto_approvable}")
    # Should have confidence >= 0.9 and be auto-approvable
    assert result.confidence >= 0.9, f"Expected confidence >= 0.9, got {result.confidence}"
    assert result.auto_approvable, "Should be auto-approvable for high confidence"
    high_conf_path.unlink()

    # Test 9: Low confidence requiring user gate (< 0.7)
    print("\n[Test 9] Low confidence requiring user gate")
    low_conf_path = Path(__file__).parent / 'test_low_conf.md'
    low_conf_path.write_text('''# Test Results

Multiple failures.

## Summary
- 45/70 tests passed
- 25 failed
- 0 errors

Build status: FAILED

TODO: fix the failing tests
''', encoding='utf-8')
    result = evaluator.evaluate_skill_output('verification-before-completion', low_conf_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Requires user input: {result.requires_user_input}")
    # Should have confidence < 0.7 and require user input
    # (test failure -0.3 + placeholder/structural -0.3 = 0.4 confidence)
    assert result.confidence < 0.7, f"Expected confidence < 0.7, got {result.confidence}"
    assert result.requires_user_input, "Should require user input for low confidence"
    low_conf_path.unlink()

    print("\n" + "=" * 60)
    print("Skill Evaluator Test: COMPLETED")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(test_evaluator())

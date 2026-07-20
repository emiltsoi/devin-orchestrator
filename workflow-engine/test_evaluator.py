"""
Test Skill Evaluator - Direct evaluation testing
Tests the confidence scoring and decision logic without full workflow
"""

import sys
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from floor_validator import validate_format, validate_iron_law, validate_structural
from skill_evaluator import SkillEvaluator


def test_evaluator():
    """Test skill evaluator with various artifact scenarios"""
    print("=" * 60)
    print("Skill Evaluator Test")
    print("=" * 60)

    harness_root = Path(__file__).parent.parent
    evaluator = SkillEvaluator(harness_root)

    # Test 1: Empty artifact (should fail)
    print("\n[Test 1] Empty artifact")
    empty_path = Path(__file__).parent / "test_empty.md"
    empty_path.write_text("", encoding="utf-8")
    result = evaluator.evaluate_skill_output("test-driven-development", empty_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    empty_path.unlink()

    # Test 2: Placeholder artifact (should fail)
    print("\n[Test 2] Placeholder artifact")
    placeholder_path = Path(__file__).parent / "test_placeholder.md"
    placeholder_path.write_text("# PLACEHOLDER\n\nTODO: implement", encoding="utf-8")
    result = evaluator.evaluate_skill_output("writing-plans", placeholder_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    placeholder_path.unlink()

    # Test 3: Valid artifact with passing tests (should pass)
    print("\n[Test 3] Valid artifact with passing tests")
    valid_path = Path(__file__).parent / "test_valid.md"
    valid_path.write_text(
        """# Test Results

All tests passed successfully.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors

Build status: OK
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output(
        "verification-before-completion", valid_path, {}
    )
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    valid_path.unlink()

    # Test 4: Valid artifact with failing tests (should fail)
    print("\n[Test 4] Valid artifact with failing tests")
    failing_path = Path(__file__).parent / "test_failing.md"
    failing_path.write_text(
        """# Test Results

Some tests failed.

## Summary
- 65/70 tests passed
- 5 failed
- 0 errors

Build status: OK
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output(
        "verification-before-completion", failing_path, {}
    )
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    failing_path.unlink()

    # Test 5: Valid YAML artifact (should pass)
    print("\n[Test 5] Valid YAML artifact")
    yaml_path = Path(__file__).parent / "test_valid.yaml"
    yaml_path.write_text(
        """
name: test
version: 1.0
steps:
  - step1
  - step2
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output("writing-plans", yaml_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    yaml_path.unlink()

    # Test 6: Invalid YAML artifact (should fail)
    print("\n[Test 6] Invalid YAML artifact")
    invalid_yaml_path = Path(__file__).parent / "test_invalid.yaml"
    invalid_yaml_path.write_text(
        """
name: test
version: 1.0
steps:
  - step1
  - [unclosed bracket
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output("writing-plans", invalid_yaml_path, {})
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Issues: {result.issues}")
    print(f"Auto-approvable: {result.auto_approvable}")
    invalid_yaml_path.unlink()

    # Test 7: Confidence threshold boundaries (0.9 auto-approve, 0.7 user review)
    print("\n[Test 7] Confidence threshold boundaries")
    boundary_path = Path(__file__).parent / "test_boundary.md"
    boundary_path.write_text(
        """# Test Results

Some minor issues but mostly complete.

## Summary
- 68/70 tests passed
- 2 failed
- 0 errors

Build status: OK
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output(
        "verification-before-completion", boundary_path, {}
    )
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Auto-approvable: {result.auto_approvable}")
    print(f"Requires user input: {result.requires_user_input}")
    # Should have confidence < 0.9 due to test failures, require user input
    assert result.confidence < 0.9, (
        f"Expected confidence < 0.9, got {result.confidence}"
    )
    assert result.requires_user_input, "Should require user input for medium confidence"
    boundary_path.unlink()

    # Test 8: High confidence auto-approval (>= 0.9)
    print("\n[Test 8] High confidence auto-approval")
    high_conf_path = Path(__file__).parent / "test_high_conf.md"
    high_conf_path.write_text(
        """# Test Results

All tests passed successfully.

## Summary
- 70/70 tests passed
- 0 failed
- 0 errors

Build status: OK
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output(
        "verification-before-completion", high_conf_path, {}
    )
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Auto-approvable: {result.auto_approvable}")
    # Should have confidence >= 0.9 and be auto-approvable
    assert result.confidence >= 0.9, (
        f"Expected confidence >= 0.9, got {result.confidence}"
    )
    assert result.auto_approvable, "Should be auto-approvable for high confidence"
    high_conf_path.unlink()

    # Test 9: Low confidence requiring user gate (< 0.7)
    print("\n[Test 9] Low confidence requiring user gate")
    low_conf_path = Path(__file__).parent / "test_low_conf.md"
    low_conf_path.write_text(
        """# Test Results

Multiple failures.

## Summary
- 45/70 tests passed
- 25 failed
- 0 errors

Build status: FAILED

TODO: fix the failing tests
""",
        encoding="utf-8",
    )
    result = evaluator.evaluate_skill_output(
        "verification-before-completion", low_conf_path, {}
    )
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Requires user input: {result.requires_user_input}")
    # Should have confidence < 0.7 and require user input
    # (test failure -0.3 + placeholder/structural -0.3 = 0.4 confidence)
    assert result.confidence < 0.7, (
        f"Expected confidence < 0.7, got {result.confidence}"
    )
    assert result.requires_user_input, "Should require user input for low confidence"
    low_conf_path.unlink()

    # Test 10: Direct floor_validator - validate_structural
    print("\n[Test 10] Direct floor_validator - validate_structural")
    test_path = Path(__file__).parent / "test_structural.md"
    test_path.write_text(
        "# Valid content\n\nThis is complete content.", encoding="utf-8"
    )
    structural_result = validate_structural(test_path)
    print(f"Structural result: {structural_result}")
    assert structural_result["result"] == "PASS", (
        f"Expected PASS, got {structural_result['result']}"
    )
    assert len(structural_result["failures"]) == 0, (
        f"Expected no failures, got {structural_result['failures']}"
    )
    test_path.unlink()

    # Test 11: Direct floor_validator - validate_structural with placeholder
    print("\n[Test 11] Direct floor_validator - validate_structural with placeholder")
    placeholder_path = Path(__file__).parent / "test_placeholder_struct.md"
    placeholder_path.write_text(
        "# PLACEHOLDER\n\nTODO: implement this", encoding="utf-8"
    )
    structural_result = validate_structural(placeholder_path)
    print(f"Structural result: {structural_result}")
    assert structural_result["result"] == "FAIL", (
        f"Expected FAIL, got {structural_result['result']}"
    )
    assert len(structural_result["failures"]) > 0, "Expected failures for placeholder"
    placeholder_path.unlink()

    # Test 12: Direct floor_validator - validate_iron_law
    print("\n[Test 12] Direct floor_validator - validate_iron_law")
    iron_law_path = Path(__file__).parent / "test_iron_law.md"
    iron_law_path.write_text(
        "# Test Results\n\nAll tests passed: 70/70", encoding="utf-8"
    )
    iron_law_text = "Must include tests and no placeholders"
    iron_law_result = validate_iron_law(iron_law_path, iron_law_text)
    print(f"Iron Law result: {iron_law_result}")
    assert iron_law_result["result"] == "PASS", (
        f"Expected PASS, got {iron_law_result['result']}"
    )
    iron_law_path.unlink()

    # Test 13: Direct floor_validator - validate_iron_law with violation
    print("\n[Test 13] Direct floor_validator - validate_iron_law with violation")
    violation_path = Path(__file__).parent / "test_iron_law_violation.md"
    violation_path.write_text(
        "# Some content\n\nTODO: add tests later", encoding="utf-8"
    )
    iron_law_text = "Must include tests and no placeholders"
    iron_law_result = validate_iron_law(violation_path, iron_law_text)
    print(f"Iron Law result: {iron_law_result}")
    assert iron_law_result["result"] == "FAIL", (
        f"Expected FAIL, got {iron_law_result['result']}"
    )
    assert len(iron_law_result["failures"]) > 0, (
        "Expected failures for Iron Law violation"
    )
    violation_path.unlink()

    # Test 14: Direct floor_validator - validate_format (YAML)
    print("\n[Test 14] Direct floor_validator - validate_format (YAML)")
    yaml_path = Path(__file__).parent / "test_format.yaml"
    yaml_path.write_text("name: test\nversion: 1.0\n", encoding="utf-8")
    format_result = validate_format(yaml_path)
    print(f"Format result: {format_result}")
    assert format_result["result"] == "PASS", (
        f"Expected PASS, got {format_result['result']}"
    )
    assert format_result["checked"] == True, "Expected YAML to be checked"
    yaml_path.unlink()

    # Test 15: Direct floor_validator - validate_format (invalid YAML)
    print("\n[Test 15] Direct floor_validator - validate_format (invalid YAML)")
    invalid_yaml_path = Path(__file__).parent / "test_invalid_format.yaml"
    invalid_yaml_path.write_text("name: test\nversion: [unclosed", encoding="utf-8")
    format_result = validate_format(invalid_yaml_path)
    print(f"Format result: {format_result}")
    assert format_result["result"] == "FAIL", (
        f"Expected FAIL, got {format_result['result']}"
    )
    assert format_result["checked"] == True, "Expected YAML to be checked"
    invalid_yaml_path.unlink()

    # Test 16: Direct floor_validator - validate_format (Markdown - not checked)
    print(
        "\n[Test 16] Direct floor_validator - validate_format (Markdown - not checked)"
    )
    md_path = Path(__file__).parent / "test_format.md"
    md_path.write_text(
        "# Markdown content\n\nNo format validation needed.", encoding="utf-8"
    )
    format_result = validate_format(md_path)
    print(f"Format result: {format_result}")
    assert format_result["result"] == "PASS", (
        f"Expected PASS, got {format_result['result']}"
    )
    assert format_result["checked"] == False, "Expected Markdown to not be checked"
    md_path.unlink()

    print("\n" + "=" * 60)
    print("Skill Evaluator Test: COMPLETED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(test_evaluator())

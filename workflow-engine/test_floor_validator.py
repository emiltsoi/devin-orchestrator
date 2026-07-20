"""
Test Floor Validator - Comprehensive testing of floor_validator module
Tests structural, Iron Law, and format validation functions
"""

import sys
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from floor_validator import validate_format, validate_iron_law, validate_structural


def test_floor_validator():
    """Comprehensive test of floor_validator module functions"""
    print("=" * 60)
    print("Floor Validator Module Test")
    print("=" * 60)

    # Test validate_structural
    print("\n[Section 1] Testing validate_structural")
    print("-" * 60)

    # Test 1.1: Non-existent file
    print("\n[Test 1.1] Non-existent file")
    non_existent = Path(__file__).parent / "non_existent.md"
    result = validate_structural(non_existent)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for non-existent file"
    assert len(result["failures"]) > 0, "Expected failures for non-existent file"

    # Test 1.2: Empty file
    print("\n[Test 1.2] Empty file")
    empty_file = Path(__file__).parent / "test_empty.md"
    empty_file.write_text("", encoding="utf-8")
    result = validate_structural(empty_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for empty file"
    assert len(result["failures"]) > 0, "Expected failures for empty file"
    empty_file.unlink()

    # Test 1.3: Valid file with content
    print("\n[Test 1.3] Valid file with content")
    valid_file = Path(__file__).parent / "test_valid.md"
    valid_file.write_text("# Valid Content\n\nThis is real content.", encoding="utf-8")
    result = validate_structural(valid_file)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for valid file"
    assert len(result["failures"]) == 0, "Expected no failures for valid file"
    valid_file.unlink()

    # Test 1.4: File with PLACEHOLDER pattern
    print("\n[Test 1.4] File with PLACEHOLDER pattern")
    placeholder_file = Path(__file__).parent / "test_placeholder.md"
    placeholder_file.write_text("# PLACEHOLDER\n\nContent here.", encoding="utf-8")
    result = validate_structural(placeholder_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for PLACEHOLDER"
    assert len(result["failures"]) > 0, "Expected failures for PLACEHOLDER"
    placeholder_file.unlink()

    # Test 1.5: File with TODO pattern
    print("\n[Test 1.5] File with TODO pattern")
    todo_file = Path(__file__).parent / "test_todo.md"
    todo_file.write_text("# Some Content\n\nTODO: implement this.", encoding="utf-8")
    result = validate_structural(todo_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for TODO"
    assert len(result["failures"]) > 0, "Expected failures for TODO"
    todo_file.unlink()

    # Test 1.6: File with TBD pattern
    print("\n[Test 1.6] File with TBD pattern")
    tbd_file = Path(__file__).parent / "test_tbd.md"
    tbd_file.write_text("# Some Content\n\nTBD: to be determined.", encoding="utf-8")
    result = validate_structural(tbd_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for TBD"
    assert len(result["failures"]) > 0, "Expected failures for TBD"
    tbd_file.unlink()

    # Test 1.7: File with "Created after dispatch failure" pattern
    print("\n[Test 1.7] File with dispatch failure pattern")
    dispatch_file = Path(__file__).parent / "test_dispatch.md"
    dispatch_file.write_text(
        "# Some Content\n\nCreated after dispatch failure.", encoding="utf-8"
    )
    result = validate_structural(dispatch_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for dispatch failure pattern"
    assert len(result["failures"]) > 0, "Expected failures for dispatch failure pattern"
    dispatch_file.unlink()

    # Test 1.8: File with HTML comment placeholder
    print("\n[Test 1.8] File with HTML comment placeholder")
    html_file = Path(__file__).parent / "test_html.md"
    html_file.write_text(
        "# Some Content\n\n<!-- placeholder comment -->", encoding="utf-8"
    )
    result = validate_structural(html_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for HTML comment placeholder"
    assert len(result["failures"]) > 0, "Expected failures for HTML comment placeholder"
    html_file.unlink()

    # Test 1.9: File with whitespace only
    print("\n[Test 1.9] File with whitespace only")
    whitespace_file = Path(__file__).parent / "test_whitespace.md"
    whitespace_file.write_text("   \n\n  \n", encoding="utf-8")
    result = validate_structural(whitespace_file)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for whitespace-only file"
    assert len(result["failures"]) > 0, "Expected failures for whitespace-only file"
    whitespace_file.unlink()

    print("\n[OK] All validate_structural tests passed")

    # Test validate_iron_law
    print("\n[Section 2] Testing validate_iron_law")
    print("-" * 60)

    # Test 2.1: Empty Iron Law (should pass)
    print("\n[Test 2.1] Empty Iron Law")
    test_file = Path(__file__).parent / "test_iron_law_empty.md"
    test_file.write_text("# Content\n\nSome content here.", encoding="utf-8")
    result = validate_iron_law(test_file, "")
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for empty Iron Law"
    assert len(result["failures"]) == 0, "Expected no failures for empty Iron Law"
    test_file.unlink()

    # Test 2.2: Iron Law requiring tests - with tests
    print("\n[Test 2.2] Iron Law requiring tests - with tests")
    test_file = Path(__file__).parent / "test_iron_law_tests.md"
    test_file.write_text("# Test Results\n\nAll tests passed: 70/70", encoding="utf-8")
    iron_law = "Must include comprehensive tests"
    result = validate_iron_law(test_file, iron_law)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS when tests present"
    assert len(result["failures"]) == 0, "Expected no failures when tests present"
    test_file.unlink()

    # Test 2.3: Iron Law requiring tests - without tests
    print("\n[Test 2.3] Iron Law requiring tests - without tests")
    test_file = Path(__file__).parent / "test_iron_law_no_tests.md"
    test_file.write_text(
        "# Content\n\nSome content but no verification.", encoding="utf-8"
    )
    iron_law = "Must include comprehensive tests"
    result = validate_iron_law(test_file, iron_law)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL when tests missing"
    assert len(result["failures"]) > 0, "Expected failures when tests missing"
    test_file.unlink()

    # Test 2.4: Iron Law prohibiting placeholders - without placeholders
    print("\n[Test 2.4] Iron Law prohibiting placeholders - without placeholders")
    test_file = Path(__file__).parent / "test_iron_law_no_placeholder.md"
    test_file.write_text(
        "# Content\n\nComplete content without issues.", encoding="utf-8"
    )
    iron_law = "No placeholder allowed"
    result = validate_iron_law(test_file, iron_law)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS when no placeholders"
    assert len(result["failures"]) == 0, "Expected no failures when no placeholders"
    test_file.unlink()

    # Test 2.5: Iron Law prohibiting placeholders - with placeholders
    print("\n[Test 2.5] Iron Law prohibiting placeholders - with placeholders")
    test_file = Path(__file__).parent / "test_iron_law_with_placeholder.md"
    test_file.write_text("# Content\n\nTODO: implement this.", encoding="utf-8")
    iron_law = "No placeholder allowed"
    result = validate_iron_law(test_file, iron_law)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL when placeholders present"
    assert len(result["failures"]) > 0, "Expected failures when placeholders present"
    test_file.unlink()

    # Test 2.6: Non-existent file with Iron Law
    print("\n[Test 2.6] Non-existent file with Iron Law")
    non_existent = Path(__file__).parent / "non_existent_iron.md"
    iron_law = "Some requirement"
    result = validate_iron_law(non_existent, iron_law)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for non-existent file"
    assert len(result["failures"]) > 0, "Expected failures for non-existent file"

    print("\n[OK] All validate_iron_law tests passed")

    # Test validate_format
    print("\n[Section 3] Testing validate_format")
    print("-" * 60)

    # Test 3.1: Valid YAML file
    print("\n[Test 3.1] Valid YAML file")
    yaml_file = Path(__file__).parent / "test_valid.yaml"
    yaml_file.write_text(
        "name: test\nversion: 1.0\nsteps:\n  - step1\n  - step2\n", encoding="utf-8"
    )
    result = validate_format(yaml_file)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for valid YAML"
    assert result["checked"] == True, "Expected YAML to be checked"
    assert len(result["failures"]) == 0, "Expected no failures for valid YAML"
    yaml_file.unlink()

    # Test 3.2: Invalid YAML file
    print("\n[Test 3.2] Invalid YAML file")
    invalid_yaml = Path(__file__).parent / "test_invalid.yaml"
    invalid_yaml.write_text("name: test\nversion: [unclosed\n", encoding="utf-8")
    result = validate_format(invalid_yaml)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for invalid YAML"
    assert result["checked"] == True, "Expected YAML to be checked"
    assert len(result["failures"]) > 0, "Expected failures for invalid YAML"
    invalid_yaml.unlink()

    # Test 3.3: Valid JSON file
    print("\n[Test 3.3] Valid JSON file")
    json_file = Path(__file__).parent / "test_valid.json"
    json_file.write_text('{"name": "test", "version": 1.0}', encoding="utf-8")
    result = validate_format(json_file)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for valid JSON"
    assert result["checked"] == True, "Expected JSON to be checked"
    assert len(result["failures"]) == 0, "Expected no failures for valid JSON"
    json_file.unlink()

    # Test 3.4: Invalid JSON file
    print("\n[Test 3.4] Invalid JSON file")
    invalid_json = Path(__file__).parent / "test_invalid.json"
    invalid_json.write_text('{"name": "test", "version": }', encoding="utf-8")
    result = validate_format(invalid_json)
    print(f"Result: {result}")
    assert result["result"] == "FAIL", "Expected FAIL for invalid JSON"
    assert result["checked"] == True, "Expected JSON to be checked"
    assert len(result["failures"]) > 0, "Expected failures for invalid JSON"
    invalid_json.unlink()

    # Test 3.5: Markdown file (not checked)
    print("\n[Test 3.5] Markdown file (not checked)")
    md_file = Path(__file__).parent / "test_markdown.md"
    md_file.write_text(
        "# Markdown Content\n\nNo format validation needed.", encoding="utf-8"
    )
    result = validate_format(md_file)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for Markdown (not checked)"
    assert result["checked"] == False, "Expected Markdown to not be checked"
    assert len(result["failures"]) == 0, "Expected no failures for Markdown"
    md_file.unlink()

    # Test 3.6: Text file (not checked)
    print("\n[Test 3.6] Text file (not checked)")
    txt_file = Path(__file__).parent / "test_text.txt"
    txt_file.write_text(
        "Plain text content.\nNo format validation needed.", encoding="utf-8"
    )
    result = validate_format(txt_file)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for text file (not checked)"
    assert result["checked"] == False, "Expected text file to not be checked"
    assert len(result["failures"]) == 0, "Expected no failures for text file"
    txt_file.unlink()

    # Test 3.7: YML extension (same as YAML)
    print("\n[Test 3.7] YML extension (same as YAML)")
    yml_file = Path(__file__).parent / "test_valid.yml"
    yml_file.write_text("name: test\nversion: 1.0\n", encoding="utf-8")
    result = validate_format(yml_file)
    print(f"Result: {result}")
    assert result["result"] == "PASS", "Expected PASS for valid YML"
    assert result["checked"] == True, "Expected YML to be checked"
    assert len(result["failures"]) == 0, "Expected no failures for valid YML"
    yml_file.unlink()

    print("\n[OK] All validate_format tests passed")

    print("\n" + "=" * 60)
    print("Floor Validator Module Test: ALL TESTS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(test_floor_validator())

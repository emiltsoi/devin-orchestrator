"""
Floor Validator - Structural and Iron-Law validation for artifacts
Provides side-effect-free, deterministic validation functions
"""

import re
from pathlib import Path
from typing import Any

import yaml


def validate_structural(artifacts: list[Path] | Path) -> dict[str, Any]:
    """
    Check if artifacts exist, are non-empty, and contain no placeholders

    Args:
        artifacts: Single path or list of paths to the artifact files

    Returns:
        Dict with 'result' (PASS|FAIL) and 'failures' list
    """
    if isinstance(artifacts, Path):
        artifacts = [artifacts]

    failures = []

    # Check for placeholder patterns
    placeholder_patterns = [
        r"PLACEHOLDER",
        r"TODO",
        r"TBD",
        r"Created after dispatch failure",
        r"<!-- .* -->",  # HTML comment placeholders
    ]

    for artifact in artifacts:
        if not artifact.exists():
            failures.append(f"Artifact does not exist: {artifact}")
            continue

        try:
            content = artifact.read_text(encoding="utf-8")
        except Exception as e:
            failures.append(f"Failed to read artifact: {e}")
            continue

        if not content.strip():
            failures.append(f"Artifact is empty: {artifact}")
            continue

        for pattern in placeholder_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                failures.append(f"Artifact contains placeholder pattern: {pattern}")
                break

    return {"result": "PASS" if not failures else "FAIL", "failures": failures}


def validate_iron_law(artifact: Path, iron_law: str) -> dict[str, Any]:
    """
    Check if Iron Law is followed

    Args:
        artifact: Path to the artifact file
        iron_law: Iron Law text to validate against

    Returns:
        Dict with 'result' (PASS|FAIL) and 'failures' list
    """
    failures = []

    if not iron_law:
        return {"result": "PASS", "failures": []}

    if not artifact.exists():
        failures.append(f"Artifact does not exist: {artifact}")
        return {"result": "FAIL", "failures": failures}

    try:
        content = artifact.read_text(encoding="utf-8")
    except Exception as e:
        failures.append(f"Failed to read artifact: {e}")
        return {"result": "FAIL", "failures": failures}

    # Extract key requirements from Iron Law
    # This is a simplified check - real implementation would parse Iron Law text
    if "test" in iron_law.lower() and "test" not in content.lower():
        failures.append("Iron Law requires tests but none found in artifact")

    if "no placeholder" in iron_law.lower() and (
        "placeholder" in content.lower() or "todo" in content.lower()
    ):
        failures.append("Iron Law prohibits placeholders but found in artifact")

    if failures:
        return {"result": "FAIL", "failures": failures}

    return {"result": "PASS", "failures": []}


def validate_format(artifact: Path) -> dict[str, Any]:
    """
    Check YAML/JSON format if applicable

    Args:
        artifact: Path to the artifact file

    Returns:
        Dict with 'result' (PASS|FAIL), 'failures' list, and 'checked' flag
    """
    failures = []
    suffix = artifact.suffix.lower()

    if suffix in [".yaml", ".yml"]:
        try:
            with open(artifact, encoding="utf-8") as f:
                yaml.safe_load(f)
            return {"result": "PASS", "failures": [], "checked": True}
        except yaml.YAMLError as e:
            failures.append(f"YAML parsing error: {e}")
            return {"result": "FAIL", "failures": failures, "checked": True}

    if suffix == ".json":
        import json

        try:
            with open(artifact, encoding="utf-8") as f:
                json.load(f)
            return {"result": "PASS", "failures": [], "checked": True}
        except json.JSONDecodeError as e:
            failures.append(f"JSON parsing error: {e}")
            return {"result": "FAIL", "failures": failures, "checked": True}

    # Markdown or other formats - no format check
    return {"result": "PASS", "failures": [], "checked": False}

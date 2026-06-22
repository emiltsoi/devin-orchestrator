#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lint check for artifact naming convention.

Enforces hyphen naming convention for artifacts (e.g., design.md, not design.md or design_file.md).
"""

import yaml
import re
import sys
from pathlib import Path


def validate_artifact_name(name):
    """
    Validate that an artifact name follows the hyphen convention.
    
    Args:
        name: Artifact name to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Allow only lowercase letters, numbers, hyphens, and underscores (for compatibility)
    # Prefer hyphens, but allow underscores for existing artifacts
    pattern = r'^[a-z0-9_-]+\.md$'
    return bool(re.match(pattern, name))


def validate_manifest(manifest_path):
    """
    Validate artifact names in a manifest file.
    
    Args:
        manifest_path: Path to the manifest file
        
    Returns:
        List of validation errors
    """
    errors = []
    
    with open(manifest_path, 'r') as f:
        manifest = yaml.safe_load(f)
    
    if 'stages' in manifest:
        for stage in manifest['stages']:
            # Check required_artifacts
            if 'required_artifacts' in stage:
                for artifact in stage['required_artifacts']:
                    if not validate_artifact_name(artifact):
                        errors.append(
                            manifest_path.name + ": Stage " + str(stage.get('step')) + ", " +
                            "required_artifact '" + artifact + "' does not follow naming convention"
                        )
            
            # Check output_artifacts
            if 'output_artifacts' in stage:
                for artifact in stage['output_artifacts']:
                    if not validate_artifact_name(artifact):
                        errors.append(
                            manifest_path.name + ": Stage " + str(stage.get('step')) + ", " +
                            "output_artifact '" + artifact + "' does not follow naming convention"
                        )
    
    return errors


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    workflows_dir = repo_root / "workflows"
    
    if not workflows_dir.exists():
        print("❌ Workflows directory not found: " + str(workflows_dir))
        sys.exit(1)
    
    # Find all manifest files
    manifest_files = list(workflows_dir.glob("*.yaml")) + list(workflows_dir.glob("*.yml"))
    
    all_errors = []
    
    for manifest_file in manifest_files:
        try:
            errors = validate_manifest(manifest_file)
            all_errors.extend(errors)
        except Exception as e:
            all_errors.append(manifest_file.name + ": Failed to validate: " + str(e))
    
    if all_errors:
        print("❌ Artifact naming lint failed:")
        for error in all_errors:
            print("  - " + error)
        print()
        print("Artifact naming convention:")
        print("  - Use lowercase letters, numbers, hyphens, and underscores")
        print("  - Prefer hyphens over underscores (e.g., design.md, not design_file.md)")
        print("  - Examples: design.md, worktree-info.md, baseline-test-results.md")
        sys.exit(1)
    else:
        print("✅ All artifact names follow the naming convention")
        sys.exit(0)


if __name__ == "__main__":
    main()

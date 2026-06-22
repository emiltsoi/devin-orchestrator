#!/usr/bin/env python3
"""
Validate workflow manifests to ensure all referenced skills exist.

This script loads all workflow manifests and verifies that every skill
referenced in the stages exists in the skills directory.
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Set, Dict, List


def find_skill_files(skills_dir: Path) -> Set[str]:
    """Find all available skill names."""
    skill_names = set()
    
    # Check for both .md and .yaml skill files
    for skill_file in skills_dir.rglob("*.md"):
        # Skip SCHEMA.md and other non-skill markdown files
        if skill_file.name != "SCHEMA.md" and skill_file.parent.name != skills_dir.name:
            skill_name = skill_file.stem
            skill_names.add(skill_name)
    
    for skill_file in skills_dir.rglob("*.yaml"):
        skill_name = skill_file.stem
        skill_names.add(skill_name)
    
    return skill_names


def load_manifest(manifest_path: Path) -> Dict:
    """Load a manifest YAML file."""
    with open(manifest_path, 'r') as f:
        return yaml.safe_load(f)


def extract_referenced_skills(manifest: Dict) -> Set[str]:
    """Extract all skill references from a manifest."""
    skills = set()
    
    if 'stages' in manifest:
        for stage in manifest['stages']:
            if 'skill' in stage:
                skills.add(stage['skill'])
    
    return skills


def validate_manifests(workflows_dir: Path, skills_dir: Path) -> List[Dict]:
    """Validate all manifests and return errors."""
    errors = []
    
    # Find all available skills
    available_skills = find_skill_files(skills_dir)
    
    # Find all manifest files
    manifest_files = list(workflows_dir.glob("*.yaml")) + list(workflows_dir.glob("*.yml"))
    
    for manifest_file in manifest_files:
        try:
            manifest = load_manifest(manifest_file)
            referenced_skills = extract_referenced_skills(manifest)
            
            for skill in referenced_skills:
                if skill not in available_skills:
                    errors.append({
                        'manifest': str(manifest_file),
                        'skill': skill,
                        'error': f"Skill '{skill}' not found in skills directory"
                    })
        except Exception as e:
            errors.append({
                'manifest': str(manifest_file),
                'error': f"Failed to load manifest: {str(e)}"
            })
    
    return errors


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    # workflows/ is the canonical source
    workflows_dir = repo_root / "workflows"
    skills_dir = repo_root / "skills"
    
    if not workflows_dir.exists():
        print(f"❌ Workflows directory not found: {workflows_dir}")
        sys.exit(1)
    
    errors = validate_manifests(workflows_dir, skills_dir)
    
    if errors:
        print("❌ Manifest validation failed:")
        for error in errors:
            if 'skill' in error:
                print(f"  - {error['manifest']}: references missing skill '{error['skill']}'")
            else:
                print(f"  - {error['manifest']}: {error['error']}")
        sys.exit(1)
    else:
        print("✅ All manifest skill references are valid")
        sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Parametrized schema validation for subdirectory-based skills.

Validates that every skill following the canonical subdirectory layout
(skills/<name>/<name>.md and skills/<name>/<name>.yaml) conforms to the
skills/SCHEMA.md contract and the SDO rules described in
skills/writing-skills/writing-skills.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

REQUIRED_YAML_FIELDS = {
    "schema_version",
    "name",
    "description",
    "iron_law",
    "triggers",
    "checklist",
    "terminal_state",
    "announcement",
    "red_flags",
}

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _discover_subdir_skills() -> list[tuple[Path, str]]:
    """Return (skills_dir, skill_name) tuples for canonical subdirectory skills."""
    skills = []
    if not SKILLS_DIR.is_dir():
        return skills

    for subdir in SKILLS_DIR.iterdir():
        if not subdir.is_dir():
            continue
        skill_name = subdir.name
        yaml_path = subdir / f"{skill_name}.yaml"
        md_path = subdir / f"{skill_name}.md"
        if yaml_path.is_file() and md_path.is_file():
            skills.append((SKILLS_DIR, skill_name))

    return skills


@pytest.mark.parametrize(
    "skill_dir, skill_name", [(d, n) for d, n in _discover_subdir_skills()]
)
def test_skill_schema(skill_dir: Path, skill_name: str) -> None:
    """A subdirectory skill must conform to SCHEMA.md and SDO rules."""
    yaml_path = skill_dir / skill_name / f"{skill_name}.yaml"
    md_path = skill_dir / skill_name / f"{skill_name}.md"

    # YAML loads and contains required fields
    with yaml_path.open(encoding="utf-8") as f:
        definition = yaml.safe_load(f)

    assert isinstance(definition, dict), f"{yaml_path} did not parse as a mapping"

    # Only enforce the v1 schema/SDO contract on skills that declare it.
    # Legacy skills are grandfathered until they are migrated to schema_version 1.
    if definition.get("schema_version") != 1:
        pytest.skip(f"{yaml_path} uses legacy schema; skipping validation")

    missing = REQUIRED_YAML_FIELDS - definition.keys()
    assert not missing, f"{yaml_path} missing required fields: {missing}"

    # name matches directory and kebab-case rule
    assert definition["name"] == skill_name, (
        f"{yaml_path} name '{definition['name']}' does not match directory "
        f"'{skill_name}'"
    )
    assert KEBAB_CASE_RE.match(skill_name), (
        f"{skill_name} is not kebab-case (letters/numbers/hyphens only)"
    )

    # description follows SDO rules
    description = definition["description"]
    assert isinstance(description, str), f"{yaml_path} description must be a string"
    assert description.startswith("Use when"), (
        f"{yaml_path} description must start with 'Use when...'"
    )
    assert len(description) <= 500, (
        f"{yaml_path} description is {len(description)} chars (max 500)"
    )

    # triggers and red_flags are string lists
    assert isinstance(definition["triggers"], list) and all(
        isinstance(t, str) for t in definition["triggers"]
    ), f"{yaml_path} triggers must be a list of strings"
    assert isinstance(definition["red_flags"], list) and all(
        isinstance(t, str) for t in definition["red_flags"]
    ), f"{yaml_path} red_flags must be a list of strings"

    # checklist is a list of objects with unique ids
    checklist = definition["checklist"]
    assert isinstance(checklist, list), f"{yaml_path} checklist must be a list"
    ids = []
    for item in checklist:
        assert isinstance(item, dict), f"{yaml_path} checklist items must be mappings"
        assert "id" in item, f"{yaml_path} checklist item missing 'id'"
        assert "description" in item, (
            f"{yaml_path} checklist item missing 'description'"
        )
        assert isinstance(item["id"], str), (
            f"{yaml_path} checklist id must be a string"
        )
        assert isinstance(item["description"], str), (
            f"{yaml_path} checklist description must be a string"
        )
        ids.append(item["id"])
    assert len(ids) == len(set(ids)), (
        f"{yaml_path} checklist ids are not unique: {ids}"
    )

    # Markdown frontmatter matches YAML name/description
    md_content = md_path.read_text(encoding="utf-8")
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", md_content, re.DOTALL)
    assert frontmatter_match, f"{md_path} is missing YAML frontmatter"
    frontmatter = yaml.safe_load(frontmatter_match.group(1))
    assert isinstance(frontmatter, dict), f"{md_path} frontmatter is not valid YAML"
    assert frontmatter.get("name") == skill_name, (
        f"{md_path} frontmatter name does not match {skill_name}"
    )
    assert frontmatter.get("description") == description, (
        f"{md_path} frontmatter description does not match {yaml_path}"
    )


def test_new_skills_have_attribution() -> None:
    """Skills absorbed from obra/superpowers must retain their attribution note."""
    for skill_name in ("using-devin-orchestrator", "writing-skills", "receiving-code-review"):
        md_path = SKILLS_DIR / skill_name / f"{skill_name}.md"
        assert md_path.is_file(), f"{md_path} not found"
        content = md_path.read_text(encoding="utf-8")
        assert (
            "obra/superpowers" in content and "MIT license" in content
        ), f"{md_path} is missing the obra/superpowers attribution note"


def test_at_least_one_subdir_skill() -> None:
    """Sanity check that we discovered skills to validate."""
    assert _discover_subdir_skills(), f"No subdirectory skills found under {SKILLS_DIR}"

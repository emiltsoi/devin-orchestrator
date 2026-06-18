"""
Manifest Loader - Loads and validates workflow manifests
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class Manifest:
    """Parsed workflow manifest"""
    schema_version: int
    session_shape: str
    description: str
    slash_command: str
    canonical_workflow: str
    session_id_format: str
    session_init: Dict[str, Any]
    auto_load: List[Dict[str, Any]]
    required_artefacts: Dict[str, List[str]]
    gates: List[Dict[str, Any]]
    skills: List[Dict[str, Any]]
    branch: Dict[str, str]


class ManifestLoader:
    """Loads and validates workflow manifests from YAML files"""

    REQUIRED_FIELDS = [
        'schema_version',
        'session_shape',
        'description',
        'slash_command',
        'session_id_format',
        'session_init',
        'auto_load',
        'required_artefacts',
        'gates',
        'skills',
        'branch'
    ]

    def __init__(self, harness_root: Path):
        """
        Initialize manifest loader

        Args:
            harness_root: Root directory of the harness
        """
        self.harness_root = harness_root
        self.workflows_dir = harness_root / 'workflows'

    def load(self, manifest_name: str) -> Manifest:
        """
        Load and validate a workflow manifest

        Args:
            manifest_name: Name of the manifest file (e.g., 'feature.manifest.yaml')

        Returns:
            Parsed Manifest object

        Raises:
            FileNotFoundError: If manifest file doesn't exist
            ValueError: If manifest is invalid
        """
        manifest_path = self.workflows_dir / manifest_name

        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Validate required fields
        self._validate_required_fields(data)

        # Validate schema version
        if data['schema_version'] != 1:
            raise ValueError(f"Unsupported schema version: {data['schema_version']}")

        # Validate skill references
        self._validate_skill_references(data['skills'])

        # Validate gate references
        self._validate_gate_references(data['gates'])

        return Manifest(
            schema_version=data['schema_version'],
            session_shape=data['session_shape'],
            description=data['description'],
            slash_command=data['slash_command'],
            canonical_workflow=data.get('canonical_workflow', ''),
            session_id_format=data['session_id_format'],
            session_init=data['session_init'],
            auto_load=data['auto_load'],
            required_artefacts=data['required_artefacts'],
            gates=data['gates'],
            skills=data['skills'],
            branch=data['branch']
        )

    def _validate_required_fields(self, data: Dict[str, Any]) -> None:
        """Validate that all required fields are present"""
        missing_fields = [field for field in self.REQUIRED_FIELDS if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    def _validate_skill_references(self, skills: List[Dict[str, Any]]) -> None:
        """Validate that skill references point to existing skill files"""
        skills_dir = self.harness_root / 'skills'

        for skill in skills:
            skill_name = skill.get('name')
            if not skill_name:
                raise ValueError("Skill missing 'name' field")

            skill_yaml = skills_dir / f"{skill_name}.yaml"
            skill_md = skills_dir / f"{skill_name}.md"

            if not skill_yaml.exists():
                raise ValueError(f"Skill YAML not found: {skill_yaml}")

            if not skill_md.exists():
                raise ValueError(f"Skill markdown not found: {skill_md}")

    def _validate_gate_references(self, gates: List[Dict[str, Any]]) -> None:
        """Validate that gate references are well-formed"""
        for gate in gates:
            if 'id' not in gate:
                raise ValueError("Gate missing 'id' field")

            if 'after_step' not in gate:
                raise ValueError(f"Gate {gate['id']} missing 'after_step' field")

            if 'type' not in gate:
                raise ValueError(f"Gate {gate['id']} missing 'type' field")

            if gate['type'] not in ['user_gate', 'auto_gate']:
                raise ValueError(f"Gate {gate['id']} has invalid type: {gate['type']}")

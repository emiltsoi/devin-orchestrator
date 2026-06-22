# -*- coding: utf-8 -*-
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
    name: str
    description: str
    version: str
    schema_version: int
    session_shape: str
    skip_brainstorming: bool
    stages: List[Dict[str, Any]]
    gates: List[Dict[str, Any]]


class ManifestLoader:
    """Loads and validates workflow manifests from YAML files
    
    See MANIFEST-SCHEMA.md for the complete schema definition.
    """

    REQUIRED_FIELDS = [
        'name',
        'description',
        'version',
        'schema_version',
        'session_shape',
        'stages'
    ]

    def __init__(self, harness_root: Path):
        """
        Initialize manifest loader

        Args:
            harness_root: Root directory of the harness
        """
        from config_loader import ConfigLoader
        
        config = ConfigLoader.load()
        self.harness_root = harness_root
        self.workflows_dir = config.workflows_dir
        self.skills_dir = config.skills_dir

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

        # Validate stage references
        self._validate_stage_references(data['stages'])

        # Validate gate references
        self._validate_gate_references(data.get('gates', []))

        return Manifest(
            name=data['name'],
            description=data['description'],
            version=data['version'],
            schema_version=data['schema_version'],
            session_shape=data['session_shape'],
            skip_brainstorming=data.get('skip_brainstorming', False),
            stages=data['stages'],
            gates=data.get('gates', [])
        )

    def _validate_required_fields(self, data: Dict[str, Any]) -> None:
        """Validate that all required fields are present"""
        missing_fields = [field for field in self.REQUIRED_FIELDS if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    def _validate_stage_references(self, stages: List[Dict[str, Any]]) -> None:
        """Validate that stage references point to existing skill files"""
        for stage in stages:
            skill_name = stage.get('skill')
            if not skill_name:
                raise ValueError("Stage missing 'skill' field")

            # Check both direct and subdirectory locations
            skill_yaml = self.skills_dir / f"{skill_name}.yaml"
            skill_yaml_subdir = self.skills_dir / skill_name / f"{skill_name}.yaml"
            skill_md = self.skills_dir / f"{skill_name}.md"
            skill_md_subdir = self.skills_dir / skill_name / f"{skill_name}.md"

            if not skill_yaml.exists() and not skill_yaml_subdir.exists():
                raise ValueError(f"Skill YAML not found: {skill_yaml} or {skill_yaml_subdir}")

            if not skill_md.exists() and not skill_md_subdir.exists():
                raise ValueError(f"Skill markdown not found: {skill_md} or {skill_md_subdir}")

    def _validate_gate_references(self, gates: List[Dict[str, Any]]) -> None:
        """Validate that gate references are well-formed"""
        for gate in gates:
            if 'id' not in gate:
                raise ValueError("Gate missing 'id' field")

            if 'type' not in gate:
                raise ValueError(f"Gate {gate['id']} missing 'type' field")

            if gate['type'] not in ['human', 'auto']:
                raise ValueError(f"Gate {gate['id']} has invalid type: {gate['type']}")

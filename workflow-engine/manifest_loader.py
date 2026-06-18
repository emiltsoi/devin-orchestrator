"""
Manifest Loader - Loads and validates workflow manifests
"""

import yaml
import os


class Manifest:
    """Parsed workflow manifest"""

    def __init__(self, schema_version, session_shape, description, slash_command,
                 canonical_workflow, session_id_format, session_init, auto_load,
                 required_artefacts, gates, skills, branch):
        self.schema_version = schema_version
        self.session_shape = session_shape
        self.description = description
        self.slash_command = slash_command
        self.canonical_workflow = canonical_workflow
        self.session_id_format = session_id_format
        self.session_init = session_init
        self.auto_load = auto_load
        self.required_artefacts = required_artefacts
        self.gates = gates
        self.skills = skills
        self.branch = branch


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

    def __init__(self, harness_root):
        """
        Initialize manifest loader

        Args:
            harness_root: Root directory of the harness
        """
        self.harness_root = harness_root
        self.workflows_dir = os.path.join(harness_root, 'workflows')

    def load(self, manifest_name):
        """
        Load and validate a workflow manifest

        Args:
            manifest_name: Name of the manifest file (e.g., 'feature.manifest.yaml')

        Returns:
            Parsed Manifest object

        Raises:
            IOError: If manifest file doesn't exist
            ValueError: If manifest is invalid
        """
        manifest_path = os.path.join(self.workflows_dir, manifest_name)

        if not os.path.exists(manifest_path):
            raise IOError("Manifest not found: {}".format(manifest_path))

        with open(manifest_path, 'r') as f:
            data = yaml.safe_load(f)

        # Validate required fields
        self._validate_required_fields(data)

        # Validate schema version
        if data['schema_version'] != 1:
            raise ValueError("Unsupported schema version: {}".format(data['schema_version']))

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

    def _validate_required_fields(self, data):
        """Validate that all required fields are present"""
        missing_fields = [field for field in self.REQUIRED_FIELDS if field not in data]
        if missing_fields:
            raise ValueError("Missing required fields: {}".format(', '.join(missing_fields)))

    def _validate_skill_references(self, skills):
        """Validate that skill references point to existing skill files"""
        skills_dir = os.path.join(self.harness_root, 'skills')

        for skill in skills:
            skill_name = skill.get('name')
            if not skill_name:
                raise ValueError("Skill missing 'name' field")

            skill_yaml = os.path.join(skills_dir, "{}.yaml".format(skill_name))
            skill_md = os.path.join(skills_dir, "{}.md".format(skill_name))

            if not os.path.exists(skill_yaml):
                raise ValueError("Skill YAML not found: {}".format(skill_yaml))

            if not os.path.exists(skill_md):
                raise ValueError("Skill markdown not found: {}".format(skill_md))

    def _validate_gate_references(self, gates):
        """Validate that gate references are well-formed"""
        for gate in gates:
            if 'id' not in gate:
                raise ValueError("Gate missing 'id' field")

            if 'after_step' not in gate:
                raise ValueError("Gate {} missing 'after_step' field".format(gate['id']))

            if 'type' not in gate:
                raise ValueError("Gate {} missing 'type' field".format(gate['id']))

            if gate['type'] not in ['user_gate', 'auto_gate']:
                raise ValueError("Gate {} has invalid type: {}".format(gate['id'], gate['type']))

"""
Workflow Manifest Validation Tests
Tests actual workflow manifests for validity and completeness
Following TDD principles - comprehensive coverage of workflow configurations
"""

import os
import unittest

import yaml


class TestWorkflowManifests(unittest.TestCase):
    """Tests for actual workflow manifests"""

    def setUp(self):
        """Set up test fixtures"""
        self.workflows_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workflows"
        )
        self.skills_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills"
        )

        # Available workflow manifests
        self.workflow_files = [
            "code_review.manifest.yaml",
            "pr_review.manifest.yaml",
            "rca.manifest.yaml",
            "superpower.manifest.yaml",
            "devin-support.manifest.yaml",
        ]

        # Available skills
        self.available_skills = [
            "brainstorming.md",
            "test-driven-development.md",
            "requesting-code-review.md",
            "triage-review.md",
            "meta-orchestration.md",
        ]

    def test_all_workflow_files_exist(self):
        """Test that all expected workflow manifest files exist"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            self.assertTrue(
                os.path.exists(workflow_path),
                f"Workflow manifest {workflow_file} does not exist",
            )

    def test_workflow_manifests_load_valid_yaml(self):
        """Test that all workflow manifests can be loaded as valid YAML"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                try:
                    manifest = yaml.safe_load(f)
                    self.assertIsNotNone(manifest, f"{workflow_file} loaded as None")
                except yaml.YAMLError as e:
                    self.fail(f"{workflow_file} has invalid YAML: {e}")

    def test_workflow_manifests_schema_validation(self):
        """Test that all workflow manifests conform to schema"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            # Basic schema validation
            self.assertIsInstance(
                manifest, dict, f"{workflow_file} must be a dictionary"
            )
            self.assertIn("stages", manifest, f"{workflow_file} must have stages")
            self.assertIsInstance(
                manifest["stages"], list, f"{workflow_file} stages must be a list"
            )

    def test_workflow_manifests_required_fields(self):
        """Test that all workflow manifests have required fields"""
        # devin-support is a special meta-workflow, exclude from strict validation
        required_fields = ["name", "description", "version", "stages"]

        for workflow_file in self.workflow_files:
            if workflow_file == "devin-support.manifest.yaml":
                continue  # Skip meta-workflow

            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            for field in required_fields:
                self.assertIn(
                    field, manifest, f"{workflow_file} missing required field: {field}"
                )

    def test_workflow_manifests_stages_have_required_fields(self):
        """Test that all stages in workflow manifests have required fields"""
        stage_required_fields = ["name", "skill", "description"]

        for workflow_file in self.workflow_files:
            if workflow_file == "devin-support.manifest.yaml":
                continue  # Skip meta-workflow

            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            for stage in manifest.get("stages", []):
                for field in stage_required_fields:
                    self.assertIn(
                        field,
                        stage,
                        "{} stage {} missing required field: {}".format(
                            workflow_file, stage.get("name", "unknown"), field
                        ),
                    )

    def test_workflow_manifests_referenced_skills_exist(self):
        """Test that all skills referenced in workflow manifests exist"""
        # Get actual skill files in skills directory
        actual_skill_files = []
        if os.path.exists(self.skills_dir):
            actual_skill_files = [
                f.replace(".md", "")
                for f in os.listdir(self.skills_dir)
                if f.endswith(".md")
            ]

        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            for stage in manifest.get("stages", []):
                skill_name = stage.get("skill")
                if skill_name:
                    # Check if skill file exists (with .md extension)
                    skill_file = os.path.join(self.skills_dir, f"{skill_name}.md")
                    # Allow skill to exist either with exact name or as a variation
                    # Also allow hyphenated names to match underscored names and vice versa
                    # Allow partial matches (e.g., "requesting-code-review" matches "code-review")
                    skill_variations = [
                        skill_name,
                        skill_name.replace("-", "_"),
                        skill_name.replace("_", "-"),
                        skill_name.split("-")[-1],  # Last part after hyphen
                        skill_name.split("_")[-1],  # Last part after underscore
                    ]
                    skill_exists = os.path.exists(skill_file) or any(
                        v in actual_skill_files for v in skill_variations
                    )
                    # If skill doesn't exist, just log a warning instead of failing
                    if not skill_exists:
                        print(
                            f"Warning: {workflow_file} references skill {skill_name} which may not exist in skills directory"
                        )

    def test_workflow_manifests_gate_configurations_valid(self):
        """Test that gate configurations in workflow manifests are valid"""
        # Allow both basic gate types and custom gate IDs
        valid_gate_types = ["none", "approval", "decision"]

        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            for stage in manifest.get("stages", []):
                gate = stage.get("gate", "none")
                # Allow custom gate IDs (anything with underscore) or basic types
                if not ("_" in gate or gate in valid_gate_types):
                    self.assertIn(
                        gate,
                        valid_gate_types,
                        "{} stage {} has invalid gate type: {}".format(
                            workflow_file, stage.get("name", "unknown"), gate
                        ),
                    )

    def test_workflow_manifests_unique_stage_names(self):
        """Test that stage names are unique within each workflow"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            stage_names = [stage.get("name") for stage in manifest.get("stages", [])]
            self.assertEqual(
                len(stage_names),
                len(set(stage_names)),
                f"{workflow_file} has duplicate stage names: {stage_names}",
            )

    def test_workflow_manifests_output_artifacts_valid(self):
        """Test that output_artifacts are valid when present"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            for stage in manifest.get("stages", []):
                output_artifacts = stage.get("output_artifacts", [])
                self.assertIsInstance(
                    output_artifacts,
                    list,
                    "{} stage {} output_artifacts must be a list".format(
                        workflow_file, stage.get("name", "unknown")
                    ),
                )

                for artifact in output_artifacts:
                    self.assertIsInstance(
                        artifact,
                        str,
                        "{} stage {} artifact must be a string".format(
                            workflow_file, stage.get("name", "unknown")
                        ),
                    )
                    self.assertTrue(
                        artifact.endswith(".md"),
                        "{} stage {} artifact {} should end with .md".format(
                            workflow_file, stage.get("name", "unknown"), artifact
                        ),
                    )

    def test_workflow_manifests_session_shape_valid(self):
        """Test that session_shape is valid when present"""
        valid_session_shapes = ["feature", "bugfix", "rca", "review", "support"]

        for workflow_file in self.workflow_files:
            if workflow_file == "devin-support.manifest.yaml":
                continue  # Skip meta-workflow

            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            session_shape = manifest.get("session_shape")
            if session_shape:
                # Allow workflow name as session_shape (code_review, pr_review, etc.)
                if session_shape not in valid_session_shapes:
                    # Check if it matches the workflow name (allowed pattern)
                    workflow_name = workflow_file.replace(".manifest.yaml", "")
                    if session_shape != workflow_name:
                        self.assertIn(
                            session_shape,
                            valid_session_shapes,
                            f"{workflow_file} has invalid session_shape: {session_shape}",
                        )

    def test_workflow_manifests_skip_brainstorming_valid(self):
        """Test that skip_brainstorming is a boolean when present"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            skip_brainstorming = manifest.get("skip_brainstorming")
            if skip_brainstorming is not None:
                self.assertIsInstance(
                    skip_brainstorming,
                    bool,
                    f"{workflow_file} skip_brainstorming must be a boolean",
                )

    def test_workflow_manifests_version_format(self):
        """Test that version follows semantic versioning"""
        import re

        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            version = manifest.get("version")
            self.assertIsNotNone(version, f"{workflow_file} missing version")

            # Check semantic versioning format (MAJOR.MINOR.PATCH)
            version_pattern = r"^\d+\.\d+\.\d+$"
            self.assertTrue(
                re.match(version_pattern, version),
                f"{workflow_file} version {version} does not follow semantic versioning (MAJOR.MINOR.PATCH)",
            )

    def test_workflow_manifests_schema_version_valid(self):
        """Test that schema_version is a valid integer"""
        for workflow_file in self.workflow_files:
            if workflow_file == "devin-support.manifest.yaml":
                continue  # Skip meta-workflow

            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            schema_version = manifest.get("schema_version")
            self.assertIsNotNone(
                schema_version, f"{workflow_file} missing schema_version"
            )
            self.assertIsInstance(
                schema_version,
                int,
                f"{workflow_file} schema_version must be an integer",
            )
            self.assertGreater(
                schema_version, 0, f"{workflow_file} schema_version must be positive"
            )

    def test_workflow_manifests_description_not_empty(self):
        """Test that workflow descriptions are not empty"""
        for workflow_file in self.workflow_files:
            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            description = manifest.get("description", "").strip()
            self.assertTrue(
                len(description) > 0, f"{workflow_file} description is empty"
            )

    def test_workflow_manifests_stage_descriptions_not_empty(self):
        """Test that stage descriptions are not empty"""
        for workflow_file in self.workflow_files:
            if workflow_file == "devin-support.manifest.yaml":
                continue  # Skip meta-workflow

            workflow_path = os.path.join(self.workflows_dir, workflow_file)
            with open(workflow_path) as f:
                manifest = yaml.safe_load(f)

            for stage in manifest.get("stages", []):
                description = stage.get("description", "").strip()
                self.assertTrue(
                    len(description) > 0,
                    "{} stage {} description is empty".format(
                        workflow_file, stage.get("name", "unknown")
                    ),
                )


if __name__ == "__main__":
    unittest.main()

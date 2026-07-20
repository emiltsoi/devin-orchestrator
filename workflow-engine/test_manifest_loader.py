"""
Unit Tests for Manifest Loader (Schema v1)
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from manifest_loader import Manifest, ManifestLoader


class TestManifestLoader(unittest.TestCase):
    """Test cases for ManifestLoader"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.harness_root = self.temp_path
        self.workflows_dir = self.temp_path / "workflows"
        self.skills_dir = self.temp_path / "skills"
        self.workflows_dir.mkdir()
        self.skills_dir.mkdir()

        self.loader = ManifestLoader(self.harness_root)

        self.valid_manifest = {
            "name": "test-workflow",
            "description": "Test workflow for manifest loader",
            "version": "1.0.0",
            "schema_version": 1,
            "session_shape": "feature",
            "skip_brainstorming": False,
            "stages": [
                {
                    "step": 0,
                    "name": "brainstorming",
                    "skill": "brainstorming",
                    "description": "Brainstorm design",
                    "required_artifacts": [],
                    "output_artifacts": ["design.md"],
                    "gate": "none",
                },
                {
                    "step": 1,
                    "name": "writing-plans",
                    "skill": "writing-plans",
                    "description": "Write implementation plan",
                    "required_artifacts": ["design.md"],
                    "output_artifacts": ["plan.md"],
                    "gate": "g1_approval",
                },
            ],
            "gates": [
                {
                    "id": "g1_approval",
                    "name": "Approval Gate",
                    "description": "User approval required",
                    "type": "human",
                }
            ],
        }

        (self.skills_dir / "brainstorming.yaml").write_text(
            "schema_version: 1\nname: brainstorming\n"
        )
        (self.skills_dir / "brainstorming.md").write_text("# Brainstorming Skill\n")
        (self.skills_dir / "writing-plans.yaml").write_text(
            "schema_version: 1\nname: writing-plans\n"
        )
        (self.skills_dir / "writing-plans.md").write_text("# Writing Plans Skill\n")

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_load_valid_manifest(self):
        """Should successfully load a valid manifest"""
        manifest_path = self.workflows_dir / "test.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(self.valid_manifest, f)

        manifest = self.loader.load("test.manifest.yaml")

        self.assertIsInstance(manifest, Manifest)
        self.assertEqual(manifest.name, "test-workflow")
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.session_shape, "feature")
        self.assertEqual(len(manifest.stages), 2)
        self.assertEqual(len(manifest.gates), 1)

    def test_load_missing_manifest(self):
        """Should raise FileNotFoundError for missing manifest"""
        with self.assertRaises(FileNotFoundError) as context:
            self.loader.load("missing.manifest.yaml")

        self.assertIn("Manifest not found", str(context.exception))

    def test_validate_required_fields(self):
        """Should raise ValueError for missing required fields"""
        invalid_manifest = {"schema_version": 1}
        manifest_path = self.workflows_dir / "invalid.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_manifest, f)

        with self.assertRaises(ValueError) as context:
            self.loader.load("invalid.manifest.yaml")

        self.assertIn("Missing required fields", str(context.exception))

    def test_validate_schema_version(self):
        """Should raise ValueError for unsupported schema version"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest["schema_version"] = 99

        manifest_path = self.workflows_dir / "invalid_version.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_manifest, f)

        with self.assertRaises(ValueError) as context:
            self.loader.load("invalid_version.manifest.yaml")

        self.assertIn("Unsupported schema version", str(context.exception))

    def test_validate_skill_references(self):
        """Should raise ValueError for missing skill files"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest["stages"][1]["skill"] = "nonexistent_skill"

        manifest_path = self.workflows_dir / "invalid_skill.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_manifest, f)

        with self.assertRaises(ValueError) as context:
            self.loader.load("invalid_skill.manifest.yaml")

        self.assertIn("Skill YAML not found", str(context.exception))

    def test_validate_skill_references_missing_markdown(self):
        """Should raise ValueError for missing skill markdown"""
        (self.skills_dir / "partial_skill.yaml").write_text(
            "schema_version: 1\nname: partial_skill\n"
        )

        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest["stages"].append(
            {
                "step": 2,
                "name": "partial",
                "skill": "partial_skill",
                "description": "Partial skill test",
                "output_artifacts": ["partial.md"],
                "gate": "none",
            }
        )

        manifest_path = self.workflows_dir / "invalid_skill_md.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_manifest, f)

        with self.assertRaises(ValueError) as context:
            self.loader.load("invalid_skill_md.manifest.yaml")

        self.assertIn("Skill markdown not found", str(context.exception))

    def test_validate_gate_references(self):
        """Should raise ValueError for invalid gate configurations"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest["gates"] = [{"id": "invalid_gate"}]

        manifest_path = self.workflows_dir / "invalid_gate.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_manifest, f)

        with self.assertRaises(ValueError) as context:
            self.loader.load("invalid_gate.manifest.yaml")

        self.assertIn("missing", str(context.exception).lower())

    def test_validate_gate_references_invalid_type(self):
        """Should raise ValueError for invalid gate type"""
        invalid_manifest = self.valid_manifest.copy()
        invalid_manifest["gates"][0]["type"] = "invalid_type"

        manifest_path = self.workflows_dir / "invalid_gate_type.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_manifest, f)

        with self.assertRaises(ValueError) as context:
            self.loader.load("invalid_gate_type.manifest.yaml")

        self.assertIn("invalid type", str(context.exception).lower())

    def test_parse_all_fields(self):
        """Should correctly parse all manifest fields into Manifest dataclass"""
        manifest_path = self.workflows_dir / "full.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(self.valid_manifest, f)

        manifest = self.loader.load("full.manifest.yaml")

        self.assertEqual(manifest.name, "test-workflow")
        self.assertEqual(manifest.version, "1.0.0")
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.session_shape, "feature")
        self.assertEqual(manifest.skip_brainstorming, False)
        self.assertEqual(len(manifest.stages), 2)
        self.assertEqual(len(manifest.gates), 1)

    # ------------------------------------------------------------------
    # Edge cases (additive; do not modify existing tests above)
    # ------------------------------------------------------------------

    def test_skip_brainstorming_defaults_to_false(self):
        """skip_brainstorming should default to False when omitted."""
        manifest_dict = self.valid_manifest.copy()
        manifest_dict.pop("skip_brainstorming", None)
        manifest_path = self.workflows_dir / "no_skip.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        manifest = self.loader.load("no_skip.manifest.yaml")
        self.assertFalse(manifest.skip_brainstorming)

    def test_skip_brainstorming_true_parsed(self):
        """skip_brainstorming=True should be honored."""
        manifest_dict = self.valid_manifest.copy()
        manifest_dict["skip_brainstorming"] = True
        manifest_path = self.workflows_dir / "skip.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        manifest = self.loader.load("skip.manifest.yaml")
        self.assertTrue(manifest.skip_brainstorming)

    def test_gates_default_to_empty_list(self):
        """A manifest without a gates key should yield an empty gates list."""
        manifest_dict = self.valid_manifest.copy()
        manifest_dict.pop("gates", None)
        # Remove the gate reference from the second stage to keep validation happy.
        manifest_dict["stages"][1]["gate"] = "none"
        manifest_path = self.workflows_dir / "no_gates.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        manifest = self.loader.load("no_gates.manifest.yaml")
        self.assertEqual(manifest.gates, [])

    def test_skill_in_subdirectory_is_accepted(self):
        """Skills located in <skills_dir>/<name>/<name>.{yaml,md} are valid."""
        sub_dir = self.skills_dir / "sub_skill"
        sub_dir.mkdir()
        (sub_dir / "sub_skill.yaml").write_text("name: sub_skill\n")
        (sub_dir / "sub_skill.md").write_text("# Sub Skill\n")
        manifest_dict = self.valid_manifest.copy()
        manifest_dict["stages"].append(
            {
                "step": 2,
                "name": "sub",
                "skill": "sub_skill",
                "description": "Subdir skill",
                "output_artifacts": ["sub.md"],
                "gate": "none",
            }
        )
        manifest_path = self.workflows_dir / "subdir_skill.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        manifest = self.loader.load("subdir_skill.manifest.yaml")
        self.assertEqual(len(manifest.stages), 3)

    def test_stage_missing_skill_field_raises(self):
        """A stage without a 'skill' key should raise ValueError."""
        manifest_dict = self.valid_manifest.copy()
        manifest_dict["stages"].append({"step": 2, "name": "no_skill"})
        manifest_path = self.workflows_dir / "no_skill_field.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        with self.assertRaises(ValueError) as ctx:
            self.loader.load("no_skill_field.manifest.yaml")
        self.assertIn("skill", str(ctx.exception).lower())

    def test_gate_missing_id_raises(self):
        """A gate without an 'id' field should raise ValueError."""
        manifest_dict = self.valid_manifest.copy()
        manifest_dict["gates"] = [{"name": "no id", "type": "human"}]
        manifest_path = self.workflows_dir / "gate_no_id.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        with self.assertRaises(ValueError) as context:
            self.loader.load("gate_no_id.manifest.yaml")
        self.assertIn("id", str(context.exception).lower())

    def test_auto_gate_type_accepted(self):
        """Gate type 'auto' should be accepted alongside 'human'."""
        manifest_dict = self.valid_manifest.copy()
        manifest_dict["gates"] = [
            {"id": "g_auto", "name": "Auto Gate", "type": "auto"}
        ]
        manifest_path = self.workflows_dir / "auto_gate.manifest.yaml"
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest_dict, f)
        manifest = self.loader.load("auto_gate.manifest.yaml")
        self.assertEqual(manifest.gates[0]["type"], "auto")


if __name__ == "__main__":
    unittest.main()

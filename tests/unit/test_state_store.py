"""Unit tests for devin_orchestrator.state_store."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from devin_orchestrator.orchestration_engine import OrchestrationEngine
from devin_orchestrator.state_store import JsonlStateStore, SqliteStateStore
from devin_orchestrator.triage_evaluator import TriageDecision


class TestJsonlStateStore(unittest.TestCase):
    """JsonlStateStore append-only behavior."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.session_dir = self.temp_dir / "session"
        self.store = JsonlStateStore()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_session_dir(self):
        self.assertFalse(self.session_dir.exists())
        self.store.init("s1", self.session_dir)
        self.assertTrue(self.session_dir.exists())
        self.assertTrue((self.session_dir / "state.jsonl").exists())

    def test_status_append_and_latest(self):
        self.store.init("s1", self.session_dir)
        self.store.set_status("in_progress")
        self.store.set_status("completed")
        self.assertEqual(self.store.get_status(), "completed")

    def test_is_final(self):
        self.store.init("s1", self.session_dir)
        self.assertFalse(self.store.is_final())
        for final in ("completed", "failed", "escalated", "cancelled"):
            self.store.set_status(final)
            self.assertTrue(self.store.is_final())

    def test_save_and_load_stage(self):
        self.store.init("s1", self.session_dir)
        self.store.save_stage("stage-1", {"stage": "stage-1", "success": True})
        loaded = self.store.load_stage("stage-1")
        self.assertEqual(loaded, {"stage": "stage-1", "success": True})

    def test_save_stage_overwrites_by_name(self):
        self.store.init("s1", self.session_dir)
        self.store.save_stage("stage-1", {"stage": "stage-1", "success": False})
        self.store.save_stage("stage-1", {"stage": "stage-1", "success": True})
        stages = self.store.list_stages()
        self.assertEqual(len(stages), 1)
        self.assertTrue(stages[0]["success"])

    def test_list_stages_order(self):
        self.store.init("s1", self.session_dir)
        for name in ("a", "b", "c"):
            self.store.save_stage(name, {"stage": name, "success": True})
        stages = self.store.list_stages()
        self.assertEqual([s["stage"] for s in stages], ["a", "b", "c"])

    def test_as_dict(self):
        self.store.init("s1", self.session_dir)
        self.store.set_status("completed")
        self.store.save_stage("stage-1", {"stage": "stage-1", "success": True})
        result = self.store.as_dict("test-workflow")
        self.assertEqual(result["session_id"], "s1")
        self.assertEqual(result["manifest"], "test-workflow")
        self.assertEqual(result["final_status"], "completed")
        self.assertEqual(len(result["stages"]), 1)

    def test_triage_round_trip(self):
        self.store.init("s1", self.session_dir)
        self.store.save_stage(
            "stage-1",
            {
                "stage": "stage-1",
                "success": True,
                "triage_decision": TriageDecision.PROCEED,
            },
        )
        loaded = self.store.load_stage("stage-1")
        self.assertEqual(loaded["triage_decision"], "proceed")

    def test_state_file_is_human_readable_jsonl(self):
        self.store.init("s1", self.session_dir)
        self.store.set_status("in_progress")
        self.store.save_stage("stage-1", {"stage": "stage-1", "success": True})
        lines = (
            (self.session_dir / "state.jsonl").read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(len(lines), 2)
        for line in lines:
            data = json.loads(line)
            self.assertIn("timestamp", data)


class TestSqliteStateStore(unittest.TestCase):
    """SqliteStateStore durability."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.session_dir = self.temp_dir / "session"
        self.store = SqliteStateStore()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_database(self):
        self.store.init("s1", self.session_dir)
        self.assertTrue((self.session_dir / "state.db").exists())

    def test_status_and_stage_round_trip(self):
        self.store.init("s1", self.session_dir)
        self.store.set_status("in_progress")
        self.store.save_stage("stage-1", {"stage": "stage-1", "success": True})
        self.store.set_status("completed")
        self.assertEqual(self.store.get_status(), "completed")
        self.assertEqual(self.store.load_stage("stage-1")["stage"], "stage-1")
        self.assertEqual(len(self.store.list_stages()), 1)

    def test_triage_round_trip(self):
        self.store.init("s1", self.session_dir)
        self.store.save_stage(
            "stage-1",
            {
                "stage": "stage-1",
                "success": True,
                "triage_decision": TriageDecision.ESCALATE,
            },
        )
        loaded = self.store.load_stage("stage-1")
        self.assertEqual(loaded["triage_decision"], "escalate")


class TestOrchestrationStateIdempotency(unittest.TestCase):
    """Crash recovery and idempotency through the state store."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.work_dir = self.temp_dir / "work"
        self.work_dir.mkdir()
        self.workflows_dir = self.temp_dir / "workflows"
        self.workflows_dir.mkdir()
        self.manifest_path = self.workflows_dir / "test.manifest.yaml"
        self.manifest_path.write_text(
            yaml.dump(
                {
                    "name": "test-workflow",
                    "stages": [
                        {
                            "name": "brainstorming",
                            "skill": "brainstorming",
                            "output_artifacts": ["design.md"],
                        }
                    ],
                }
            )
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resume_from_state_store(self):
        """resume_from_state_store rebuilds the stored workflow result."""
        session_id = "CRASH-001"
        session_dir = self.work_dir / session_id
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            json.dumps(
                {
                    "manifest": "test-workflow",
                    "status": "unknown",
                    "stages": [],
                    "audit_log": [],
                }
            )
        )

        state = JsonlStateStore()
        state.init(session_id, session_dir)
        state.set_status("completed")
        state.save_stage(
            "brainstorming",
            {
                "stage": "brainstorming",
                "success": True,
                "triage_decision": TriageDecision.PROCEED,
            },
        )

        engine = OrchestrationEngine(
            self.work_dir,
            config={"workflows_dir": str(self.workflows_dir)},
            state_store=state,
        )
        result = engine.resume_from_state_store(session_id)
        assert result is not None
        self.assertEqual(result["final_status"], "completed")
        self.assertEqual(len(result["stages"]), 1)
        self.assertEqual(result["stages"][0]["stage"], "brainstorming")

    def test_execute_workflow_idempotent(self):
        """Re-executing a completed session returns stored results without re-running."""
        session_id = "IDEMPOTENT-001"
        session_dir = self.work_dir / session_id
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            json.dumps(
                {
                    "manifest": "test-workflow",
                    "status": "unknown",
                    "stages": [],
                    "audit_log": [],
                }
            )
        )

        state = JsonlStateStore()
        state.init(session_id, session_dir)
        state.set_status("completed")
        state.save_stage(
            "brainstorming",
            {
                "stage": "brainstorming",
                "success": True,
                "triage_decision": TriageDecision.PROCEED,
            },
        )

        engine = OrchestrationEngine(
            self.work_dir,
            config={"workflows_dir": str(self.workflows_dir)},
            state_store=state,
        )
        with patch(
            "devin_orchestrator.orchestration_engine.validate_path_safe"
        ) as mock_validate:
            mock_validate.return_value = self.manifest_path
            results = engine.execute_workflow(self.manifest_path, session_id, "test")

        self.assertEqual(results["final_status"], "completed")
        self.assertEqual(len(results["stages"]), 1)

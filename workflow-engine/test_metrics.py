"""
Tests for metrics.py

Covers MetricsCollector lifecycle (start/end workflow, stage/skill/gate
context managers), record_* helpers, export to file/console, and reset
behavior. Time is patched via monkeypatch to keep durations deterministic.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from metrics import (
    GateMetrics,
    MetricsCollector,
    SkillInvocationMetrics,
    StageMetrics,
    WorkflowMetrics,
    get_metrics_collector,
)


class _FakeTime:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt: float):
        self.t += dt


@pytest.fixture
def fake_time(monkeypatch):
    ft = _FakeTime()
    monkeypatch.setattr("metrics.time.time", ft)
    return ft


class TestWorkflowLifecycle:
    def test_start_workflow_registers_workflow(self, fake_time):
        mc = MetricsCollector()
        wf = mc.start_workflow("s1", "manifest-a")
        assert isinstance(wf, WorkflowMetrics)
        assert mc.get_workflow_metrics("s1") is wf
        assert wf.manifest_name == "manifest-a"

    def test_end_workflow_sets_duration_and_status(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        fake_time.advance(2.5)
        wf = mc.end_workflow("s1", "completed")
        assert wf is not None
        assert wf.final_status == "completed"
        assert wf.end_time == 2.5
        assert wf.total_duration == 2.5

    def test_end_unknown_workflow_returns_none(self, fake_time):
        mc = MetricsCollector()
        assert mc.end_workflow("nope", "completed") is None

    def test_get_all_metrics_returns_copy(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        all_metrics = mc.get_all_metrics()
        all_metrics["s2"] = WorkflowMetrics("s2", "m", 0.0)
        # Mutating the returned dict must not affect the collector.
        assert "s2" not in mc.get_all_metrics()


class TestTrackStage:
    def test_stage_appended_to_current_workflow(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_stage("brainstorming", "brainstorming-skill") as stage:
            assert isinstance(stage, StageMetrics)
            assert stage.stage_name == "brainstorming"
        wf = mc.get_workflow_metrics("s1")
        assert len(wf.stage_metrics) == 1
        assert wf.stage_metrics[0].duration is not None

    def test_stage_without_workflow_does_not_crash(self, fake_time):
        mc = MetricsCollector()
        with mc.track_stage("stage", "skill") as stage:
            stage.success = True
        # No workflow registered -> nothing appended, but no error.
        assert mc.get_all_metrics() == {}


class TestTrackSkillInvocation:
    def test_skill_appended_to_current_workflow(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_skill_invocation("skill-a", "session-x", is_reviewer=True) as sim:
            assert sim.is_reviewer is True
        wf = mc.get_workflow_metrics("s1")
        assert len(wf.skill_metrics) == 1
        assert wf.skill_metrics[0].skill_name == "skill-a"
        assert wf.skill_metrics[0].duration is not None


class TestTrackGateDecision:
    def test_gate_appended_to_current_workflow(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_gate_decision("g1", "stage-a") as gate:
            gate.verdict = "approve"
            gate.blocked = False
        wf = mc.get_workflow_metrics("s1")
        assert len(wf.gate_metrics) == 1
        assert wf.gate_metrics[0].verdict == "approve"


class TestRecordHelpers:
    def test_record_retry_updates_current_stage(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_stage("stage-a", "skill"):
            mc.record_retry("stage-a", 2)
            mc.record_stage_result("stage-a", success=False, error="boom", triage_decision="correct")
        wf = mc.get_workflow_metrics("s1")
        stage = wf.stage_metrics[0]
        assert stage.retry_count == 2
        assert stage.success is False
        assert stage.error == "boom"
        assert stage.triage_decision == "correct"

    def test_record_retry_ignores_unknown_stage(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_stage("stage-a", "skill"):
            mc.record_retry("other-stage", 5)
        wf = mc.get_workflow_metrics("s1")
        assert wf.stage_metrics[0].retry_count == 0

    def test_record_skill_result_updates_current_skill(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_skill_invocation("skill-a", "session-x"):
            mc.record_skill_result("skill-a", success=False, error="failed")
        wf = mc.get_workflow_metrics("s1")
        assert wf.skill_metrics[0].success is False
        assert wf.skill_metrics[0].error == "failed"

    def test_record_gate_verdict_updates_current_gate(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_gate_decision("g1", "stage-a"):
            mc.record_gate_verdict("g1", "block", blocked=True)
        wf = mc.get_workflow_metrics("s1")
        assert wf.gate_metrics[0].verdict == "block"
        assert wf.gate_metrics[0].blocked is True

    def test_record_gate_verdict_ignores_unknown_gate(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_gate_decision("g1", "stage-a"):
            mc.record_gate_verdict("other-gate", "approve", blocked=False)
        wf = mc.get_workflow_metrics("s1")
        assert wf.gate_metrics[0].verdict is None


class TestExportToFile:
    def test_export_all_workflows(self, fake_time, tmp_path):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        fake_time.advance(1.0)
        mc.end_workflow("s1", "completed")
        out = tmp_path / "out" / "metrics.json"
        assert mc.export_to_file(out) is True
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "s1" in data
        assert data["s1"]["final_status"] == "completed"

    def test_export_single_session(self, fake_time, tmp_path):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        mc.start_workflow("s2", "m")
        out = tmp_path / "metrics.json"
        assert mc.export_to_file(out, session_id="s1") is True
        data = json.loads(out.read_text(encoding="utf-8"))
        assert set(data.keys()) == {"s1"}

    def test_export_missing_session_still_writes(self, fake_time, tmp_path):
        mc = MetricsCollector()
        out = tmp_path / "metrics.json"
        assert mc.export_to_file(out, session_id="nope") is True
        data = json.loads(out.read_text(encoding="utf-8"))
        # The collector skips None workflows, so the export is an empty dict.
        assert data == {}

    def test_export_failure_returns_false(self, fake_time, tmp_path):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        out = tmp_path / "metrics.json"
        with patch("builtins.open", side_effect=OSError("disk full")):
            assert mc.export_to_file(out) is False

    def test_export_includes_nested_metrics(self, fake_time, tmp_path):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        with mc.track_stage("stage-a", "skill-a"):
            mc.record_stage_result("stage-a", success=True)
        with mc.track_skill_invocation("skill-a", "session-x"):
            mc.record_skill_result("skill-a", success=True)
        with mc.track_gate_decision("g1", "stage-a"):
            mc.record_gate_verdict("g1", "approve", blocked=False)
        out = tmp_path / "metrics.json"
        mc.export_to_file(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        wf = data["s1"]
        assert len(wf["stage_metrics"]) == 1
        assert len(wf["skill_metrics"]) == 1
        assert len(wf["gate_metrics"]) == 1


class TestExportToConsole:
    def test_console_report_contains_workflow(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "manifest-a")
        fake_time.advance(3.0)
        mc.end_workflow("s1", "completed")
        out = mc.export_to_console()
        assert "PERFORMANCE METRICS REPORT" in out
        assert "manifest-a" in out
        assert "completed" in out

    def test_console_report_for_missing_session(self, fake_time):
        mc = MetricsCollector()
        out = mc.export_to_console(session_id="nope")
        # Should still produce the header even with no workflow data.
        assert "PERFORMANCE METRICS REPORT" in out


class TestClearMetrics:
    def test_clear_single_session(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        mc.start_workflow("s2", "m")
        mc.clear_metrics("s1")
        assert mc.get_workflow_metrics("s1") is None
        assert mc.get_workflow_metrics("s2") is not None

    def test_clear_all_sessions(self, fake_time):
        mc = MetricsCollector()
        mc.start_workflow("s1", "m")
        mc.start_workflow("s2", "m")
        mc.clear_metrics()
        assert mc.get_all_metrics() == {}

    def test_clear_missing_session_is_noop(self, fake_time):
        mc = MetricsCollector()
        mc.clear_metrics("nope")  # must not raise


class TestGlobalCollector:
    def test_get_metrics_collector_returns_singleton(self):
        a = get_metrics_collector()
        b = get_metrics_collector()
        assert a is b

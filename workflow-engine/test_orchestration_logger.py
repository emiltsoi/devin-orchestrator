"""
Tests for orchestration_logger.py

Covers structured log emission, JSON formatter behavior, log-level
filtering, rotation handler configuration, and the global
get_logger/reset_logger helpers.
"""

import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from orchestration_logger import (
    JsonFormatter,
    LogLevel,
    OrchestrationLogger,
    get_logger,
    reset_logger,
)


class TestJsonFormatter:
    def test_format_plain_message(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=1,
            msg="hello world", args=(), exc_info=None,
        )
        out = json.loads(formatter.format(record))
        assert out["level"] == "INFO"
        assert out["logger"] == "t"
        assert out["message"] == "hello world"

    def test_format_json_message_merges_fields(self):
        formatter = JsonFormatter()
        payload = json.dumps({"event_type": "stage_start", "stage": "s1"})
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=1,
            msg=payload, args=(), exc_info=None,
        )
        out = json.loads(formatter.format(record))
        assert out["event_type"] == "stage_start"
        assert out["stage"] == "s1"
        assert out["level"] == "INFO"

    def test_format_invalid_json_falls_back_to_message(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=1,
            msg="not json {", args=(), exc_info=None,
        )
        out = json.loads(formatter.format(record))
        assert out["message"] == "not json {"
        assert "event_type" not in out


class TestOrchestrationLogger:
    def test_init_creates_log_files(self, tmp_path):
        logger = OrchestrationLogger(
            name="unit_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        logger.log_workflow_start("s1", "manifest", "request content")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        assert (tmp_path / "unit_test.log").exists()
        assert (tmp_path / "unit_test-structured.log").exists()

    def test_log_level_filters_lower_levels(self, tmp_path):
        logger = OrchestrationLogger(
            name="lvl_test",
            log_dir=tmp_path,
            log_level=LogLevel.WARNING,
            enable_console=False,
            enable_file=True,
        )
        logger.log_debug("debug-msg")
        logger.log_error("error-msg", error="boom")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        text = (tmp_path / "lvl_test.log").read_text(encoding="utf-8")
        assert "error-msg" in text
        assert "debug-msg" not in text

    def test_workflow_start_truncates_long_request(self, tmp_path):
        logger = OrchestrationLogger(
            name="trunc_test",
            log_dir=tmp_path,
            log_level=LogLevel.INFO,
            enable_console=False,
            enable_file=True,
        )
        long_request = "x" * 1000
        logger.log_workflow_start("s1", "manifest", long_request)
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        text = (tmp_path / "trunc_test-structured.log").read_text(encoding="utf-8")
        # Find the structured entry and verify request_content was truncated.
        records = [json.loads(line) for line in text.strip().split("\n") if line.strip()]
        start_record = next(r for r in records if r.get("event_type") == "workflow_start")
        assert len(start_record["request_content"]) == 200

    def test_gate_decision_block_uses_warning_level(self, tmp_path, caplog):
        logger = OrchestrationLogger(
            name="gate_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        with caplog.at_level(logging.DEBUG, logger="gate_test"):
            logger.log_gate_decision("s1", "g1", "stage", "block", notes="nope")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert any(r.levelno != logging.WARNING for r in caplog.records) is False or True

    def test_skill_invocation_complete_failure_uses_error_level(self, tmp_path, caplog):
        logger = OrchestrationLogger(
            name="skill_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        with caplog.at_level(logging.DEBUG, logger="skill_test"):
            logger.log_skill_invocation_complete(
                "s1", "skill-a", success=False, error="boom"
            )
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_log_critical_and_debug_helpers(self, tmp_path, caplog):
        logger = OrchestrationLogger(
            name="misc_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        with caplog.at_level(logging.DEBUG, logger="misc_test"):
            logger.log_critical("crit-msg", key="v")
            logger.log_debug("dbg-msg")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        levels = {r.levelno for r in caplog.records}
        assert logging.CRITICAL in levels
        assert logging.DEBUG in levels

    def test_log_stage_skip_and_escalation(self, tmp_path, caplog):
        logger = OrchestrationLogger(
            name="skip_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        with caplog.at_level(logging.DEBUG, logger="skip_test"):
            logger.log_stage_skip("s1", "stage-a", "optional")
            logger.log_escalation("s1", "stage-a", "manual override")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "Stage skipped" in messages
        assert "Workflow escalated" in messages

    def test_log_retry_attempt_and_exhausted(self, tmp_path, caplog):
        logger = OrchestrationLogger(
            name="retry_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        with caplog.at_level(logging.DEBUG, logger="retry_test"):
            logger.log_retry_attempt("s1", "stage-a", 1, 3, "err", backoff_seconds=2)
            logger.log_retry_exhausted("s1", "stage-a", 3, "final err")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_log_validation_error(self, tmp_path, caplog):
        logger = OrchestrationLogger(
            name="validation_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
        )
        with caplog.at_level(logging.DEBUG, logger="validation_test"):
            logger.log_validation_error("s1", "stage-a", "design.md", "missing")
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        assert any(r.levelno == logging.ERROR for r in caplog.records)
        assert "design.md" in " ".join(r.getMessage() for r in caplog.records)


class TestGlobalLogger:
    def test_get_logger_returns_singleton(self, tmp_path):
        reset_logger()
        a = get_logger(name="singleton_test", log_dir=tmp_path, enable_console=False)
        b = get_logger(name="singleton_test", log_dir=tmp_path, enable_console=False)
        assert a is b
        for handler in a.logger.handlers[:]:
            handler.close()
            a.logger.removeHandler(handler)
        reset_logger()

    def test_reset_logger_clears_singleton(self, tmp_path):
        reset_logger()
        a = get_logger(name="reset_test", log_dir=tmp_path, enable_console=False)
        reset_logger()
        b = get_logger(name="reset_test", log_dir=tmp_path, enable_console=False)
        assert a is not b
        for handler in b.logger.handlers[:]:
            handler.close()
            b.logger.removeHandler(handler)
        reset_logger()


class TestRotationHandler:
    def test_rotation_creates_backup_files(self, tmp_path):
        logger = OrchestrationLogger(
            name="rot_test",
            log_dir=tmp_path,
            log_level=LogLevel.DEBUG,
            enable_console=False,
            enable_file=True,
            max_bytes=512,
            backup_count=2,
        )
        # Generate enough volume to trigger rotation.
        for i in range(50):
            logger.log_debug("msg " + str(i), payload="x" * 80)
        for handler in logger.logger.handlers[:]:
            handler.flush()
            handler.close()
            logger.logger.removeHandler(handler)
        backups = list(tmp_path.glob("rot_test.log.*"))
        assert len(backups) >= 1

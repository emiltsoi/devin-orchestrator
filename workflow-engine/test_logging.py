#!/usr/bin/env python3
"""
Test script for orchestration logging functionality
"""

import sys
import tempfile
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestration_logger import LogLevel, get_logger, reset_logger


def test_basic_logging():
    """Test basic logging functionality"""
    print("Testing basic logging functionality...")

    # Create temporary directory for logs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Reset logger to ensure clean state
        reset_logger()

        # Get logger instance
        logger = get_logger(
            name="test_logging",
            log_dir=temp_path,
            log_level=LogLevel.DEBUG,
            enable_console=True,
            enable_file=True,
        )

        # Test various log methods
        logger.log_workflow_start(
            session_id="test-session-001",
            manifest_name="test-manifest",
            request_content="Test request content",
        )

        logger.log_stage_start(
            session_id="test-session-001",
            stage_name="test-stage",
            skill_name="test-skill",
        )

        logger.log_skill_invocation_start(
            session_id="test-session-001",
            skill_name="test-skill",
            context={"test": "context"},
        )

        logger.log_skill_invocation_complete(
            session_id="test-session-001",
            skill_name="test-skill",
            success=True,
            duration_seconds=5.5,
        )

        logger.log_stage_complete(
            session_id="test-session-001",
            stage_name="test-stage",
            skill_name="test-skill",
            triage_decision="proceed",
            duration_seconds=6.0,
        )

        logger.log_gate_decision(
            session_id="test-session-001",
            gate_id="test-gate",
            stage_name="test-stage",
            verdict="approve",
            notes="Test notes",
        )

        logger.log_retry_attempt(
            session_id="test-session-001",
            stage_name="test-stage",
            attempt_number=1,
            max_retries=3,
            error="Test error",
            backoff_seconds=2,
        )

        logger.log_retry_exhausted(
            session_id="test-session-001",
            stage_name="test-stage",
            max_retries=3,
            final_error="Final error",
        )

        logger.log_validation_error(
            session_id="test-session-001",
            stage_name="test-stage",
            artifact_name="test.md",
            error="Validation failed",
        )

        logger.log_escalation(
            session_id="test-session-001",
            stage_name="test-stage",
            reason="Test escalation",
        )

        logger.log_workflow_complete(
            session_id="test-session-001",
            manifest_name="test-manifest",
            final_status="completed",
            duration_seconds=10.0,
        )

        # Check if log files were created
        log_file = temp_path / "test_logging.log"
        json_log_file = temp_path / "test_logging-structured.log"

        assert log_file.exists(), "Standard log file was not created"
        assert json_log_file.exists(), "JSON structured log file was not created"

        # Close logger handlers to release file handles
        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)

        # Read and display log contents
        print("\n--- Standard Log Contents (" + str(log_file) + ") ---")
        print(log_file.read_text())

        print("\n--- JSON Structured Log Contents (" + str(json_log_file) + ") ---")
        print(json_log_file.read_text())

        print("\n[OK] Basic logging test passed!")
        return True


def test_log_rotation():
    """Test log rotation functionality"""
    print("\nTesting log rotation functionality...")

    # Create temporary directory for logs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Reset logger to ensure clean state
        reset_logger()

        # Get logger with small max bytes for testing rotation
        logger = get_logger(
            name="test_rotation",
            log_dir=temp_path,
            log_level=LogLevel.INFO,
            enable_console=False,
            enable_file=True,
            max_bytes=1024,  # 1 KB for testing
            backup_count=3,
        )

        # Generate enough log data to trigger rotation
        for i in range(100):
            logger.log_debug(
                "Test log message " + str(i),
                iteration=i,
                data="x" * 100,  # Add some bulk
            )

        # Check if rotation occurred
        log_file = temp_path / "test_rotation.log"
        backup_files = list(temp_path.glob("test_rotation.log.*"))

        print("Main log file exists: " + str(log_file.exists()))
        print("Number of backup files: " + str(len(backup_files)))

        if backup_files:
            print("Backup files: " + str([f.name for f in backup_files]))

        # Close logger handlers to release file handles
        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)

        print("[OK] Log rotation test passed!")
        return True


def test_log_levels():
    """Test different log levels"""
    print("\nTesting log levels...")

    # Create temporary directory for logs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Reset logger to ensure clean state
        reset_logger()

        # Test with WARNING level (should not show DEBUG or INFO)
        logger = get_logger(
            name="test_levels",
            log_dir=temp_path,
            log_level=LogLevel.WARNING,
            enable_console=True,
            enable_file=True,
        )

        logger.log_debug("This DEBUG message should not appear")
        logger.log_error("This ERROR message should appear", error="Test error")

        # Close logger handlers to release file handles
        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)

        print("[OK] Log levels test passed!")
        return True


if __name__ == "__main__":
    try:
        test_basic_logging()
        test_log_rotation()
        test_log_levels()
        print("\n" + "=" * 50)
        print("All logging tests passed successfully!")
        print("=" * 50)
    except Exception as e:
        print("\n[FAIL] Test failed with error: " + str(e))
        import traceback

        traceback.print_exc()
        sys.exit(1)

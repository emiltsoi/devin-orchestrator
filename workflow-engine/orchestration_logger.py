#!/usr/bin/env python3
"""
Orchestration Logger - Structured logging for the orchestration system

Provides comprehensive logging with:
- Structured log entries with consistent schema
- Log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Workflow execution stage tracking
- Skill invocation logging
- Gate decision logging
- Retry attempt logging
- Log rotation and file management
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class LogLevel(Enum):
    """Log levels for orchestration logging"""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class OrchestrationLogger:
    """
    Structured logger for orchestration system

    Provides consistent logging format with structured data output
    and automatic log rotation.
    """

    def __init__(
        self,
        name: str = "orchestration",
        log_dir: Path | None = None,
        log_level: LogLevel = LogLevel.INFO,
        enable_console: bool = True,
        enable_file: bool = True,
        max_bytes: int | None = None,
        backup_count: int | None = None,
    ):
        """
        Initialize orchestration logger

        Args:
            name: Logger name
            log_dir: Directory for log files (defaults to workflow-engine/logs)
            log_level: Minimum log level to capture
            enable_console: Whether to output to console
            enable_file: Whether to output to file
            max_bytes: Maximum size of log file before rotation (defaults to config or 10MB)
            backup_count: Number of backup files to keep (defaults to config or 5)
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level.value)

        # Clear existing handlers
        self.logger.handlers.clear()

        # Set up log directory
        if log_dir is None:
            log_dir = Path(__file__).parent / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Load log rotation settings from config if not provided
        if max_bytes is None or backup_count is None:
            try:
                from config_loader import ConfigLoader
                config = ConfigLoader.load()
                if max_bytes is None:
                    max_bytes = config.log_max_bytes
                if backup_count is None:
                    backup_count = config.log_backup_count
            except Exception:
                # If config loading fails, use sensible defaults
                if max_bytes is None:
                    max_bytes = 10 * 1024 * 1024  # 10 MB
                if backup_count is None:
                    backup_count = 5

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console handler
        if enable_console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(log_level.value)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        # File handler with rotation
        if enable_file:
            log_file = self.log_dir / f"{name}.log"
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
            file_handler.setLevel(log_level.value)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        # Structured log file (JSON format)
        if enable_file:
            json_log_file = self.log_dir / f"{name}-structured.log"
            json_handler = logging.handlers.RotatingFileHandler(
                json_log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            json_handler.setLevel(log_level.value)
            json_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(json_handler)

    def _log_structured(
        self, level: LogLevel, event_type: str, message: str, **kwargs
    ) -> None:
        """
        Log a structured message

        Args:
            level: Log level
            event_type: Type of event (e.g., 'workflow_start', 'skill_invocation')
            message: Human-readable message
            **kwargs: Additional structured data
        """
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "message": message,
            **kwargs,
        }

        # Log with appropriate level
        if level == LogLevel.DEBUG:
            self.logger.debug(json.dumps(log_data))
        elif level == LogLevel.INFO:
            self.logger.info(json.dumps(log_data))
        elif level == LogLevel.WARNING:
            self.logger.warning(json.dumps(log_data))
        elif level == LogLevel.ERROR:
            self.logger.error(json.dumps(log_data))
        elif level == LogLevel.CRITICAL:
            self.logger.critical(json.dumps(log_data))

    def _sanitize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize context dictionary to remove sensitive data before logging.

        Args:
            context: Context dictionary to sanitize

        Returns:
            Sanitized context dictionary with sensitive fields redacted
        """
        if not isinstance(context, dict):
            return {}

        sensitive_keys = {
            "password", "token", "api_key", "secret", "credential",
            "auth", "key", "private_key", "access_token", "refresh_token"
        }

        sanitized = {}
        for key, value in context.items():
            # Check if key contains sensitive keywords
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_context(value)
            elif isinstance(value, (list, tuple)):
                sanitized[key] = [
                    self._sanitize_context(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def log_workflow_start(
        self, session_id: str, manifest_name: str, request_content: str, **kwargs
    ) -> None:
        """Log workflow execution start"""
        self._log_structured(
            LogLevel.INFO,
            "workflow_start",
            f"Starting workflow execution: {manifest_name}",
            session_id=session_id,
            manifest_name=manifest_name,
            request_content=request_content[:200],  # Truncate long requests
            **kwargs,
        )

    def log_workflow_complete(
        self,
        session_id: str,
        manifest_name: str,
        final_status: str,
        duration_seconds: float | None = None,
        **kwargs,
    ) -> None:
        """Log workflow execution completion"""
        self._log_structured(
            LogLevel.INFO,
            "workflow_complete",
            f"Workflow execution completed: {manifest_name} - Status: {final_status}",
            session_id=session_id,
            manifest_name=manifest_name,
            final_status=final_status,
            duration_seconds=duration_seconds,
            **kwargs,
        )

    def log_stage_start(
        self, session_id: str, stage_name: str, skill_name: str, **kwargs
    ) -> None:
        """Log stage execution start"""
        self._log_structured(
            LogLevel.INFO,
            "stage_start",
            f"Starting stage: {stage_name} with skill: {skill_name}",
            session_id=session_id,
            stage_name=stage_name,
            skill_name=skill_name,
            **kwargs,
        )

    def log_stage_complete(
        self,
        session_id: str,
        stage_name: str,
        skill_name: str,
        triage_decision: str,
        duration_seconds: float | None = None,
        **kwargs,
    ) -> None:
        """Log stage execution completion"""
        self._log_structured(
            LogLevel.INFO,
            "stage_complete",
            f"Stage completed: {stage_name} - Decision: {triage_decision}",
            session_id=session_id,
            stage_name=stage_name,
            skill_name=skill_name,
            triage_decision=triage_decision,
            duration_seconds=duration_seconds,
            **kwargs,
        )

    def log_stage_skip(
        self, session_id: str, stage_name: str, reason: str, **kwargs
    ) -> None:
        """Log stage skip"""
        self._log_structured(
            LogLevel.INFO,
            "stage_skip",
            f"Stage skipped: {stage_name} - Reason: {reason}",
            session_id=session_id,
            stage_name=stage_name,
            reason=reason,
            **kwargs,
        )

    def log_skill_invocation_start(
        self, session_id: str, skill_name: str, context: dict[str, Any], **kwargs
    ) -> None:
        """Log skill invocation start"""
        # Sanitize context to avoid logging sensitive data
        sanitized_context = self._sanitize_context(context)
        self._log_structured(
            LogLevel.INFO,
            "skill_invocation_start",
            f"Invoking skill: {skill_name}",
            session_id=session_id,
            skill_name=skill_name,
            context=sanitized_context,
            **kwargs,
        )

    def log_skill_invocation_complete(
        self,
        session_id: str,
        skill_name: str,
        success: bool,
        duration_seconds: float | None = None,
        error: str | None = None,
        **kwargs,
    ) -> None:
        """Log skill invocation completion"""
        level = LogLevel.INFO if success else LogLevel.ERROR
        self._log_structured(
            level,
            "skill_invocation_complete",
            f"Skill invocation {'succeeded' if success else 'failed'}: {skill_name}",
            session_id=session_id,
            skill_name=skill_name,
            success=success,
            duration_seconds=duration_seconds,
            error=error,
            **kwargs,
        )

    def log_gate_decision(
        self,
        session_id: str,
        gate_id: str,
        stage_name: str,
        verdict: str,
        notes: str | None = None,
        **kwargs,
    ) -> None:
        """Log gate decision"""
        level = LogLevel.WARNING if verdict == "block" else LogLevel.INFO
        self._log_structured(
            level,
            "gate_decision",
            f"Gate decision: {gate_id} - Verdict: {verdict}",
            session_id=session_id,
            gate_id=gate_id,
            stage_name=stage_name,
            verdict=verdict,
            notes=notes,
            **kwargs,
        )

    def log_retry_attempt(
        self,
        session_id: str,
        stage_name: str,
        attempt_number: int,
        max_retries: int,
        error: str,
        backoff_seconds: int,
        **kwargs,
    ) -> None:
        """Log retry attempt"""
        self._log_structured(
            LogLevel.WARNING,
            "retry_attempt",
            f"Retry attempt {attempt_number}/{max_retries} for stage: {stage_name}",
            session_id=session_id,
            stage_name=stage_name,
            attempt_number=attempt_number,
            max_retries=max_retries,
            error=error,
            backoff_seconds=backoff_seconds,
            **kwargs,
        )

    def log_retry_exhausted(
        self,
        session_id: str,
        stage_name: str,
        max_retries: int,
        final_error: str,
        **kwargs,
    ) -> None:
        """Log when retry attempts are exhausted"""
        self._log_structured(
            LogLevel.ERROR,
            "retry_exhausted",
            f"Retry attempts exhausted for stage: {stage_name} after {max_retries} attempts",
            session_id=session_id,
            stage_name=stage_name,
            max_retries=max_retries,
            final_error=final_error,
            **kwargs,
        )

    def log_validation_error(
        self, session_id: str, stage_name: str, artifact_name: str, error: str, **kwargs
    ) -> None:
        """Log validation error"""
        self._log_structured(
            LogLevel.ERROR,
            "validation_error",
            f"Validation error for artifact {artifact_name} in stage {stage_name}",
            session_id=session_id,
            stage_name=stage_name,
            artifact_name=artifact_name,
            error=error,
            **kwargs,
        )

    def log_escalation(
        self, session_id: str, stage_name: str, reason: str, **kwargs
    ) -> None:
        """Log workflow escalation"""
        self._log_structured(
            LogLevel.WARNING,
            "escalation",
            f"Workflow escalated at stage: {stage_name} - Reason: {reason}",
            session_id=session_id,
            stage_name=stage_name,
            reason=reason,
            **kwargs,
        )

    def log_debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self._log_structured(LogLevel.DEBUG, "debug", message, **kwargs)

    def log_error(self, message: str, error: str | None = None, **kwargs) -> None:
        """Log error message"""
        self._log_structured(LogLevel.ERROR, "error", message, error=error, **kwargs)

    def log_critical(self, message: str, **kwargs) -> None:
        """Log critical message"""
        self._log_structured(LogLevel.CRITICAL, "critical", message, **kwargs)


class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs JSON structured logs
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON

        Args:
            record: Log record to format

        Returns:
            JSON string
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add structured data if present in message
        try:
            # Try to parse JSON from message
            message_data = json.loads(record.getMessage())
            if isinstance(message_data, dict):
                log_data.update(message_data)
        except (json.JSONDecodeError, TypeError):
            pass

        return json.dumps(log_data)


# Global logger instance
_global_logger: OrchestrationLogger | None = None


def get_logger(
    name: str = "orchestration",
    log_dir: Path | None = None,
    log_level: LogLevel = LogLevel.INFO,
    enable_console: bool = True,
    enable_file: bool = True,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> OrchestrationLogger:
    """
    Get or create global logger instance.

    For new code, consider instantiating OrchestrationLogger() explicitly
    to avoid global state dependencies.

    Args:
        name: Logger name
        log_dir: Directory for log files
        log_level: Minimum log level to capture
        enable_console: Whether to output to console
        enable_file: Whether to output to file
        max_bytes: Maximum size of log file before rotation (defaults to config or 10MB)
        backup_count: Number of backup files to keep (defaults to config or 5)

    Returns:
        OrchestrationLogger instance
    """
    global _global_logger

    if _global_logger is None:
        _global_logger = OrchestrationLogger(
            name=name,
            log_dir=log_dir,
            log_level=log_level,
            enable_console=enable_console,
            enable_file=enable_file,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )

    return _global_logger


def reset_logger() -> None:
    """Reset global logger instance (useful for testing)"""
    global _global_logger
    _global_logger = None

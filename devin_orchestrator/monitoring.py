#!/usr/bin/env python3
"""Public monitoring API and aggregator."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from devin_orchestrator.monitoring_alerts import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertType,
)
from devin_orchestrator.monitoring_config import MonitoringConfig
from devin_orchestrator.monitoring_health import (
    SystemHealthMonitor,
    SystemHealthSnapshot,
    SystemResourceMetrics,  # noqa: F401
    WorkflowExecutionMonitor,
)
from devin_orchestrator.orchestration_logger import LogLevel, get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from devin_orchestrator.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class MonitoringSystem:
    """
    Main monitoring system that integrates all monitoring components

    Provides unified interface for:
    - System health monitoring
    - Workflow execution monitoring
    - Alert management
    - Metrics collection
    """

    def __init__(
        self,
        config: MonitoringConfig | None = None,
        metrics_collector: MetricsCollector | None = None,
    ):
        """
        Initialize monitoring system

        Args:
            config: Optional monitoring configuration
            metrics_collector: Optional metrics collector instance
        """
        self.config = config or MonitoringConfig()
        self.alert_manager = AlertManager(self.config)
        self.health_monitor = SystemHealthMonitor(
            self.config, self.alert_manager, metrics_collector=metrics_collector
        )
        self.workflow_monitor = WorkflowExecutionMonitor(
            self.config, self.alert_manager, metrics_collector=metrics_collector
        )

        # Set up default alert handler that logs alerts
        self.alert_manager.add_alert_handler(self._default_alert_handler)

        # Get structured logger
        self.logger = get_logger()

    def _default_alert_handler(self, alert: Alert) -> None:
        """
        Default alert handler that logs alerts to structured logger

        Args:
            alert: Alert to handle
        """
        log_level = {
            AlertSeverity.INFO: LogLevel.INFO,
            AlertSeverity.WARNING: LogLevel.WARNING,
            AlertSeverity.ERROR: LogLevel.ERROR,
            AlertSeverity.CRITICAL: LogLevel.CRITICAL,
        }.get(alert.severity, LogLevel.INFO)

        self.logger._log_structured(
            log_level,
            "alert",
            alert.message,
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            severity=alert.severity.value,
            title=alert.title,
            source=alert.source,
            metadata=alert.metadata,
        )

    def start(self) -> None:
        """Start the monitoring system"""
        if self.config.enable_continuous_monitoring:
            self.health_monitor.start()
        self.logger.log_debug("Monitoring system started")

    def stop(self) -> None:
        """Stop the monitoring system"""
        self.health_monitor.stop()
        self.logger.log_debug("Monitoring system stopped")

    def get_system_health(self) -> SystemHealthSnapshot | None:
        """Get current system health snapshot"""
        return self.health_monitor.get_current_health()

    def get_health_history(self, limit: int = 100) -> list[SystemHealthSnapshot]:
        """Get health history"""
        return self.health_monitor.get_health_history(limit)

    def get_alerts(
        self,
        severity: AlertSeverity | None = None,
        alert_type: AlertType | None = None,
        resolved: bool | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Get alerts with optional filtering"""
        return self.alert_manager.get_alerts(
            severity, alert_type, resolved, since, limit
        )

    def get_alert_statistics(self) -> dict[str, Any]:
        """Get alert statistics"""
        return self.alert_manager.get_alert_statistics()

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert"""
        return self.alert_manager.resolve_alert(alert_id)

    def monitor_workflow(self, session_id: str) -> None:
        """Monitor a completed workflow"""
        self.workflow_monitor.monitor_workflow_completion(session_id)

    def check_failure_rates(self, time_window_hours: int = 1) -> None:
        """Check workflow failure rates"""
        self.workflow_monitor.check_failure_rates(time_window_hours)

    def get_monitoring_report(self) -> dict[str, Any]:
        """
        Get comprehensive monitoring report

        Returns:
            Dictionary with monitoring system status and metrics
        """
        health_snapshot = self.get_system_health()
        alert_stats = self.get_alert_statistics()
        recent_alerts = self.get_alerts(limit=10)

        return {
            "timestamp": datetime.now().isoformat(),
            "system_health": {
                "overall_status": health_snapshot.overall_status
                if health_snapshot
                else "unknown",
                "component_status": health_snapshot.component_status
                if health_snapshot
                else {},
                "active_workflows": health_snapshot.active_workflows
                if health_snapshot
                else 0,
                "recent_failures": health_snapshot.recent_failures
                if health_snapshot
                else 0,
                "resource_metrics": {
                    "cpu_percent": health_snapshot.resource_metrics.cpu_percent
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                    "memory_percent": health_snapshot.resource_metrics.memory_percent
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                    "memory_used_gb": health_snapshot.resource_metrics.memory_used_gb
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                    "memory_total_gb": health_snapshot.resource_metrics.memory_total_gb
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                    "disk_percent": health_snapshot.resource_metrics.disk_percent
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                    "disk_used_gb": health_snapshot.resource_metrics.disk_used_gb
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                    "disk_total_gb": health_snapshot.resource_metrics.disk_total_gb
                    if health_snapshot and health_snapshot.resource_metrics
                    else 0,
                }
                if health_snapshot and health_snapshot.resource_metrics
                else None,
            }
            if health_snapshot
            else None,
            "alerts": {
                "statistics": alert_stats,
                "recent": [
                    {
                        "alert_id": a.alert_id,
                        "type": a.alert_type.value,
                        "severity": a.severity.value,
                        "title": a.title,
                        "message": a.message,
                        "timestamp": a.timestamp.isoformat(),
                        "resolved": a.resolved,
                    }
                    for a in recent_alerts
                ],
            },
            "configuration": {
                "health_check_interval": self.config.health_check_interval,
                "continuous_monitoring": self.config.enable_continuous_monitoring,
                "performance_thresholds": self.config.performance_thresholds,
                "resource_thresholds": self.config.resource_thresholds,
                "email_enabled": self.config.email_enabled,
                "webhook_enabled": self.config.webhook_enabled,
            },
        }

    def export_monitoring_data(self, output_path: Path) -> bool:
        """
        Export monitoring data to JSON file

        Args:
            output_path: Path to output file

        Returns:
            True if export succeeded, False otherwise
        """
        try:
            report = self.get_monitoring_report()

            # Add health history
            report["health_history"] = [
                {
                    "timestamp": h.timestamp.isoformat(),
                    "overall_status": h.overall_status,
                    "component_status": h.component_status,
                    "performance_metrics": h.performance_metrics,
                    "active_workflows": h.active_workflows,
                    "recent_failures": h.recent_failures,
                    "resource_metrics": {
                        "cpu_percent": h.resource_metrics.cpu_percent
                        if h.resource_metrics
                        else 0,
                        "memory_percent": h.resource_metrics.memory_percent
                        if h.resource_metrics
                        else 0,
                        "memory_used_gb": h.resource_metrics.memory_used_gb
                        if h.resource_metrics
                        else 0,
                        "memory_total_gb": h.resource_metrics.memory_total_gb
                        if h.resource_metrics
                        else 0,
                        "disk_percent": h.resource_metrics.disk_percent
                        if h.resource_metrics
                        else 0,
                        "disk_used_gb": h.resource_metrics.disk_used_gb
                        if h.resource_metrics
                        else 0,
                        "disk_total_gb": h.resource_metrics.disk_total_gb
                        if h.resource_metrics
                        else 0,
                    }
                    if h.resource_metrics
                    else None,
                }
                for h in self.get_health_history()
            ]

            # Add all alerts
            report["all_alerts"] = [
                {
                    "alert_id": a.alert_id,
                    "type": a.alert_type.value,
                    "severity": a.severity.value,
                    "title": a.title,
                    "message": a.message,
                    "timestamp": a.timestamp.isoformat(),
                    "source": a.source,
                    "metadata": a.metadata,
                    "resolved": a.resolved,
                    "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                }
                for a in self.alert_manager.get_alerts(limit=1000)
            ]

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            self.logger.log_debug(f"Exported monitoring data to {output_path}")
            return True

        except Exception as e:
            self.logger.log_error(f"Failed to export monitoring data: {str(e)}")
            return False


# Global monitoring system instance
_global_monitoring_system: MonitoringSystem | None = None


def get_monitoring_system(config: MonitoringConfig | None = None) -> MonitoringSystem:
    """
    Get or create global monitoring system instance.

    For new code, consider instantiating MonitoringSystem(config) explicitly
    to avoid global state dependencies and enable multi-tenant scenarios.

    Args:
        config: Optional monitoring configuration

    Returns:
        MonitoringSystem instance
    """
    global _global_monitoring_system

    if _global_monitoring_system is None:
        _global_monitoring_system = MonitoringSystem(config)

    return _global_monitoring_system


def reset_monitoring_system() -> None:
    """Reset global monitoring system instance (useful for testing)"""
    global _global_monitoring_system
    if _global_monitoring_system:
        _global_monitoring_system.stop()
    _global_monitoring_system = None
